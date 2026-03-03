### Overview

This document defines the **stable data contracts** used by the Interactive Album Engine and Choice Kit pipeline.

- **Album config**: what an album is and which audio files it uses.
- **Catalog mapping**: how catalog variants map to concrete MP3 files.
- **Track data**: what each `track_0X_data` / `<variant_id>_data` object looks like.
- **Media manifest**: how visual concepts map to concrete image files.

If you change any of these shapes, **update this file and the relevant scripts together**.

---

### 1. Album config (`album_config.json`)

Album configs define a single buildable album, usually stored in `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/albums/<ALBUM_ID>/album_config.json`.

- **Required top-level fields**
  - **`album_id`**: string, e.g. `"ALBUM_CUSTOM_001"`.
  - **`title`**: human-readable album title.
  - **`artist`**: display name for the artist/curator.
  - **`description`**: short description of how/why this album was built.
  - **`source`**: where the audio comes from, e.g. `"THE_CHAK_CHAK_MAGE_CHOICE_KIT"`.
  - **`tracks`**: ordered array of track slots (see below).

- **Track entry (`tracks[]`)**
  - **`slot`**: 1–9, the position in the album.
  - **`track_id`**: logical track id, e.g. `"track_01"`.
  - **`variant_id`**: variant id from the catalog, e.g. `"Track_01_VariantA"`.
  - **`audio_path`**: repo-relative path to the chosen MP3 inside the Choice Kit.

Example:

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

`pipeline/build_album_from_catalog.py` (see pipeline docs) will consume this file to materialize a playable album folder under `albums/<ALBUM_ID>/`.

---

### 2. Catalog mapping (`catalog_mapping.json`)

The catalog mapping describes **which catalog variants exist** and **where their audio files live** in the Choice Kit. It is used by:

- `catalog_aligner.py`
- `build_catalog_timelines.py`

**Shape**

- **Top-level**
  - **`tracks`**: array of entries, one per catalog variant you want to align.

- **Track mapping entry (`tracks[]`)**
  - **`track_id`**: logical track id (`"track_01"` … `"track_09"`).
  - **`variant_id`**: catalog variant id (also used in filenames and JS variable names), e.g. `"Track_01_VariantA"`.
  - **`audio_path`**: repo-relative path to the MP3 file inside `THE_CHAK_CHAK_MAGE_CHOICE_KIT`.

Current example:

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

**Contract notes**

- `catalog_aligner.py` and `build_catalog_timelines.py` both expect this exact structure:
  - Top-level `tracks` array.
  - Each entry has `track_id`, `variant_id`, `audio_path`.
- You may add additional top-level fields (e.g. `"version"`) if needed, but **do not rename or remove** the existing ones without updating those scripts.

---

### 3. Track data (`track_0X.js` and catalog variant JS)

Track data files are **browser-ready** JavaScript objects that power the visual album player.

- Album tracks live at:
  - `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/albums/<ALBUM_ID>/data/track_0X.js`
  - Each defines a global variable, e.g. `track_01_data`.
- Catalog variant tracks live at:
  - `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/THE_CHAK_CHAK_MAGE_CHOICE_KIT/data/<variant_id>.js`
  - Each defines `<variant_id>_data`.

**Top-level TrackData object**

- **`id`**: string, e.g. `"track_01"` or `"Track_01_VariantA"`.
- **`timeline`**: array of timeline entries (lyric or instrumental segments), ordered by time.

**Timeline entry (`timeline[]`)**

- **`id`**: string identifier, e.g. `"line_4_occ_0"` or `"instrumental_0"`.
- **`line_index`**: integer index into the canonical lyric lines for this track, or `null` for instrumental/ambient segments.
- **`occurrence_index`**: 0-based occurrence count for this `line_index`.
- **`start`**: float, seconds from track start.
- **`end`**: float, seconds from track start.
- **`lyric`**: canonical lyric line text (or raw segment text for instrumentals).
- **`real_meaning`**: human-readable “deep meaning” for this segment.
- **`media`**: array of media slots for this segment (see below).
- **`words`**: array of word-level timing entries for karaoke highlighting.

**Word entry (`words[]`)**

- **`start`**: float, word start time in seconds.
- **`end`**: float, word end time in seconds.
- **`text`**: the word itself.

**Media entry (`media[]`)**

- **`offset`**: float, seconds from the **segment start** when this media should become active.
- **`url`**: string path to the image file (relative to the album folder), e.g. `"media/t1_l0_o0_m0.jpg"`.
- **`query`**: the text prompt / concept used to generate this image.

Contract note:

- The engine treats `media[]` entries as **optional**. If the array is empty for a segment, the player falls back to phase or track-level backgrounds.
- Future iterations may add an optional **`concept_id`** field to `media[]` entries, tying them directly to `media_manifest.json` entries. When that happens, both this document and the generation scripts will be updated in lockstep.

---

### 4. Media manifest (`media_manifest.json`)

The media manifest is the **single source of truth** for which visual concepts exist and which image file (if any) has been fetched for each.

- Location (current Gemini album):
  - `THE_CHAK_CHAK_MAGE_INTERACTIVE_ALBUM/albums/GEMINI_3.1_PRO_HIGH/media_manifest.json`
- Created and updated by:
  - `media_prepare_manifest.py`
  - `media_fetcher.py`

**Shape**

- **Top-level**
  - **`concepts`**: object/dictionary keyed by **query string**, not by filename.

- **Concept entry (`concepts[query]`)**
  - **`filename`**: string, e.g. `"c0000.jpg"`, relative to the album’s `media/` folder.
  - **`status`**: string, one of:
    - `"pending"`: concept discovered, image not yet fetched.
    - `"ok"`: image successfully fetched and written to disk.
    - `"failed"`: fetching failed after retries; this concept should not be wired into `media[]` URLs.

Example:

```json
{
  "concepts": {
    "vintage green British phone booth glowing at night, cinematic neon": {
      "filename": "c0000.jpg",
      "status": "ok"
    },
    "wide, ominous valley at dawn, cinematic": {
      "filename": "c0001.jpg",
      "status": "pending"
    }
  }
}
```

**Contract notes**

- For now, the **query string itself is the concept key**. Scripts treat it as the unique identifier.
- Only concepts with `status == "ok"` should ultimately be used to populate `media[].url` fields in track data, to avoid broken image URLs.
- Future revisions may introduce a separate `concept_id` distinct from the raw query; when that happens, this document and both media scripts must be updated together.

