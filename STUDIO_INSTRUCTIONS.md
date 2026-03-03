### THE CHAK CHAK MAGE – Interactive Studio Instructions

This is the **authoritative guide** for turning catalog MP3s into a fully built interactive album with:

- **Word-level karaoke** (Whisper alignments).
- **Canonical semantics** (real meanings and visual prompts).
- **Manifest-based visuals** (no broken image URLs).

The older text file (`STUDIO_INSTRUCTIONS.txt`) is kept for historical reference, but this markdown file is the one to follow.

---

### 1. Define or update an album config

Albums are described by `album_config.json` files, usually under:

- `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/albums/<ALBUM_ID>/album_config.json`

Each config defines:

- **Album identity**
  - `album_id`: e.g. `"GEMINI_3.1_PRO_HIGH"` or `"ALBUM_CUSTOM_001"`.
  - `title`, `artist`, `description`.
  - `source`: usually `"THE_CHAK_CHAK_MAGE_CHOICE_KIT"` for catalog-based albums.
- **Track choices**
  - `tracks[]`: 1–9 entries, one per slot.
  - For each track:
    - `slot`: 1–9.
    - `track_id`: `"track_01"` … `"track_09"`.
    - `variant_id`: e.g. `"Track_01_VariantA"`.
    - `audio_path`: repo-relative path to the chosen MP3 in the Choice Kit.

Example (simplified):

```json
{
  "album_id": "ALBUM_CUSTOM_001",
  "title": "The Chak Chak Mage – Your Cut",
  "artist": "You + AI",
  "description": "Curated from the Choice Kit.",
  "source": "THE_CHAK_CHAK_MAGE_CHOICE_KIT",
  "tracks": [
    {
      "slot": 1,
      "track_id": "track_01",
      "variant_id": "Track_01_VariantA",
      "audio_path": "THE_CHAK_CHAK_MAGE_CHOICE_KIT/Track_01_Prologue_The_Green_Booth/Track_01_Prologue_The_Green_Booth - Version A.mp3"
    }
  ]
}
```

There is already a backfilled config for the Gemini album at:

- `albums/GEMINI_3.1_PRO_HIGH/album_config.json`

You can copy and modify this as a starting point for your own albums.

---

### If things are broken (wrong tracks, lyric blobs, UI scroll)

The pipeline was updated to reduce Whisper hallucination and cap on-screen lyric length. If you still see wrong tracks or garbage lyrics:

1. **Re-run catalog from RAW (clean)**  
   From `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/`:
   - Clear Choice Kit alignment and track folders (see pipeline scripts under `pipeline/`: `raw_catalog_classify.py --clear_tracks`, and delete `THE_CHAK_CHAK_MAGE_CHOICE_KIT/RAW/alignment/*` and contents of each `TRACK_*` folder if you want a full reset).
   - Re-align all RAW: `python pipeline/raw_catalog_aligner.py` (from studio root; uses `THE_CHAK_CHAK_MAGE_CHOICE_KIT/RAW`).
   - Re-classify: `python pipeline/raw_catalog_classify.py --clear_tracks` (writes `catalog_mapping.json` and copies MP3s into `TRACK_*`).
2. **Rebuild the album**  
   Create or edit `albums/<ALBUM_ID>/album_config.json` with one variant per track from the new `catalog_mapping.json`, then run the full build (see §2).
3. **Regenerate index**  
   `python studio_pipeline.py generate-index`.

---

### 2. Build / refresh an album from the catalog

From `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/`, run:

```bash
python pipeline/build_album_from_catalog.py --album_config albums/GEMINI_3.1_PRO_HIGH/album_config.json
```

Or for a custom album:

```bash
python pipeline/build_album_from_catalog.py --album_config albums/ALBUM_CUSTOM_001/album_config.json
```

What this does for `<ALBUM_ID>`:

1. **Materialize audio & metadata**
   - Creates `albums/<ALBUM_ID>/` if it does not exist.
   - Copies MP3s from the Choice Kit (`audio_path`) into:
     - `albums/<ALBUM_ID>/01 - track_01.mp3`, `02 - track_02.mp3`, etc.
   - Writes:
     - `albums/<ALBUM_ID>/00_ALBUM.m3u` (playlist).
     - `albums/<ALBUM_ID>/album_metadata.json` (resolved track list).
   - Ensures `data/` and `media/` subfolders exist.
   - Copies canonical `semantic_matrix.json` (and `master_matrix.json` when present) from the Gemini album so all albums share the same story semantics.

2. **Alignment (word-level timestamps)**
   - Calls:

```bash
python pipeline/auto_aligner.py --album_dir albums/<ALBUM_ID>
```

   - Produces:
     - `albums/alignment/track_0X_words.json` for each audio track.

3. **Timelines (canonical lines → aligned segments)**
   - Calls:

```bash
python pipeline/build_timelines.py --album_dir albums/<ALBUM_ID>
```

   - Produces:
     - `albums/<ALBUM_ID>/data/track_0X.timeline.json`
   - Each entry encodes `start`, `end`, `line_index`, `occurrence_index`, `lyric`.

4. **Visual manifest & fetching (concepts → images)**
   - Calls:

```bash
python pipeline/media_prepare_manifest.py --album_dir albums/<ALBUM_ID>
python pipeline/media_fetcher.py --album_dir albums/<ALBUM_ID>
```

   - `media_prepare_manifest.py` scans:
     - `albums/<ALBUM_ID>/semantic_matrix.json`
     - `track_visuals.json` at project root
   - Writes:
     - `albums/<ALBUM_ID>/media_manifest.json`:
       - `concepts[query] = { "filename": "c0000.jpg", "status": "pending"|"ok"|"failed" }`
   - `media_fetcher.py`:
     - Downloads images via DuckDuckGo (`ddgs`) into `albums/<ALBUM_ID>/media/<filename>`.
     - Updates `status` to `"ok"` or `"failed"`.

5. **Fusion (timelines + semantics + words + manifest → track JS)**
   - Calls:

```bash
node pipeline/build_album_timeline.js --album_dir albums/<ALBUM_ID>
```

   - For each `track_0X` it produces:
     - `albums/<ALBUM_ID>/data/track_0X.js` containing `var track_0X_data = { ... }`.
   - Each timeline entry includes:
     - `start`, `end`, `lyric`, `real_meaning`.
     - `words[]` for word-level karaoke.
     - `media[]` entries with `{ offset, url, query }`:
       - **Only concepts with `status == "ok"` in `media_manifest.json` receive a `url`.**
       - Failed/pending concepts are skipped, so there are **no broken image URLs**.

If you want to stage audio and metadata without running heavy AI steps yet, pass `--skip_heavy`:

```bash
python pipeline/build_album_from_catalog.py --album_config albums/ALBUM_CUSTOM_001/album_config.json --skip_heavy
```

You can then run individual steps manually as needed.

---

### 3. Catalog alignment & timelines (Choice Kit side)

The Choice Kit remains a **pure input catalog**:

- All candidate MP3s live under `THE_CHAK_CHAK_MAGE_CHOICE_KIT/Track_0X_*`.
- `catalog_mapping.json` maps logical variants to those MP3s:

```json
{
  "tracks": [
    {
      "track_id": "track_01",
      "variant_id": "Track_01_VariantA",
      "audio_path": "THE_CHAK_CHAK_MAGE_CHOICE_KIT/Track_01_Prologue_The_Green_Booth/REPLACE_ME_WITH_MP3_FILENAME.mp3"
    }
  ]
}
```

To align catalog variants:

```bash
python pipeline/catalog_aligner.py --mapping catalog_mapping.json
```

This writes:

- `THE_CHAK_CHAK_MAGE_CHOICE_KIT/alignment/<variant_id>_words.json`

To build catalog timelines (using the Gemini semantics as a reference):

```bash
python pipeline/build_catalog_timelines.py --mapping catalog_mapping.json --album_dir albums/GEMINI_3.1_PRO_HIGH
```

This writes:

- `THE_CHAK_CHAK_MAGE_CHOICE_KIT/data/<variant_id>.timeline.json`

Later, `build_catalog_timeline.js` can fuse those into player-ready variant JS:

```bash
node pipeline/build_catalog_timeline.js --mapping catalog_mapping.json --album_dir albums/GEMINI_3.1_PRO_HIGH
```

Result:

- `THE_CHAK_CHAK_MAGE_CHOICE_KIT/data/<variant_id>.js` defining `<variant_id>_data`.

---

### 4. Front-end: albums, catalog mode, and selection

The main UI is `index.html` in `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/`.

- Data loading:
  - `albums/GEMINI_3.1_PRO_HIGH/matrix.js` defines `masterMatrix` (narrative phases and semantics).
  - `albums/GEMINI_3.1_PRO_HIGH/data/track_0X.js` define `track_0X_data` objects.
  - For other albums, you will typically:
    - Add additional `<script>` tags for `albums/<ALBUM_ID>/data/track_0X.js`, or
    - Inject them dynamically in a future enhancement.

- JS engine:
  - `js/data_schema.js`
    - Defines:
      - `fallbackAlbumConfig` (Gemini album).
      - `catalogConfig` (Choice Kit variants).
      - `albumRegistry` (list of available albums; currently seeded with Gemini).
      - `currentAlbumId`, `currentAlbumConfig`, and `fetchTrackData(...)`.
  - `js/player.js`
    - Handles playback, per-line + per-word sync, and background image transitions.
    - Uses `currentAlbumConfig` and `currentMode` (`"album"` vs `"catalog"`).
    - Reads `timeline[]`, `words[]`, and `media[]` from the track data objects.
  - `js/editor.js`
    - Optional manual sync tool for quick experiments (spacebar tapping).

**Album selection UI**

- In the header:
  - `<select id="album-selector">` lists albums from `albumRegistry`.
  - A **mode toggle** button switches between:
    - **Album mode**: uses `currentAlbumId` + `albumRegistry` (e.g., Gemini, future custom albums).
    - **Catalog mode**: uses `catalogConfig` (Choice Kit variants).
- When you add a new album:
  1. Run `pipeline/build_album_from_catalog.py` so `albums/<ALBUM_ID>/data/track_0X.js` exists.
  2. Add an entry to `albumRegistry` in `js/data_schema.js` with matching `album_id`.
  3. Optionally add `<script>` tags in `index.html` for the new album’s `track_0X.js` files.

---

### 5. Legacy scripts and data

The following are **legacy prototypes** and should not be used in the new pipeline:

- `extract_transcripts.py`
- `apply_semantics_to_timings.js`
- `sync_aligner.py`
- `build_track_02.js`
- `fetch_t02.py`
- `raw_transcripts/track_0X_raw.json`

They are documented in:

- `legacy/README_LEGACY.md`

All new work should go through:

- `pipeline/build_album_from_catalog.py`
- `pipeline/auto_aligner.py` / `pipeline/catalog_aligner.py`
- `pipeline/build_timelines.py` / `pipeline/build_catalog_timelines.py`
- `semantic_matrix.json` + `track_visuals.json`
- `pipeline/build_album_timeline.js` / `pipeline/build_catalog_timeline.js`
- `pipeline/media_prepare_manifest.py` + `pipeline/media_fetcher.py`

---

### 6. Quick checklist: build a new album from the Choice Kit

1. **Pick variants** in the Choice Kit (by listening to the `Track_0X_*` folders).
2. **Update** `catalog_mapping.json` so each `audio_path` points to the chosen MP3.
3. **Create** `albums/ALBUM_CUSTOM_001/album_config.json` with:
   - `album_id`, `title`, `artist`, `description`, `source`, and `tracks[]` referencing your chosen `variant_id` and `audio_path`.
4. From `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/`, run:

```bash
python pipeline/build_album_from_catalog.py --album_config albums/ALBUM_CUSTOM_001/album_config.json
```

5. Open `index.html` in a browser:
   - Use the **album selector** and **mode toggle** to explore the experience.
6. (Optional) Add the new album to `albumRegistry` and script tags so it appears in the UI without further changes.

---

### 7. Active pipeline files vs. legacy / archive

To keep things manageable, here is the **authoritative list of files that are part of the current pipeline**. Everything else can be treated as legacy or support code.

#### 7.1 Core engine (you rarely need to edit these)

- **Front-end**
  - `index.html` – main UI shell.
  - `css/style.css` – visual styling.
  - `js/player.js` – audio playback, per-word highlighting, background transitions.
  - `js/data_schema.js` – album config wiring + dynamic track loading.
  - `shared/semantics/master_matrix.js` – `masterMatrix` phases for the story.
- **Shared semantics**
  - `shared/semantics/base_semantic_matrix.json` – canonical story + meanings + prompts for all tracks.
  - `semantic_overrides.json` – optional hand-tuned tweaks for specific lines.
  - `track_visuals.json` – per-track intro/outro visual prompts.

#### 7.2 Album build pipeline (CLI tools)

All commands are run from `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/`.

- **High-level orchestrator**
  - `studio_pipeline.py`
    - `build-from-catalog` – take a Choice Kit selection → `album_config.json` → build album folder.
    - `rebuild-album --album_id <ALBUM_ID>` – run the full pipeline (align → timelines → manifest → fetch → fuse) for one album.
    - `rebuild-all` – rebuilds every album that has an `album_config.json`.
- **Album materialization from catalog**
  - `pipeline/choicekit_to_album_config.py` – converts `selected_album.json` + `catalog_mapping.json` → `albums/<ALBUM_ID>/album_config.json`.
  - `pipeline/build_album_from_catalog.py` – copies MP3s, writes playlist + metadata, then (optionally) calls the heavy steps.
- **Pipeline phases**
  - Alignment:
    - `pipeline/auto_aligner.py` – MP3 → `albums/alignment/track_0X_words.json` (word timings).
  - Timelines:
    - `pipeline/build_timelines.py` – word timings + shared semantics → `albums/<ALBUM_ID>/data/track_0X.timeline.json`.
  - Visual manifest:
    - `pipeline/media_prepare_manifest.py` – scans `base_semantic_matrix.json` + `track_visuals.json` and builds `media_manifest.json`.
  - Image fetching:
    - `pipeline/media_fetcher.py` – fills `albums/<ALBUM_ID>/media/*.jpg` using a no-key provider (Bing HTML), with:
      - `MEDIA_REQUEST_DELAY` and `MEDIA_MAX_REQUESTS` to throttle requests.
      - `status: "ok" | "failed"` in `media_manifest.json`.
  - Fusion:
    - `pipeline/build_album_timeline.js` – merges timelines + semantics + word timings + manifest → `albums/<ALBUM_ID>/data/track_0X.js`.
      - Only uses images with `status:"ok"`, and reuses the nearest ok concept when a query has no image.

#### 7.3 Catalog (Choice Kit) support

- `THE_CHAK_CHAK_MAGE_CHOICE_KIT/` – audio only + helper files.
- `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/catalog_mapping.json` – maps logical variants to Choice Kit MP3 paths.
- (Optional) `pipeline/catalog_aligner.py`, `pipeline/build_catalog_timelines.py`, `pipeline/build_catalog_timeline.js` – used only if you want to prebuild per-variant catalog timelines; not required for the main album engine.

#### 7.4 Legacy / archived code

These files are **kept for historical reference** and are not part of the current pipeline. You can safely ignore them when working on the studio:

- `legacy/` folder and its contents (see `legacy/README_LEGACY.md`).
- Old one-off scripts that have been superseded by the `pipeline/` versions or by `studio_pipeline.py`.
- Anything under `raw_transcripts/` that isn’t referenced in the steps above.

When in doubt:

- If a file is **mentioned by name in sections 1–7 above**, it’s part of the active system.
- If it only lives under `legacy/` or is not referenced here, treat it as archive. You do **not** need to touch it to build or refresh albums.

