# Creating a New Album — Step-by-Step Guide

This guide walks you through creating a completely new album with new songs, lyrics, and narrative for the Chak Chak Mage Interactive Album platform.

---

## Prerequisites

- Python 3.10+ with the `chak` package installed (`pip install -e .`)
- GPU setup for alignment (Whisper/stable-ts) and image generation (SDXL-Turbo)
- Audio files (MP3) for your tracks
- Lyrics for each track (plain text, one line per lyric line)

## 1. Create the Album Directory

```
albums/
  MY_ALBUM_002/
    album_config.json
    semantic_matrix.json
    lyrics/
      track_01.txt
      track_02.txt
      ...
```

## 2. Write `album_config.json`

This is the master config that defines your album. All fields are required unless noted.

```json
{
    "album_id": "MY_ALBUM_002",
    "title": "Your Album Title",
    "artist": "Artist Name",
    "description": "Short description of the album.",
    "source": "CUSTOM",
    "tracks": [
        {
            "slot": 1,
            "track_id": "track_01",
            "title": "First Track Name",
            "variant_id": "T1a",
            "audio_path": "T1a.mp3",
            "theme": { "accent": "#ffaa00", "glow": "rgba(255,170,0,0.6)" },
            "variants": [
                { "id": "T1a", "label": "Version A", "audio": "T1a.mp3" },
                { "id": "T1b", "label": "Version B", "audio": "T1b.mp3" }
            ]
        },
        {
            "slot": 2,
            "track_id": "track_02",
            "title": "Second Track Name",
            "variant_id": "T2a",
            "audio_path": "T2a.mp3",
            "theme": { "accent": "#ff4444", "glow": "rgba(255,68,68,0.6)" },
            "variants": []
        }
    ]
}
```

### Field Reference

| Field | Description |
|-------|-------------|
| `album_id` | Unique ID, used as directory name. Use UPPER_SNAKE_CASE. |
| `title` | Display title shown in the player UI. |
| `artist` | Artist name shown in the player. |
| `tracks[].slot` | 1-based position in the album. |
| `tracks[].track_id` | Logical ID (e.g. `track_01`). Must be unique within the album. |
| `tracks[].title` | Track display name. |
| `tracks[].variant_id` | The default variant to use. Must match one of the `variants[].id` entries. |
| `tracks[].audio_path` | Path to the default MP3, relative to the album's audio source. |
| `tracks[].theme` | Optional. `accent` (hex color) + `glow` (rgba). Auto-generated if omitted. |
| `tracks[].variants` | Array of alternative versions. Can be empty for single-version tracks. |

## 3. Place Audio Files

Put your MP3 files where the pipeline can find them. The default location depends on your `source` field. For a custom album, place them alongside your config or in a dedicated audio directory.

## 4. Write Lyrics

Create one text file per track in `albums/MY_ALBUM_002/lyrics/`:

```
track_01.txt
track_02.txt
...
```

Format: one line per lyric line. Empty lines are ignored. The file name must match the `track_id`.

## 5. Create `semantic_matrix.json`

This is the creative heart of the album. It defines what images appear for each lyric line, plus the hidden narrative layer.

```json
{
    "tracks": {
        "track_01": {
            "lines": [
                {
                    "text": "First line of lyrics",
                    "media_queries": [
                        "Wide shot: visual description for literal story image 1",
                        "Close shot: visual description for literal story image 2",
                        "Medium shot: visual description for literal story image 3"
                    ],
                    "hidden_media_queries": [
                        "Wide shot: hidden narrative image 1",
                        "Close shot: hidden narrative image 2",
                        "Medium shot: hidden narrative image 3"
                    ],
                    "real_meaning": "What this line really means in the hidden narrative"
                }
            ]
        }
    }
}
```

Each line gets:
- **3 `media_queries`** — literal story images (Zone 1, phone frame)
- **3 `hidden_media_queries`** — hidden narrative images (Zone 2, outer panels)
- **`real_meaning`** — text shown in the meaning panel

Prompt tips for SDXL-Turbo:
- Keep prompts 15-30 words
- Be visual and specific: describe the scene, not the emotion
- Start with shot type: "Wide shot:", "Close shot:", "Aerial view:", etc.
- Avoid abstract concepts — describe what the camera sees

## 6. Run the Pipeline

### Full build (all stages)

```bash
chak build MY_ALBUM_002
```

This runs: `align` -> `timeline` -> `structure` -> `manifest` -> `fetch_media` -> `fuse` -> `export`

### Individual stages (for debugging or re-running)

```bash
chak align MY_ALBUM_002        # Force-align lyrics to audio
chak timeline MY_ALBUM_002     # Build word-level timelines
chak structure MY_ALBUM_002    # Analyze musical structure (energy, beats, sections)
chak media-prep MY_ALBUM_002   # Prepare image manifest from semantic matrix
chak media-fetch MY_ALBUM_002  # Generate/download images
chak fuse MY_ALBUM_002         # Fuse lyrics + images + structure into track data
chak export MY_ALBUM_002       # Export JS data files for the frontend
```

### Process variants (if you have multiple versions of tracks)

```bash
chak process-variants MY_ALBUM_002
```

### Regenerate the album index

```bash
chak index
```

This updates `albums/albums_index.json` so the frontend discovers your new album.

## 7. Verify

```bash
# Check pipeline status
chak status MY_ALBUM_002

# Validate data integrity
chak validate MY_ALBUM_002

# Serve locally
python -m http.server 8080
# Open http://localhost:8080
```

The player automatically discovers albums from `albums_index.json` — no frontend code changes needed.

## 8. Pipeline Output

After a successful build, your album directory will contain:

```
albums/MY_ALBUM_002/
  album_config.json          # Your config
  semantic_matrix.json       # Your narrative data
  lyrics/                    # Your lyrics files
  data/
    track_01.js              # Fused track data (lyrics + timing + images)
    track_01_T1a.js          # Default variant copy
    track_01.timeline.json   # Word-level timestamps
    track_01.structure.json  # Musical structure analysis
    ...
  media/
    track_01/                # Generated images per track
      img_001.webp
      img_002.webp
      ...
```

## Tips

- **Themes are optional**: If you omit `theme` from tracks, the player auto-generates colors using HSL hue cycling.
- **Single-variant tracks**: Set `variants: []` and the track just plays its `audio_path`.
- **Re-running stages**: Each stage is idempotent. Re-run `chak fuse` after editing the semantic matrix. Re-run `chak media-fetch` to regenerate images.
- **Config reference**: All pipeline thresholds are in `chak_pipeline.toml`.
- **Data contracts**: See `DATA_CONTRACTS.md` for the exact schema of all data files.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `chak align` fails | Check that audio files exist and GPU is available. Try `--config` to point to your TOML. |
| Images look wrong | Edit prompts in `semantic_matrix.json` and re-run `chak media-fetch` + `chak fuse` + `chak export`. |
| Player doesn't show new album | Run `chak index` to regenerate `albums_index.json`. |
| Track themes look off | Add explicit `theme` objects to `album_config.json`. |
| Variant files missing | Run `chak process-variants MY_ALBUM_002` or `chak export MY_ALBUM_002`. |
