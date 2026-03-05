### THE CHAK CHAK MAGE – Interactive Studio Instructions

This is the **authoritative guide** for turning catalog MP3s into a fully built interactive album with:

- **Word-level karaoke** (stable-ts force-aligned + Demucs vocal isolation).
- **Canonical semantics** (dual-layer narrative: literal story + modern parallel).
- **Manifest-based visuals** (SDXL-Turbo generated, no broken image URLs).
- **Musical structure analysis** (librosa intensity curves, beat-aware image pacing).

---

### 1. Album config

Albums are described by `album_config.json` files under:

- `albums/<ALBUM_ID>/album_config.json`

Each config defines:

- **Album identity**: `album_id`, `title`, `artist`, `description`, `source`.
- **Track choices**: `tracks[]` — one per slot (1–9), with:
  - `slot`: 1–9.
  - `track_id`: `"track_01"` … `"track_09"`.
  - `variant_id`: the default variant (e.g. `"T1-2-3a"`).
  - `audio_path`: filename of the chosen MP3.
  - `variants[]`: all available variants for this track.

Example:

```json
{
  "album_id": "MY_ALBUM_001",
  "title": "The Chak Chak Mage",
  "tracks": [
    {
      "slot": 1,
      "track_id": "track_01",
      "variant_id": "T1-2-3a",
      "audio_path": "T1-2-3a.mp3",
      "variants": [
        { "id": "T1-2-3a", "label": "Medley A", "audio": "T1-2-3a.mp3" },
        { "id": "T1-2-3b", "label": "Medley B", "audio": "T1-2-3b.mp3" }
      ]
    }
  ]
}
```

---

### 2. Pipeline CLI (`chak`)

All commands run from `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/`. The CLI entry point is `chak` (installed via pip from `src/chak/`).

#### Full build (base tracks)

```bash
chak build MY_ALBUM_001
```

Runs: align → timeline → structure → manifest → fetch-media → fuse → export.

#### Process all non-default variants

```bash
chak process-variants MY_ALBUM_001
```

Runs the full pipeline for each variant that isn't the default.

#### Individual stages

| Command                        | What it does                                                    |
| ------------------------------ | --------------------------------------------------------------- |
| `chak align MY_ALBUM_001`      | stable-ts force-alignment + Demucs vocal isolation              |
| `chak timeline MY_ALBUM_001`   | Canonical lines → aligned timeline segments                     |
| `chak structure MY_ALBUM_001`  | librosa musical structure analysis (sections, beats, energy)    |
| `chak manifest MY_ALBUM_001`   | Build media manifest from semantic matrix                       |
| `chak fetch-media MY_ALBUM_001`| Generate images via SDXL-Turbo (local GPU)                      |
| `chak fuse MY_ALBUM_001`       | Merge timelines + semantics + alignment + manifest → fused data |
| `chak export MY_ALBUM_001`     | Write `.js` + `.json` player files + `albums_index.js`          |

#### Catalog commands

| Command                        | What it does                                            |
| ------------------------------ | ------------------------------------------------------- |
| `chak catalog extract <zips>`  | Extract MP3s from archive zips into Choice Kit          |
| `chak catalog align-raw`       | Align all RAW MP3s with Whisper for classification      |
| `chak catalog classify`        | Classify aligned RAW files into per-track folders       |
| `chak catalog build`           | Build an album from the Choice Kit classification       |

---

### 3. Pipeline stages in detail

#### 3.1 Alignment (`chak align`)

- **Engine**: stable-ts 2.19.1 with Demucs 4.0.1 vocal isolation.
- **Two-pass strategy**:
  1. `model.align()` — force-aligns canonical lyrics to audio.
  2. `model.transcribe()` — free transcription to discover ad-libs.
  3. Merge: canonical = ground truth, transcribed gaps = ad-libs.
- **Output**: `albums/<ALBUM_ID>/alignment/track_XX.alignment.json`

#### 3.2 Timeline (`chak timeline`)

- Matches canonical lyric lines to aligned segments using text similarity.
- Two-pass: standard threshold (0.45) + aggregate unmatched (0.25 for music tracks).
- **Output**: `albums/<ALBUM_ID>/data/track_XX.timeline.json`

#### 3.3 Structure (`chak structure`)

- Computes RMS energy, spectral flux/contrast, beat density via librosa.
- Composite intensity: 35% RMS + 30% onset + 20% contrast + 15% beat density.
- **Output**: `albums/<ALBUM_ID>/data/track_XX.structure.json`

#### 3.4 Manifest & media fetch (`chak manifest` + `chak fetch-media`)

- Scans `semantic_matrix.json` for all `media_queries` and `hidden_media_queries`.
- Maps each query to `concepts[query] = { filename, status }` in `media_manifest.json`.
- Generates images via SDXL-Turbo on local GPU (~0.7s/image).
- **Output**: `albums/<ALBUM_ID>/media_manifest.json` + `media/*.jpg`

#### 3.5 Fusion (`chak fuse`)

- **LYRICS-DRIVEN**: iterates ALL canonical lines, guaranteeing every lyric appears.
- `build_media_array()` uses musical structure for emotionally intelligent pacing:
  - High energy → rapid cycling (1.5s hold), Low energy → images breathe (15s hold).
  - Images snapped to nearest beat timestamps.
  - Short lines (2-3s) hold a single establishing image.
- Lines without Whisper matches get interpolated timing + synthetic words.

#### 3.6 Export (`chak export`)

- Writes `track_XX.js` and `track_XX.json` per track.
- For default variants, also writes variant-qualified copies (e.g. `track_01_T1-2-3a.js`).
- Generates `js/albums_index.js` (browser-loadable album registry).

---

### 4. Semantic data

- **Source of truth**: `shared/semantics/base_semantic_matrix.json`
  - 169 lines across 9 tracks.
  - Each line: `lyric`, `real_meaning`, 3 `media_queries` (literal), 3 `hidden_media_queries` (modern parallel).
  - Total: 507 literal + 507 hidden = 1014 unique image prompts.
- **Per-album copy**: `albums/<ALBUM_ID>/semantic_matrix.json` (merged during build).
- **Overrides**: `semantic_overrides.json` (optional per-line tweaks).
- **Narrative phases**: `shared/semantics/master_matrix.js` (8 phases mapping tracks to dual-layer story).

#### Dual narrative layers

- **Literal** (`media_queries` → Zone 1 phone frame): prehistoric allegory (cavemen, fire, Gralha, Muda).
- **Hidden** (`hidden_media_queries` → Zone 2/3 ambient): modern parallel (tech worship, hustle, polarization, open source).

---

### 5. Frontend architecture (3-Zone)

- **Zone 1** (phone frame 9:16): literal story images, A/B crossfade inside `#phone-frame`.
- **Zone 2** (outer panels): hidden narrative — side panels, meaning text.
- **Zone 3** (ambient): blurred/dimmed hidden narrative as fullscreen background.

Key files:

| File                   | Purpose                                          |
| ---------------------- | ------------------------------------------------ |
| `index.html`           | Main UI shell                                    |
| `css/style.css`        | Visual styling, beat-reactive CSS variables      |
| `js/player.js`         | Audio playback, sync loop, zone orchestration    |
| `js/data_schema.js`    | Album config wiring, dynamic track loading       |
| `js/timing_engine.js`  | Timeline binary search, active line resolution   |
| `js/zone1_inner.js`    | Phone frame A/B crossfade                        |
| `js/zone2_outer.js`    | Side panels, meaning text                        |
| `js/zone3_ambient.js`  | Ambient background layer                         |
| `js/audio_analyser.js` | Real-time beat detection via captureStream       |
| `js/albums_index.js`   | Auto-generated album registry                    |

#### Running locally

Use the included HTTP server to avoid CORS issues with `file://`:

```bash
serve.bat
# or: python -m http.server 8080
```

Then open `http://localhost:8080` in your browser.

---

### 6. Quick checklist: build a new album

1. **Pick variants** from the Choice Kit by listening to `THE_CHAK_CHAK_MAGE_CHOICE_KIT/` tracks.
2. **Create** `albums/<ALBUM_ID>/album_config.json` with your chosen variants.
3. **Build**:

   ```bash
   chak build <ALBUM_ID>
   chak process-variants <ALBUM_ID>
   ```

4. **Open** `http://localhost:8080` (run `serve.bat` first).
5. Use the album selector dropdown to switch between albums.

---

### 7. Configuration

All pipeline thresholds, model parameters, and provider settings are in:

- `chak_pipeline.toml`

Key settings: similarity thresholds, Whisper model, GPU device, image generation parameters.

---

### 8. Testing

```bash
python -m pytest tests/ -q
```

111 tests covering text matching, similarity scoring, schema validation, timeline building, and fusion logic.
