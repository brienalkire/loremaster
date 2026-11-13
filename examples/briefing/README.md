# A narrated briefing about Loremaster

These files make the six-minute video introducing Loremaster, narrated in
the bot's own voice. The finished video is on the
[v0.7.0 release page](https://github.com/brienalkire/loremaster/releases/tag/v0.7.0).

| File | What it is |
| --- | --- |
| `loremaster-intro.pdf` | The slides |
| `loremaster-intro.md` | The narration script, one `## Page N` section per slide |
| `loremaster-intro.lexicon.txt` | Pronunciation fixes (ffmpeg, SQLite and so on) |
| `loremaster-intro.html` | The slides' source, for editing them |

The video was made with
[podcast-generator](https://github.com/brienalkire/podcast_generator),
using Kokoro's `bm_george` voice, which is also Loremaster's default
speaking voice. To rebuild it, install podcast-generator with the
`briefing` extra and make sure ffmpeg is on your `PATH`:

```
pip install "podcast-generator[briefing]"
podcast-generator examples/briefing/loremaster-intro.md
```

The script's `**Briefing:**` and `**Lexicon:**` lines name the PDF and the
lexicon, which are looked for next to the script. Add `--preview` to see
how long each slide is shown without making the video.

To change the slides, edit `loremaster-intro.html` and print it to PDF
from Chrome or Edge, with the page size set by the file (13.333 × 7.5
inches, one slide per page). Keep the narration's page sections in step
with the slides.
