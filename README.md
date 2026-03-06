# The Chak Chak Mage — Interactive Album

An interactive music experience with synced visuals, real-time lyrics, and hidden narratives. Nine tracks telling a prehistoric allegory with a modern parallel running beneath the surface.

**[Listen now](https://az-dev-me.github.io/chak-chak-mage/)**

---

## What is this?

A browser-based interactive album player. Each track features:

- **Karaoke-style lyrics** — words highlight in real time, synced to the music
- **Dual-layer visuals** — a literal story (prehistoric cave allegory) plays inside a phone frame, while a hidden modern narrative unfolds in surrounding panels
- **Beat-reactive UI** — interface elements pulse and respond to the music's energy
- **Structure-aware image pacing** — images change faster during intense sections, slower during calm passages
- **Meaning panel** — reveals the hidden modern interpretation of each line as it's sung

## How to listen

1. Open the [live site](https://az-dev-me.github.io/chak-chak-mage/)
2. Choose your language (English, Portuguese, or Brazilian Portuguese)
3. Click "Enter Experience"
4. Pick a track and press play — fullscreen recommended

Works on desktop and mobile. Best experienced with headphones.

## Running locally

```bash
# Serve from the project root
python -m http.server 8080
# or use the included batch file on Windows
serve.bat
```

Open `http://localhost:8080` in your browser.

## Architecture

Pure vanilla HTML/CSS/JS — no build step, no frameworks, no dependencies.

| Layer | Files | Role |
|-------|-------|------|
| Landing | `index.html` | Language selection, entry point |
| Player | `player.html` | Main orchestrator, audio sync, end screen |
| Zone 1 (Inner) | `js/zone1_inner.js` | Literal story images inside phone frame |
| Zone 2 (Outer) | `js/zone2_outer.js` | Hidden narrative panels, gallery, meaning text |
| Zone 3 (Ambient) | `js/zone3_ambient.js` | Fullscreen blurred background |
| Timing | `js/timing_engine.js` | Beat detection, sync tick loop |
| Data | `albums/MY_ALBUM_001/data/` | Per-track JS with lyrics, timestamps, images, semantics |

## Credits

This project was built by a human and an AI, using tools made by many.

| Role | Tool |
|------|------|
| Music generation | [DeeVid](https://deevid.ai) |
| Lyrics | [DeepSeek](https://deepseek.com) |
| Image generation | SDXL-Turbo (local GPU) |
| Code + architecture | [Claude](https://claude.ai) (Anthropic) via [Cursor](https://cursor.com) |
| Semantic matrix | [Antigravity](https://antigravity.google/) + Gemini 3.1 |
| Semantic prompts | [Mistral](https://mistral.ai) via Ollama |
| Audio alignment | [stable-ts](https://github.com/jianfch/stable-ts) + [Whisper](https://github.com/openai/whisper) |
| Vocal isolation | [Demucs](https://github.com/facebookresearch/demucs) |
| Musical analysis | [librosa](https://librosa.org) |

## License

[MIT](LICENSE) — Copyright 2026 AZ
