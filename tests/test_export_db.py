import pytest

import export_db
import feedback
import memory_store as ms


@pytest.fixture
def export_paths(db, tmp_path, monkeypatch):
    monkeypatch.setattr(export_db, "DB_PATH", db)
    monkeypatch.setattr(export_db, "BACKUP_PATH", tmp_path / "backup.sql")
    monkeypatch.setattr(export_db, "FEEDBACK_PATHS",
                        {"wish": tmp_path / "WISHLIST.md", "bug": tmp_path / "BUGS.md"})
    return tmp_path


def test_export_then_restore_round_trip(export_paths, instructions, requester, monkeypatch):
    ms.create_campaign("Run", "alpha")
    ms.update_campaign_state("Party is level 5.")
    requester()
    feedback.add_item("wish", "track loot")
    export_db.export()

    assert "Party is level 5." in (export_paths / "backup.sql").read_text(encoding="utf-8")
    assert "track loot" in (export_paths / "WISHLIST.md").read_text(encoding="utf-8")
    assert (export_paths / "BUGS.md").exists()

    restored = export_paths / "restored.db"
    monkeypatch.setattr(export_db, "DB_PATH", restored)
    export_db.restore()
    monkeypatch.setattr(ms, "DB_PATH", restored)
    assert ms.get_campaign_state() == {"campaign": "Run", "notes": "Party is level 5."}
    assert feedback.list_items("wish")["items"][0]["summary"] == "track loot"


def test_restore_refuses_to_overwrite(export_paths):
    export_db.export()
    with pytest.raises(SystemExit, match="already exists"):
        export_db.restore()
