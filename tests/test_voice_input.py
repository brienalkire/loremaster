import numpy as np
import pytest

voice_input = pytest.importorskip("voice_input", reason="needs py-cord and webrtcvad")
extract = voice_input.extract_wake_word_query


# Punctuation at either end of the question is stripped.
@pytest.mark.parametrize("transcript, query", [
    ("Loremaster, what should we play?", "what should we play"),
    ("hey LOREMASTER what's the boss weak to", "what's the boss weak to"),
    ("Laura Master, how do I craft a bow?", "how do I craft a bow"),   # heard as two words
    ("Ormaster: is this build good", "is this build good"),
])
def test_wake_word_finds_the_question(transcript, query):
    assert extract(transcript, "loremaster") == query


def test_wake_word_alone_returns_empty_string():
    """An utterance that's only the wake word primes the speaker's next
    utterance. That depends on "" here, as opposed to None for no wake word."""
    assert extract("Loremaster.", "loremaster") == ""
    assert extract("Laura Master", "loremaster") == ""


@pytest.mark.parametrize("transcript", [
    "what should we play tonight",
    "the master of lore is here",       # "master" alone scores 0.75
    "I need a dungeon master tonight",
    "",
])
def test_no_wake_word_returns_none(transcript):
    assert extract(transcript, "loremaster") is None


def test_near_misses_below_the_threshold_need_an_alias():
    # "Warmaster" scores 0.737 against "loremaster", just under 0.75, which
    # is what LOREMASTER_WAKE_WORD_ALIASES is for.
    assert extract("Warmaster, what's next?", "loremaster") is None
    assert extract("Warmaster, what's next?", "warmaster") == "what's next"


def test_stereo_to_mono_averages_channels():
    stereo = np.array([100, 300, -200, 200], dtype=np.int16).tobytes()
    assert voice_input.stereo_bytes_to_mono(stereo).tolist() == [200, 0]


def test_whisper_audio_is_downsampled_to_16k():
    one_second_48k = np.zeros(48000, dtype=np.int16).tobytes()
    audio = voice_input.mono_pcm_to_whisper_audio(one_second_48k)
    assert len(audio) == 16000


def test_default_wake_word_gets_warmaster_alias():
    assert voice_input.wake_word_aliases("loremaster", ()) == ("warmaster",)
    assert voice_input.wake_word_aliases("Loremaster", ()) == ("warmaster",)


def test_custom_wake_word_gets_no_default_alias():
    assert voice_input.wake_word_aliases("gandalf", ()) == ()


def test_configured_aliases_replace_the_default():
    assert voice_input.wake_word_aliases("loremaster", ("lord master",)) == ("lord master",)
