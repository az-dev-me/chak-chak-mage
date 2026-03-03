// player.js
// Handles Audio, Syncing, and UI Updating
// v2: rAF-based sync, progressive karaoke, energy-responsive effects

// ── Constants ────────────────────────────────────────────
const DISPLAY_MAX_WORDS = 60;
const DISPLAY_MAX_CHARS = 400;

// Per-track color themes (mood-derived)
const TRACK_THEMES = {
    track_01: { accent: '#66cccc', glow: 'rgba(102,204,204,0.6)' }, // Teal — mysterious/narration
    track_02: { accent: '#ff8844', glow: 'rgba(255,136,68,0.6)' },  // Orange — the orange box!
    track_03: { accent: '#ff4444', glow: 'rgba(255,68,68,0.6)' },   // Red — fire run, urgency
    track_04: { accent: '#ffaa00', glow: 'rgba(255,170,0,0.6)' },   // Gold — rules, tradition
    track_05: { accent: '#ff77aa', glow: 'rgba(255,119,170,0.6)' }, // Pink — Muda, warmth
    track_06: { accent: '#aa66ff', glow: 'rgba(170,102,255,0.6)' }, // Purple — conflict/duality
    track_07: { accent: '#4488ff', glow: 'rgba(68,136,255,0.6)' },  // Blue — empty/bittersweet
    track_08: { accent: '#ffcc33', glow: 'rgba(255,204,51,0.6)' },  // Warm gold — finale
    track_09: { accent: '#66cccc', glow: 'rgba(102,204,204,0.6)' }, // Teal — epilogue mirror
};

// ── Utility ──────────────────────────────────────────────
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

function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatTime(seconds) {
    if (!seconds || !isFinite(seconds)) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
}

// ── DOM Elements ─────────────────────────────────────────
const audio = document.getElementById('core-audio');
const btnPlay = document.getElementById('btn-play');
const btnNext = document.getElementById('btn-next');
const btnPrev = document.getElementById('btn-prev');
const progressBar = document.getElementById('progress-bar');
const progressContainer = document.getElementById('progress-container');
const elPrev = document.getElementById('lyric-prev');
const elCurr = document.getElementById('lyric-curr');
const elNext = document.getElementById('lyric-next');
const elTrackName = document.getElementById('current-track-name');
const mediaLayerA = document.getElementById('media-layer-a');
const mediaLayerB = document.getElementById('media-layer-b');
const meaningPanel = document.getElementById('meaning-panel');
const meaningText = document.getElementById('meaning-text');
const trackListNav = document.getElementById('track-list');
const vignetteOverlay = document.getElementById('vignette-overlay');
const timeCurrent = document.getElementById('time-current');
const timeTotal = document.getElementById('time-total');

// ── State ────────────────────────────────────────────────
let currentTrackIndex = 0;
let currentLyricIndex = -1;
let currentMediaIndex = -1;
let currentActiveMediaLayer = 'A';
let currentWordIndex = -1;
let lastTriggeredMedia = null;
let rafId = null;
let wordSpansBuilt = false;
let wordSpans = [];
let lastEnergyCheck = 0;

// Image preload cache
const preloadedImages = new Set();

// ── Init ─────────────────────────────────────────────────
async function initPlayer() {
    const entry = (typeof getAlbumEntryById === 'function' && currentAlbumId)
        ? getAlbumEntryById(currentAlbumId)
        : null;
    currentAlbumConfig = entry && entry.config ? entry.config : fallbackAlbumConfig;

    const elTitle = document.getElementById('album-title');
    const elSubtitle = document.getElementById('album-subtitle');
    if (elTitle) elTitle.innerText = currentAlbumConfig.title || '';
    if (elSubtitle) elSubtitle.innerText = currentAlbumConfig.description || '';

    buildTrackList();
    await loadTrack(0);
}

// ── Track List Nav ───────────────────────────────────────
function buildTrackList() {
    if (!trackListNav || !currentAlbumConfig || !currentAlbumConfig.tracks) return;
    trackListNav.innerHTML = '';
    currentAlbumConfig.tracks.forEach((t, i) => {
        const pill = document.createElement('button');
        pill.className = 'track-pill' + (i === currentTrackIndex ? ' active' : '');
        pill.textContent = t.title || `Track ${i + 1}`;
        pill.addEventListener('click', () => {
            loadTrack(i).then(() => { audio.play(); startSyncLoop(); });
        });
        trackListNav.appendChild(pill);
    });
}

function updateTrackPills() {
    if (!trackListNav) return;
    const pills = trackListNav.querySelectorAll('.track-pill');
    pills.forEach((p, i) => {
        p.classList.toggle('active', i === currentTrackIndex);
    });
}

// ── Dynamic Color Theme ──────────────────────────────────
function applyTrackTheme(trackId) {
    const theme = TRACK_THEMES[trackId] || { accent: '#ffaa00', glow: 'rgba(255,170,0,0.6)' };
    document.documentElement.style.setProperty('--accent', theme.accent);
    document.documentElement.style.setProperty('--accent-glow', theme.glow);
}

// ── Track Loading ────────────────────────────────────────
async function loadTrack(index) {
    if (!currentAlbumConfig || !currentAlbumConfig.tracks || index >= currentAlbumConfig.tracks.length) return;
    currentTrackIndex = index;
    const trackMeta = currentAlbumConfig.tracks[index];
    if (!trackMeta) return;

    audio.src = `albums/${currentAlbumConfig.album_id}/${trackMeta.audioFile}`;
    if (elTrackName) elTrackName.innerText = trackMeta.title || '';

    // Apply color theme
    applyTrackTheme(trackMeta.id);
    updateTrackPills();

    // Default Media Fallback
    let initMediaStr = trackMeta.defaultMedia;
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

    // Reset state
    currentLyricIndex = -1;
    currentMediaIndex = -1;
    currentWordIndex = -1;
    lastTriggeredMedia = null;
    wordSpansBuilt = false;
    wordSpans = [];
    preloadedImages.clear();

    const tl = loadedTrackData && loadedTrackData.timeline;
    if (elPrev) elPrev.innerText = "";
    if (elCurr) elCurr.innerHTML = (tl && tl.length > 0) ? "..." : (trackMeta.title || "");
    if (elNext) elNext.innerText = (tl && tl.length > 0) ? sanitizeLyricForDisplay(tl[0].lyric) : "";

    // Hide meaning panel
    if (meaningPanel) {
        meaningPanel.classList.remove('meaning-visible');
        meaningPanel.classList.add('meaning-hidden');
    }

    // Reset time display
    if (timeCurrent) timeCurrent.textContent = '0:00';
    if (timeTotal) timeTotal.textContent = '0:00';
}

// ── Media Change (A/B crossfade) ─────────────────────────
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

// ── Image Preloader ──────────────────────────────────────
function preloadImagesForLines(timeline, startIdx, count) {
    if (!timeline) return;
    for (let i = startIdx; i < Math.min(startIdx + count, timeline.length); i++) {
        const entry = timeline[i];
        if (!entry || !entry.media) continue;
        for (const m of entry.media) {
            if (m && m.url && !preloadedImages.has(m.url)) {
                const img = new Image();
                img.src = `albums/${currentAlbumConfig.album_id}/${m.url}`;
                preloadedImages.add(m.url);
            }
        }
    }
}

// ── Energy Lookup (binary search) ────────────────────────
function getEnergyAtTime(energyCurve, time) {
    if (!energyCurve || energyCurve.length === 0) return 0.5;
    if (time <= energyCurve[0][0]) return energyCurve[0][1];
    if (time >= energyCurve[energyCurve.length - 1][0]) return energyCurve[energyCurve.length - 1][1];

    let lo = 0, hi = energyCurve.length - 1;
    while (lo < hi - 1) {
        const mid = (lo + hi) >> 1;
        if (energyCurve[mid][0] <= time) lo = mid;
        else hi = mid;
    }
    // Linear interpolation
    const t0 = energyCurve[lo][0], t1 = energyCurve[hi][0];
    const v0 = energyCurve[lo][1], v1 = energyCurve[hi][1];
    const frac = (t1 > t0) ? (time - t0) / (t1 - t0) : 0;
    return v0 + frac * (v1 - v0);
}

// ── Build Word Spans (once per line) ─────────────────────
function buildWordSpans(words) {
    wordSpans = [];
    if (!words || words.length === 0) return '';

    const frag = document.createDocumentFragment();
    const limit = Math.min(words.length, DISPLAY_MAX_WORDS);
    for (let i = 0; i < limit; i++) {
        const span = document.createElement('span');
        span.className = 'word-future';
        span.textContent = words[i].text;
        wordSpans.push(span);
        frag.appendChild(span);
        if (i < limit - 1) frag.appendChild(document.createTextNode(' '));
    }
    if (words.length > DISPLAY_MAX_WORDS) {
        frag.appendChild(document.createTextNode('\u2026'));
    }
    wordSpansBuilt = true;
    return frag;
}

// ── rAF Sync Loop (~60fps) ───────────────────────────────
function syncTick() {
    rafId = requestAnimationFrame(syncTick);

    if (!loadedTrackData || !loadedTrackData.timeline || loadedTrackData.timeline.length === 0) return;
    const timeline = loadedTrackData.timeline;
    const ct = audio.currentTime;

    // ── 1. Find current timeline entry ──
    let newTimelineIdx = -1;
    let inGap = false;
    for (let i = 0; i < timeline.length; i++) {
        if (ct >= timeline[i].start && ct < timeline[i].end) {
            newTimelineIdx = i;
            break;
        }
    }
    // Fallback: show last started entry (we're in a gap between entries)
    if (newTimelineIdx === -1) {
        inGap = true;
        for (let i = 0; i < timeline.length; i++) {
            if (ct >= timeline[i].start) newTimelineIdx = i;
        }
    }

    // ── 2. Line change ──
    if (newTimelineIdx !== currentLyricIndex && newTimelineIdx !== -1) {
        currentLyricIndex = newTimelineIdx;
        currentWordIndex = -1;
        wordSpansBuilt = false;
        lastTriggeredMedia = null;
        const lineData = timeline[currentLyricIndex];

        // Prev/next
        if (elPrev) {
            elPrev.innerText = currentLyricIndex > 0
                ? sanitizeLyricForDisplay(timeline[currentLyricIndex - 1].lyric) : "";
        }
        if (elNext) {
            elNext.innerText = currentLyricIndex < timeline.length - 1
                ? sanitizeLyricForDisplay(timeline[currentLyricIndex + 1].lyric) : "";
        }

        // Current line
        if (elCurr && lineData) {
            const baseLyric = sanitizeLyricForDisplay(lineData.lyric);

            // Responsive sizing
            elCurr.classList.remove('lyric-short', 'lyric-medium', 'lyric-long', 'slide-in');
            if (baseLyric.length <= 40) elCurr.classList.add('lyric-short');
            else if (baseLyric.length <= 120) elCurr.classList.add('lyric-medium');
            else elCurr.classList.add('lyric-long');

            // Build word spans if words available, else plain text
            const words = lineData.words || [];
            if (words.length > 0) {
                elCurr.innerHTML = '';
                elCurr.appendChild(buildWordSpans(words));
            } else {
                elCurr.textContent = baseLyric;
                wordSpansBuilt = false;
            }

            // Slide-in animation
            void elCurr.offsetWidth; // force reflow
            elCurr.classList.add('slide-in');
        }

        // Meaning panel
        if (lineData && lineData.real_meaning) {
            if (meaningText) meaningText.textContent = lineData.real_meaning;
            if (meaningPanel) {
                meaningPanel.classList.remove('meaning-hidden');
                meaningPanel.classList.add('meaning-visible');
            }
        } else {
            if (meaningPanel) {
                meaningPanel.classList.remove('meaning-visible');
                meaningPanel.classList.add('meaning-hidden');
            }
        }

        // Preload images for upcoming lines
        preloadImagesForLines(timeline, currentLyricIndex, 3);
    }

    // ── 3. Progressive word highlighting ──
    if (currentLyricIndex !== -1 && currentLyricIndex < timeline.length && wordSpansBuilt) {
        const activeLine = timeline[currentLyricIndex];
        const words = activeLine.words || [];
        if (words.length > 0 && wordSpans.length > 0) {
            const limit = Math.min(wordSpans.length, words.length);

            // In a gap between timeline entries: mark all words as sung
            if (inGap) {
                if (currentWordIndex !== limit) {
                    currentWordIndex = limit;
                    for (let i = 0; i < limit; i++) wordSpans[i].className = 'word-sung';
                }
            } else {
                let newWordIdx = -1;
                for (let w = 0; w < words.length; w++) {
                    if (ct >= words[w].start) newWordIdx = w;
                }

                if (newWordIdx !== currentWordIndex) {
                    currentWordIndex = newWordIdx;
                    for (let i = 0; i < limit; i++) {
                        if (newWordIdx === -1) {
                            // Before first word starts
                            wordSpans[i].className = 'word-future';
                        } else if (i < newWordIdx) {
                            wordSpans[i].className = 'word-sung';
                        } else if (i === newWordIdx) {
                            // Only show as active if we're within the word's duration
                            const w = words[i];
                            const isWithin = ct >= w.start && ct < w.end;
                            wordSpans[i].className = isWithin ? 'word-active' : 'word-sung';
                        } else {
                            wordSpans[i].className = 'word-future';
                        }
                    }
                }
            }
        }
    }

    // ── 4. Media sub-timeline ──
    if (currentLyricIndex !== -1 && currentLyricIndex < timeline.length) {
        const activeLine = timeline[currentLyricIndex];
        const mediaArr = activeLine && activeLine.media;
        if (mediaArr && mediaArr.length > 0) {
            let chosenMedia = mediaArr[0].url;
            for (let m = 0; m < mediaArr.length; m++) {
                if (!mediaArr[m]) continue;
                const triggerTime = activeLine.start + parseFloat(mediaArr[m].offset || 0);
                if (ct >= triggerTime) chosenMedia = mediaArr[m].url;
            }
            if (chosenMedia && lastTriggeredMedia !== chosenMedia) {
                lastTriggeredMedia = chosenMedia;
                triggerMediaChange(`albums/${currentAlbumConfig.album_id}/${chosenMedia}`);
            }
        }
    }

    // ── 5. Energy-responsive effects (throttled to ~10Hz) ──
    const now = performance.now();
    if (now - lastEnergyCheck > 100) {
        lastEnergyCheck = now;
        const energyCurve = loadedTrackData.energy_curve;
        if (energyCurve && energyCurve.length > 0) {
            const energy = getEnergyAtTime(energyCurve, ct);

            // Dynamic brightness: 0.25 at low energy, 0.50 at high
            const brightness = 0.25 + energy * 0.25;
            document.documentElement.style.setProperty('--media-brightness', brightness.toFixed(3));

            // Vignette opacity: deeper at quiet sections
            if (vignetteOverlay) {
                vignetteOverlay.style.opacity = (1.0 - energy * 0.5).toFixed(2);
            }

            // Crossfade speed: fast at high energy, slow at quiet
            const speed = (1.2 - energy * 0.9).toFixed(2);
            document.documentElement.style.setProperty('--crossfade-speed', speed + 's');
        }
    }
}

function startSyncLoop() {
    if (rafId) return;
    rafId = requestAnimationFrame(syncTick);
}

function stopSyncLoop() {
    if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = null;
    }
}

// ── Playback Controls ────────────────────────────────────
function togglePlay() {
    if (audio.paused) {
        audio.play();
        if (btnPlay) btnPlay.innerText = "\u23F8";
        startSyncLoop();
    } else {
        audio.pause();
        if (btnPlay) btnPlay.innerText = "\u25B6";
        stopSyncLoop();
    }
}
if (btnPlay) btnPlay.addEventListener('click', togglePlay);

if (btnNext) btnNext.addEventListener('click', () => {
    if (currentAlbumConfig && currentAlbumConfig.tracks && currentTrackIndex < currentAlbumConfig.tracks.length - 1) {
        loadTrack(currentTrackIndex + 1).then(() => { audio.play(); startSyncLoop(); });
    }
});

if (btnPrev) btnPrev.addEventListener('click', () => {
    if (audio.currentTime > 3) { audio.currentTime = 0; }
    else if (currentTrackIndex > 0) {
        loadTrack(currentTrackIndex - 1).then(() => { audio.play(); startSyncLoop(); });
    }
});

// Progress bar (keep timeupdate for this — low frequency is fine)
audio.addEventListener('timeupdate', () => {
    if (progressBar && audio.duration) {
        progressBar.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
    }
    if (timeCurrent) timeCurrent.textContent = formatTime(audio.currentTime);
    if (timeTotal && audio.duration) timeTotal.textContent = formatTime(audio.duration);
});

audio.addEventListener('play', () => {
    if (btnPlay) btnPlay.innerText = "\u23F8";
    startSyncLoop();
});

audio.addEventListener('pause', () => {
    if (btnPlay) btnPlay.innerText = "\u25B6";
    stopSyncLoop();
});

audio.addEventListener('ended', () => {
    stopSyncLoop();
    if (currentAlbumConfig && currentAlbumConfig.tracks && currentTrackIndex < currentAlbumConfig.tracks.length - 1) {
        loadTrack(currentTrackIndex + 1).then(() => { audio.play(); startSyncLoop(); });
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
        // Reset lyric index to force re-sync
        currentLyricIndex = -1;
        currentWordIndex = -1;
        wordSpansBuilt = false;
    });
}

// ── Init on Load ─────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const albumSelector = document.getElementById('album-selector');

    if (albumSelector && typeof albumRegistry !== 'undefined' && Array.isArray(albumRegistry)) {
        albumRegistry.forEach((entry) => {
            const opt = document.createElement('option');
            opt.value = entry.album_id;
            opt.textContent = entry.title;
            if (entry.album_id === currentAlbumId) opt.selected = true;
            albumSelector.appendChild(opt);
        });

        albumSelector.addEventListener('change', (e) => {
            const selectedId = e.target.value;
            currentAlbumId = selectedId;
            const entry = typeof getAlbumEntryById === 'function'
                ? getAlbumEntryById(currentAlbumId) : null;
            if (entry && entry.config) {
                currentAlbumConfig = entry.config;
                const elTitle = document.getElementById('album-title');
                const elSubtitle = document.getElementById('album-subtitle');
                if (elTitle) elTitle.innerText = currentAlbumConfig.title || '';
                if (elSubtitle) elSubtitle.innerText = currentAlbumConfig.description || '';
                buildTrackList();
                loadTrack(0);
            }
        });
    }

    initPlayer();
});
