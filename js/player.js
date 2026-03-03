// player.js
// Handles Audio, Syncing, and UI Updating

// Sanitize lyric for display: prevent huge blobs (hallucination/errors) from breaking layout.
const DISPLAY_MAX_WORDS = 60;
const DISPLAY_MAX_CHARS = 400;
function sanitizeLyricForDisplay(text) {
    if (!text || typeof text !== 'string') return '';
    const t = text.trim();
    if (t.length <= DISPLAY_MAX_CHARS) {
        const words = t.split(/\s+/);
        if (words.length <= DISPLAY_MAX_WORDS) return t;
        return words.slice(0, DISPLAY_MAX_WORDS).join(' ') + '\u2026';
    }
    return t.slice(0, DISPLAY_MAX_CHARS) + '\u2026';
}

const audio = document.getElementById('core-audio');
const btnPlay = document.getElementById('btn-play');
const btnNext = document.getElementById('btn-next');
const btnPrev = document.getElementById('btn-prev');
const progressBar = document.getElementById('progress-bar');
const progressContainer = document.getElementById('progress-container');

// Elements
const elPrev = document.getElementById('lyric-prev');
const elCurr = document.getElementById('lyric-curr');
const elNext = document.getElementById('lyric-next');
const elTrackName = document.getElementById('current-track-name');
const mediaLayerA = document.getElementById('media-layer-a');
const mediaLayerB = document.getElementById('media-layer-b');

let currentTrackIndex = 0;
let currentLyricIndex = -1;
let currentMediaIndex = -1;
let currentActiveMediaLayer = 'A';
let currentWordIndex = -1;
let lastTriggeredMedia = null;

// SEMANTIC MATRIX STATE
// masterMatrix is declared globally in matrix.js

async function initPlayer() {
    const entry = (typeof getAlbumEntryById === 'function' && currentAlbumId)
        ? getAlbumEntryById(currentAlbumId)
        : null;
    currentAlbumConfig = entry && entry.config ? entry.config : fallbackAlbumConfig;

    const elTitle = document.getElementById('album-title');
    const elSubtitle = document.getElementById('album-subtitle');
    if (elTitle) elTitle.innerText = currentAlbumConfig.title || '';
    if (elSubtitle) elSubtitle.innerText = currentAlbumConfig.description || '';

    await loadTrack(0);
}

async function loadTrack(index) {
    if (!currentAlbumConfig || !currentAlbumConfig.tracks || index >= currentAlbumConfig.tracks.length) return;
    currentTrackIndex = index;
    const trackMeta = currentAlbumConfig.tracks[index];
    if (!trackMeta) return;

    audio.src = `albums/${currentAlbumConfig.album_id}/${trackMeta.audioFile}`;
    if (elTrackName) elTrackName.innerText = trackMeta.title || '';

    // Default Media Fallback
    let initMediaStr = trackMeta.defaultMedia;

    // SEMANTIC MATRIX INJECTION
    if (typeof masterMatrix !== 'undefined' && masterMatrix && masterMatrix.narrative_phases) {
        const phase = masterMatrix.narrative_phases.find(p =>
            p && p.covers_tracks && p.covers_tracks.includes(trackMeta.id)
        );
        if (phase && phase.media_pool && phase.media_pool.length > 0) {
            initMediaStr = phase.media_pool[0].url;
        }
    }

    if (initMediaStr) {
        triggerMediaChange(`albums/${currentAlbumConfig.album_id}/media/${initMediaStr}`);
    }

    // Load the dynamic sync data
    await fetchTrackData(trackMeta.id);

    // Reset Timeline
    currentLyricIndex = -1;
    currentMediaIndex = -1;
    lastTriggeredMedia = null;

    const tl = loadedTrackData && loadedTrackData.timeline;
    if (elPrev) elPrev.innerText = "";
    if (elCurr) elCurr.innerHTML = (tl && tl.length > 0) ? "..." : (trackMeta.title || "");
    if (elNext) elNext.innerText = (tl && tl.length > 0) ? sanitizeLyricForDisplay(tl[0].lyric) : "";
}

function triggerMediaChange(mediaUrl) {
    if (!mediaUrl) return;
    if (currentActiveMediaLayer === 'A') {
        if (mediaLayerB) mediaLayerB.style.backgroundImage = `url('${mediaUrl}')`;
        if (mediaLayerB) mediaLayerB.classList.add('active');
        if (mediaLayerA) mediaLayerA.classList.remove('active');
        currentActiveMediaLayer = 'B';
    } else {
        if (mediaLayerA) mediaLayerA.style.backgroundImage = `url('${mediaUrl}')`;
        if (mediaLayerA) mediaLayerA.classList.add('active');
        if (mediaLayerB) mediaLayerB.classList.remove('active');
        currentActiveMediaLayer = 'A';
    }
}

// Playback Controls
function togglePlay() {
    if (audio.paused) {
        audio.play();
        if (btnPlay) btnPlay.innerText = "\u23F8";
    } else {
        audio.pause();
        if (btnPlay) btnPlay.innerText = "\u25B6";
    }
}
if (btnPlay) btnPlay.addEventListener('click', togglePlay);

if (btnNext) btnNext.addEventListener('click', () => {
    if (currentAlbumConfig && currentAlbumConfig.tracks && currentTrackIndex < currentAlbumConfig.tracks.length - 1) {
        loadTrack(currentTrackIndex + 1).then(() => audio.play());
    }
});

if (btnPrev) btnPrev.addEventListener('click', () => {
    if (audio.currentTime > 3) { audio.currentTime = 0; }
    else if (currentTrackIndex > 0) {
        loadTrack(currentTrackIndex - 1).then(() => audio.play());
    }
});

// CORE TIMELINE SYNC
audio.addEventListener('timeupdate', () => {
    // 1. Progress Bar
    if (progressBar && audio.duration) {
        progressBar.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
    }

    if (!loadedTrackData || !loadedTrackData.timeline || loadedTrackData.timeline.length === 0) return;

    const timeline = loadedTrackData.timeline;

    // 2. High-Fidelity Timeline Sync (Lyrics, Meaning, Media)
    // First pass: find entry where start <= currentTime < end (precise match)
    let newTimelineIdx = -1;
    for (let i = 0; i < timeline.length; i++) {
        const entry = timeline[i];
        if (audio.currentTime >= entry.start && audio.currentTime < entry.end) {
            newTimelineIdx = i;
        }
    }
    // Fallback: if no entry contains currentTime (gap), show last started entry
    if (newTimelineIdx === -1) {
        for (let i = 0; i < timeline.length; i++) {
            if (audio.currentTime >= timeline[i].start) {
                newTimelineIdx = i;
            }
        }
    }

    if (newTimelineIdx !== currentLyricIndex && newTimelineIdx !== -1) {
        currentLyricIndex = newTimelineIdx;
        currentWordIndex = -1;
        lastTriggeredMedia = null; // Reset so first image of new line always triggers
        const lineData = timeline[currentLyricIndex];

        if (elPrev) {
            elPrev.innerText = currentLyricIndex > 0
                ? sanitizeLyricForDisplay(timeline[currentLyricIndex - 1].lyric)
                : "";
        }
        if (elNext) {
            elNext.innerText = currentLyricIndex < timeline.length - 1
                ? sanitizeLyricForDisplay(timeline[currentLyricIndex + 1].lyric)
                : "";
        }

        // Initial render of the current line; word highlighting will refine this below.
        if (elCurr && lineData) {
            const baseLyric = sanitizeLyricForDisplay(lineData.lyric);
            const meaning = lineData.real_meaning || '';

            // Responsive font sizing based on lyric length
            elCurr.classList.remove('lyric-short', 'lyric-medium', 'lyric-long');
            if (baseLyric.length <= 40) {
                elCurr.classList.add('lyric-short');
            } else if (baseLyric.length <= 120) {
                elCurr.classList.add('lyric-medium');
            } else {
                elCurr.classList.add('lyric-long');
            }

            elCurr.innerHTML = meaning
                ? `${baseLyric}<span class="lyric-meaning">${meaning}</span>`
                : baseLyric;

            // Pop effect
            elCurr.style.transform = 'scale(1.05)';
            setTimeout(() => { if (elCurr) elCurr.style.transform = 'scale(1)'; }, 150);
        }
    }

    // Fine-grained per-word highlight using word-level timings, when available.
    if (currentLyricIndex !== -1 && currentLyricIndex < timeline.length) {
        const activeLine = timeline[currentLyricIndex];
        const words = (activeLine && activeLine.words) || [];
        if (words.length > 0) {
            let newWordIdx = currentWordIndex;
            for (let w = 0; w < words.length; w++) {
                if (audio.currentTime >= words[w].start) {
                    newWordIdx = w;
                }
            }

            if (newWordIdx !== currentWordIndex && newWordIdx !== -1) {
                currentWordIndex = newWordIdx;
                const parts = words.slice(0, DISPLAY_MAX_WORDS).map((w, idx) => {
                    const safe = String(w.text)
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;');
                    const isActive = idx === currentWordIndex;
                    return isActive
                        ? `<span class="word-active">${safe}</span>`
                        : `<span class="word-inactive">${safe}</span>`;
                });
                const suffix = words.length > DISPLAY_MAX_WORDS ? '\u2026' : '';
                const lyricHtml = parts.join(' ') + suffix;
                const meaning = activeLine.real_meaning || '';
                const meaningHtml = meaning
                    ? `<span class="lyric-meaning">${meaning}</span>`
                    : '';
                if (elCurr) elCurr.innerHTML = meaningHtml ? `${lyricHtml}${meaningHtml}` : lyricHtml;
            }
        }

        // Sub-Timeline for Multi-Media Sequences per line
        const mediaArr = activeLine && activeLine.media;
        if (mediaArr && mediaArr.length > 0) {
            const activeTime = audio.currentTime;
            let chosenMedia = mediaArr[0].url;

            for (let m = 0; m < mediaArr.length; m++) {
                if (!mediaArr[m]) continue;
                const triggerTime = activeLine.start + parseFloat(mediaArr[m].offset || 0);
                if (activeTime >= triggerTime) {
                    chosenMedia = mediaArr[m].url;
                }
            }

            if (chosenMedia && lastTriggeredMedia !== chosenMedia) {
                lastTriggeredMedia = chosenMedia;
                triggerMediaChange(`albums/${currentAlbumConfig.album_id}/${chosenMedia}`);
            }
        }
    }
});

audio.addEventListener('ended', () => {
    if (currentAlbumConfig && currentAlbumConfig.tracks && currentTrackIndex < currentAlbumConfig.tracks.length - 1) {
        loadTrack(currentTrackIndex + 1).then(() => audio.play());
    } else {
        if (btnPlay) btnPlay.innerText = "\u25B6";
        if (elCurr) elCurr.innerText = "Experience Complete.";
    }
});

if (progressContainer) {
    progressContainer.addEventListener('click', (e) => {
        if (!audio.duration) return;
        const clickPercent = e.offsetX / progressContainer.offsetWidth;
        audio.currentTime = clickPercent * audio.duration;
    });
}

// Init on load
document.addEventListener('DOMContentLoaded', () => {
    const albumSelector = document.getElementById('album-selector');

    if (albumSelector && typeof albumRegistry !== 'undefined' && Array.isArray(albumRegistry)) {
        albumRegistry.forEach((entry) => {
            const opt = document.createElement('option');
            opt.value = entry.album_id;
            opt.textContent = entry.title;
            if (entry.album_id === currentAlbumId) {
                opt.selected = true;
            }
            albumSelector.appendChild(opt);
        });

        albumSelector.addEventListener('change', (e) => {
            const selectedId = e.target.value;
            currentAlbumId = selectedId;
            const entry = typeof getAlbumEntryById === 'function'
                ? getAlbumEntryById(currentAlbumId)
                : null;
            if (entry && entry.config) {
                currentAlbumConfig = entry.config;
                const elTitle = document.getElementById('album-title');
                const elSubtitle = document.getElementById('album-subtitle');
                if (elTitle) elTitle.innerText = currentAlbumConfig.title || '';
                if (elSubtitle) elSubtitle.innerText = currentAlbumConfig.description || '';
                loadTrack(0);
            }
        });
    }

    initPlayer();
});
