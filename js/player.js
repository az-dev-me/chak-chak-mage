// player.js
// Orchestrator — delegates visual rendering to zone modules + timing engine
// Zone 1 (phone frame): literal story images
// Zone 2 (floating particles): hidden narrative fragments
// Zone 3 (ambient background): hidden narrative images (blurred/dimmed)

// ── Constants ────────────────────────────────────────────
const DISPLAY_MAX_WORDS = 60;
const DISPLAY_MAX_CHARS = 400;

// Per-track color themes
const TRACK_THEMES = {
    track_01: { accent: '#66cccc', glow: 'rgba(102,204,204,0.6)' },
    track_02: { accent: '#ff8844', glow: 'rgba(255,136,68,0.6)' },
    track_03: { accent: '#ff4444', glow: 'rgba(255,68,68,0.6)' },
    track_04: { accent: '#ffaa00', glow: 'rgba(255,170,0,0.6)' },
    track_05: { accent: '#ff77aa', glow: 'rgba(255,119,170,0.6)' },
    track_06: { accent: '#aa66ff', glow: 'rgba(170,102,255,0.6)' },
    track_07: { accent: '#4488ff', glow: 'rgba(68,136,255,0.6)' },
    track_08: { accent: '#ffcc33', glow: 'rgba(255,204,51,0.6)' },
    track_09: { accent: '#66cccc', glow: 'rgba(102,204,204,0.6)' },
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
const elPrev = document.getElementById('lyric-prev');
const elCurr = document.getElementById('lyric-curr');
const elNext = document.getElementById('lyric-next');
const elTrackName = document.getElementById('current-track-name');
const meaningPanel = document.getElementById('meaning-panel');
const meaningText = document.getElementById('meaning-text');
const trackListNav = document.getElementById('track-list');
const timeCurrent = document.getElementById('time-current');
const timeTotal = document.getElementById('time-total');

// ── State ────────────────────────────────────────────────
let currentTrackIndex = 0;
let currentLyricIndex = -1;
let currentWordIndex = -1;
let rafId = null;
let wordSpansBuilt = false;
let wordSpans = [];
let lastEnergyTick = 0;
let lineEnteredAt = 0;        // performance.now() when line changed
const LINE_GRACE_MS = 200;    // ms before word highlighting kicks in

// Image preload cache
const preloadedImages = new Set();

// Variant state
let currentVariantId = null;
const variantPicker = document.getElementById('variant-picker');

// ── Init ─────────────────────────────────────────────────
async function initPlayer() {
    const entry = (typeof getAlbumEntryById === 'function' && currentAlbumId)
        ? getAlbumEntryById(currentAlbumId) : null;
    currentAlbumConfig = entry && entry.config ? entry.config : fallbackAlbumConfig;

    const elTitle = document.getElementById('album-title');
    const elSubtitle = document.getElementById('album-subtitle');
    if (elTitle) elTitle.innerText = currentAlbumConfig.title || '';
    if (elSubtitle) elSubtitle.innerText = currentAlbumConfig.description || '';

    // Init zone modules
    Zone1Inner.init();
    Zone2Outer.init();
    Zone3Ambient.init();

    // Load album durations for dual timeline
    if (typeof loadAlbumDurations === 'function' && currentAlbumConfig.tracks) {
        await loadAlbumDurations(currentAlbumConfig.album_id, currentAlbumConfig.tracks.length);
        buildAlbumTimelineTicks();
    }

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
    pills.forEach((p, i) => p.classList.toggle('active', i === currentTrackIndex));
}

// ── Variant Picker ──────────────────────────────────────
function buildVariantPicker(trackMeta) {
    if (!variantPicker) return;
    variantPicker.innerHTML = '';
    const variants = trackMeta.variants || [];
    if (variants.length <= 1) {
        variantPicker.classList.add('hidden');
        currentVariantId = null;
        return;
    }
    variantPicker.classList.remove('hidden');
    // Mark the "best" variant as default active
    const defaultVariant = trackMeta.variant_id || variants[0].id;
    currentVariantId = defaultVariant;

    variants.forEach(v => {
        const btn = document.createElement('button');
        btn.className = 'variant-btn' + (v.id === defaultVariant ? ' active' : '');
        btn.textContent = v.label;
        btn.dataset.variantId = v.id;
        btn.dataset.audio = v.audio;
        btn.addEventListener('click', () => switchVariant(v, trackMeta));
        variantPicker.appendChild(btn);
    });
}

async function switchVariant(variant, trackMeta) {
    if (variant.id === currentVariantId) return;
    currentVariantId = variant.id;

    // Update active state on buttons
    if (variantPicker) {
        variantPicker.querySelectorAll('.variant-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.variantId === variant.id);
        });
    }

    const wasPlaying = !audio.paused;
    if (wasPlaying) stopSyncLoop();

    // Load variant-specific data (alignment, timeline, media)
    await fetchTrackData(trackMeta.id, variant.id);
    TimingEngine.load(loadedTrackData);

    // Swap audio
    const albumPath = `albums/${currentAlbumConfig.album_id}`;
    audio.src = `${albumPath}/${variant.audio}`;
    audio.currentTime = 0;

    // Full reset
    currentLyricIndex = -1;
    currentWordIndex = -1;
    wordSpansBuilt = false;
    wordSpans = [];
    preloadedImages.clear();

    Zone1Inner.reset();
    Zone2Outer.reset();
    Zone3Ambient.reset();
    TimingEngine.reset();

    // Set initial images from new variant's data
    const tl = loadedTrackData && loadedTrackData.timeline;
    if (tl) {
        const firstMediaLine = findFirstMediaLine(tl);
        if (firstMediaLine) {
            if (firstMediaLine.media && firstMediaLine.media.length > 0)
                Zone1Inner.setImage(`${albumPath}/${firstMediaLine.media[0].url}`);
            if (firstMediaLine.hidden_media && firstMediaLine.hidden_media.length > 0)
                Zone3Ambient.setImage(`${albumPath}/${firstMediaLine.hidden_media[0].url}`);
            Zone2Outer.updateBars(firstMediaLine, 0, albumPath);
        }
        preloadImagesForLines(tl, 0, 3);
    }

    // Lyrics display
    if (elPrev) elPrev.innerText = "";
    if (elCurr) elCurr.innerHTML = trackMeta.title || "...";
    if (elNext && tl && tl.length > 0) elNext.innerText = sanitizeLyricForDisplay(tl[0].lyric);

    if (wasPlaying) {
        audio.play();
        startSyncLoop();
    }
}

// ── Dynamic Color Theme ──────────────────────────────────
function applyTrackTheme(trackId) {
    const theme = TRACK_THEMES[trackId] || { accent: '#ffaa00', glow: 'rgba(255,170,0,0.6)' };
    document.documentElement.style.setProperty('--accent', theme.accent);
    document.documentElement.style.setProperty('--accent-glow', theme.glow);
}

// ── Find first line with media/hidden_media ──────────────
function findFirstMediaLine(timeline) {
    if (!timeline) return null;
    for (let i = 0; i < timeline.length; i++) {
        if ((timeline[i].media && timeline[i].media.length > 0) ||
            (timeline[i].hidden_media && timeline[i].hidden_media.length > 0)) {
            return timeline[i];
        }
    }
    return null;
}

// ── Track Loading ────────────────────────────────────────
async function loadTrack(index) {
    if (!currentAlbumConfig || !currentAlbumConfig.tracks || index >= currentAlbumConfig.tracks.length) return;
    currentTrackIndex = index;
    const trackMeta = currentAlbumConfig.tracks[index];
    if (!trackMeta) return;

    audio.src = `albums/${currentAlbumConfig.album_id}/${trackMeta.audio_path || trackMeta.audioFile}`;
    if (elTrackName) elTrackName.innerText = trackMeta.title || '';

    applyTrackTheme(trackMeta.id);
    updateTrackPills();
    buildVariantPicker(trackMeta);

    // Load sync data — pass default variant so we load the right data file
    const defaultVariantId = trackMeta.variant_id || null;
    currentVariantId = defaultVariantId;
    await fetchTrackData(trackMeta.id, defaultVariantId);

    // Load timing data into TimingEngine + reset audio analyser
    if (loadedTrackData) {
        TimingEngine.load(loadedTrackData);
        if (typeof AudioAnalyser !== 'undefined') AudioAnalyser.reset();

        // Pre-compute downbeat times (every 4th beat) for stronger image transitions
        if (loadedTrackData.beat_times && loadedTrackData.beat_times.length > 0) {
            const downbeats = [];
            for (let i = 0; i < loadedTrackData.beat_times.length; i += 4) {
                downbeats.push(loadedTrackData.beat_times[i]);
            }
            loadedTrackData.downbeatTimes = downbeats;
        } else {
            loadedTrackData.downbeatTimes = [];
        }
    }

    // Load structure data fallback
    if (typeof loadStructureData === 'function') {
        await loadStructureData(currentAlbumConfig.album_id, trackMeta.id);
    }

    // Reset state FIRST
    currentLyricIndex = -1;
    currentWordIndex = -1;
    wordSpansBuilt = false;
    wordSpans = [];
    preloadedImages.clear();

    // Reset all zone modules
    Zone1Inner.reset();
    Zone2Outer.reset();
    Zone3Ambient.reset();
    TimingEngine.reset();

    // THEN set initial images (after reset, so they're not cleared)
    const tl = loadedTrackData && loadedTrackData.timeline;
    const albumPath = `albums/${currentAlbumConfig.album_id}`;
    const firstMediaLine = findFirstMediaLine(tl);

    if (firstMediaLine) {
        // Zone 1: literal story image inside phone frame
        if (firstMediaLine.media && firstMediaLine.media.length > 0) {
            Zone1Inner.setImage(`${albumPath}/${firstMediaLine.media[0].url}`);
        }
        // Zone 3: hidden narrative image as atmospheric background
        if (firstMediaLine.hidden_media && firstMediaLine.hidden_media.length > 0) {
            Zone3Ambient.setImage(`${albumPath}/${firstMediaLine.hidden_media[0].url}`);
        }
        // Zone 2: bars show first line's hidden narrative at edges
        Zone2Outer.updateBars(firstMediaLine, 0, albumPath);
    }

    // Lyrics display
    if (elPrev) elPrev.innerText = "";
    if (elCurr) elCurr.innerHTML = trackMeta.title || "...";
    if (elNext) elNext.innerText = (tl && tl.length > 0) ? sanitizeLyricForDisplay(tl[0].lyric) : "";

    // Hide meaning panels
    if (meaningPanel) {
        meaningPanel.classList.remove('meaning-visible');
        meaningPanel.classList.add('meaning-hidden');
    }

    if (timeCurrent) timeCurrent.textContent = '0:00';
    if (timeTotal) timeTotal.textContent = '0:00';

    // Preload first few lines of images
    if (tl) preloadImagesForLines(tl, 0, 3);
}

// ── Album Timeline Ticks ─────────────────────────────────
function buildAlbumTimelineTicks() {
    const container = document.getElementById('album-track-ticks');
    if (!container || typeof albumTotalDuration === 'undefined' || albumTotalDuration <= 0) return;
    container.innerHTML = '';

    for (let i = 1; i < trackCumulativeStarts.length; i++) {
        const tick = document.createElement('div');
        tick.className = 'track-tick';
        tick.style.left = `${(trackCumulativeStarts[i] / albumTotalDuration) * 100}%`;
        container.appendChild(tick);
    }
}

// ── Image Preloader ──────────────────────────────────────
function preloadImagesForLines(timeline, startIdx, count) {
    if (!timeline) return;
    const albumPath = `albums/${currentAlbumConfig.album_id}`;

    for (let i = startIdx; i < Math.min(startIdx + count, timeline.length); i++) {
        const entry = timeline[i];
        if (!entry) continue;
        const allMedia = (entry.media || []).concat(entry.hidden_media || []);
        for (const m of allMedia) {
            if (m && m.url && !preloadedImages.has(m.url)) {
                const img = new Image();
                img.src = `${albumPath}/${m.url}`;
                preloadedImages.add(m.url);
            }
        }
    }

    // Background preload for lines further ahead
    const bgStart = startIdx + count;
    const bgEnd = Math.min(bgStart + 3, timeline.length);
    const loadBg = () => {
        for (let i = bgStart; i < bgEnd; i++) {
            const entry = timeline[i];
            if (!entry) continue;
            const allMedia = (entry.media || []).concat(entry.hidden_media || []);
            for (const m of allMedia) {
                if (m && m.url && !preloadedImages.has(m.url)) {
                    const img = new Image();
                    img.src = `${albumPath}/${m.url}`;
                    preloadedImages.add(m.url);
                }
            }
        }
    };
    if (typeof requestIdleCallback !== 'undefined') {
        requestIdleCallback(loadBg);
    } else {
        setTimeout(loadBg, 200);
    }
}

// ── Build Word Spans ─────────────────────────────────────
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
let lastFrameTs = 0;

function syncTick(frameTimestamp) {
    rafId = requestAnimationFrame(syncTick);

    // Frame delta time (seconds) for frame-rate independent smoothing
    const dt = lastFrameTs ? (frameTimestamp - lastFrameTs) / 1000 : 0.016;
    lastFrameTs = frameTimestamp;

    if (!loadedTrackData || !loadedTrackData.timeline || loadedTrackData.timeline.length === 0) return;
    const timeline = loadedTrackData.timeline;
    const ct = audio.currentTime;
    const albumPath = `albums/${currentAlbumConfig.album_id}`;

    // ── 1a. Timing engine tick (MACRO: sections, transitions, energy_curve) ──
    const timing = TimingEngine.tick(ct);

    // ── 1b. Real-time audio analysis (MICRO: frequency bands, beat detection) ──
    let audioState = null;
    if (typeof AudioAnalyser !== 'undefined' && AudioAnalyser.isActive()) {
        audioState = AudioAnalyser.analyse(dt, ct);
    }

    // ── 2. Find current timeline entry ──
    let newTimelineIdx = -1;
    let inGap = false;
    for (let i = 0; i < timeline.length; i++) {
        if (ct >= timeline[i].start && ct < timeline[i].end) {
            newTimelineIdx = i;
            break;
        }
    }
    if (newTimelineIdx === -1) {
        inGap = true;
        for (let i = 0; i < timeline.length; i++) {
            if (ct >= timeline[i].start) newTimelineIdx = i;
        }
    }

    // ── 3. Line change ──
    if (newTimelineIdx !== currentLyricIndex && newTimelineIdx !== -1) {
        currentLyricIndex = newTimelineIdx;
        currentWordIndex = -1;
        wordSpansBuilt = false;
        lineEnteredAt = performance.now();  // Grace period: don't highlight first word immediately
        const lineData = timeline[currentLyricIndex];

        // Prev/next lyrics
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
            elCurr.classList.remove('lyric-short', 'lyric-medium', 'lyric-long', 'slide-in');
            if (baseLyric.length <= 40) elCurr.classList.add('lyric-short');
            else if (baseLyric.length <= 120) elCurr.classList.add('lyric-medium');
            else elCurr.classList.add('lyric-long');

            const words = lineData.words || [];
            if (words.length > 0) {
                elCurr.innerHTML = '';
                elCurr.appendChild(buildWordSpans(words));
            } else {
                elCurr.textContent = baseLyric;
                wordSpansBuilt = false;
            }

            void elCurr.offsetWidth;
            elCurr.classList.add('slide-in');
        }

        // Modern parallel panel (always visible inside phone, dims when no text)
        if (lineData && lineData.real_meaning && lineData.real_meaning.trim()) {
            if (meaningText) meaningText.textContent = lineData.real_meaning;
            if (meaningPanel) {
                meaningPanel.classList.remove('meaning-hidden');
                meaningPanel.classList.add('meaning-visible');
            }
        } else {
            // Keep last text visible but dimmed — no layout jump
            if (meaningPanel) {
                meaningPanel.classList.remove('meaning-visible');
                meaningPanel.classList.add('meaning-hidden');
            }
        }

        // Zone 2: outer meaning overlay
        Zone2Outer.updateMeaning(lineData);

        // (bars now update per-frame in section 5 to catch offset changes)

        // Preload upcoming images
        preloadImagesForLines(timeline, currentLyricIndex, 2);
    }

    // ── 4. Progressive word highlighting ──
    if (currentLyricIndex !== -1 && currentLyricIndex < timeline.length && wordSpansBuilt) {
        // Grace period: keep all words as word-future for LINE_GRACE_MS after line change
        if (performance.now() - lineEnteredAt < LINE_GRACE_MS) {
            // Still in grace — all spans stay 'word-future' (set by buildWordSpans)
        } else {
            const activeLine = timeline[currentLyricIndex];
            const words = activeLine.words || [];
            if (words.length > 0 && wordSpans.length > 0) {
                const limit = Math.min(wordSpans.length, words.length);

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
                                wordSpans[i].className = 'word-future';
                            } else if (i < newWordIdx) {
                                wordSpans[i].className = 'word-sung';
                            } else if (i === newWordIdx) {
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
    }

    // ── 5. Zone media updates ──
    if (currentLyricIndex !== -1 && currentLyricIndex < timeline.length) {
        const activeLine = timeline[currentLyricIndex];

        // Zone 1: literal story images inside phone frame
        Zone1Inner.updateMedia(activeLine, ct, albumPath);

        // Zone 2: bars show current line's hidden narrative (gradient-masked edges)
        Zone2Outer.updateBars(activeLine, ct, albumPath);

        // Zone 2: section change — refresh bars with nearest hidden images
        if (timing.sectionChanged && timing.section) {
            const secIdx = loadedTrackData.sections ? loadedTrackData.sections.indexOf(timing.section) : -1;
            Zone2Outer.onSectionChange(secIdx, timeline, ct, albumPath);
            if (timing.energy > 0.7) {
                Zone2Outer.chorusPulse();
            }
        }

        // Zone 3: ambient background shows HIDDEN narrative (modern parallel)
        if (activeLine.hidden_media && activeLine.hidden_media.length > 0) {
            let chosenHidden = activeLine.hidden_media[0].url;
            for (let h = 0; h < activeLine.hidden_media.length; h++) {
                if (!activeLine.hidden_media[h]) continue;
                const trigTime = activeLine.start + parseFloat(activeLine.hidden_media[h].offset || 0);
                if (ct >= trigTime) chosenHidden = activeLine.hidden_media[h].url;
            }
            if (chosenHidden) {
                Zone3Ambient.setImage(`${albumPath}/${chosenHidden}`);
            }
        }
    }

    // ── 6. Audio-reactive visuals ──
    // Use REAL-TIME audio analysis when available, fall back to pre-computed
    const root = document.documentElement.style;
    if (audioState) {
        // Real-time: driven by actual frequency content of the playing audio
        root.setProperty('--beat-pulse', audioState.beatPulse.toFixed(3));
        root.setProperty('--bass-energy', audioState.bass.toFixed(3));
        root.setProperty('--treble-energy', audioState.treble.toFixed(3));
        root.setProperty('--audio-energy', audioState.overall.toFixed(3));

        // Beat effects: real-time bass detection replaces pre-computed timestamps
        Zone2Outer.applyBeatPulse(audioState.beatPulse, audioState.beatDetected);
    } else {
        // Fallback: pre-computed timing data (less accurate but still functional)
        root.setProperty('--beat-pulse', timing.beatPulse.toFixed(3));
        root.setProperty('--bass-energy', '0');
        root.setProperty('--treble-energy', '0');
        root.setProperty('--audio-energy', timing.energy.toFixed(3));

        Zone2Outer.applyBeatPulse(timing.beatPulse, timing.isDownbeat);
    }

    // ── 7. Energy-responsive effects (throttled ~15Hz) ──
    const now = performance.now();
    if (now - lastEnergyTick > 66) {
        lastEnergyTick = now;
        const energyVal = audioState ? audioState.overall : timing.energy;
        Zone3Ambient.applyEnergy(energyVal);
        Zone2Outer.applyEnergy(energyVal);
    }
}

function startSyncLoop() {
    if (rafId) return;
    // Connect audio analyser (async — audio plays normally until it's ready).
    // connect() awaits AudioContext.resume() before rerouting audio,
    // so there's never a moment of silence.
    if (typeof AudioAnalyser !== 'undefined' && !AudioAnalyser.isActive()) {
        AudioAnalyser.connect(audio); // fire-and-forget async
    }
    rafId = requestAnimationFrame(syncTick);
}

function stopSyncLoop() {
    if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = null;
    }
}

// ── Auto-Hide UI (immersive mode) ────────────────────────
// During playback, controls collapse and track pills shrink to dots.
// Mouse movement over the phone frame reveals everything temporarily.
let uiCollapseTimer = null;
const UI_COLLAPSE_MS = 4000;

function collapseUI() {
    const pc = document.getElementById('player-controls');
    if (pc) pc.classList.add('controls-compact');
    if (trackListNav) trackListNav.classList.add('track-nav-dim');
}

function revealUI() {
    const pc = document.getElementById('player-controls');
    if (pc) pc.classList.remove('controls-compact');
    if (trackListNav) trackListNav.classList.remove('track-nav-dim');
    clearTimeout(uiCollapseTimer);
}

function scheduleUICollapse() {
    clearTimeout(uiCollapseTimer);
    if (!audio.paused) {
        uiCollapseTimer = setTimeout(() => {
            if (!audio.paused) collapseUI();
        }, UI_COLLAPSE_MS);
    }
}

// Mouse movement over phone frame temporarily reveals UI
const phoneFrame = document.getElementById('phone-frame');
if (phoneFrame) {
    phoneFrame.addEventListener('mousemove', () => {
        if (audio.paused) return;
        revealUI();
        scheduleUICollapse();
    });
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

// Progress bar — dual timeline (album + track)
audio.addEventListener('timeupdate', () => {
    // Track-level progress
    if (progressBar && audio.duration) {
        progressBar.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
    }

    // Album-level progress
    const albumBar = document.getElementById('album-progress-bar');
    if (albumBar && typeof albumTotalDuration !== 'undefined' && albumTotalDuration > 0) {
        const albumPosition = (trackCumulativeStarts[currentTrackIndex] || 0) + audio.currentTime;
        albumBar.style.width = `${(albumPosition / albumTotalDuration) * 100}%`;
    }

    // Time display — switches between album and track mode on hover
    const timelineContainer = document.getElementById('timeline-container');
    const isHovering = timelineContainer && timelineContainer.matches(':hover');
    const modeLabel = document.getElementById('time-mode-label');

    if (isHovering) {
        if (timeCurrent) timeCurrent.textContent = formatTime(audio.currentTime);
        if (timeTotal && audio.duration) timeTotal.textContent = formatTime(audio.duration);
        if (modeLabel) modeLabel.textContent = 'TRACK';
    } else {
        const albumPos = (typeof trackCumulativeStarts !== 'undefined' ? (trackCumulativeStarts[currentTrackIndex] || 0) : 0) + audio.currentTime;
        if (timeCurrent) timeCurrent.textContent = formatTime(albumPos);
        if (timeTotal && typeof albumTotalDuration !== 'undefined' && albumTotalDuration > 0) {
            timeTotal.textContent = formatTime(albumTotalDuration);
        } else if (timeTotal && audio.duration) {
            timeTotal.textContent = formatTime(audio.duration);
        }
        if (modeLabel) modeLabel.textContent = 'ALBUM';
    }
});

audio.addEventListener('play', () => {
    if (btnPlay) btnPlay.innerText = "\u23F8";
    startSyncLoop();
    scheduleUICollapse();
});

audio.addEventListener('pause', () => {
    if (btnPlay) btnPlay.innerText = "\u25B6";
    stopSyncLoop();
    revealUI();
});

audio.addEventListener('ended', () => {
    stopSyncLoop();
    revealUI();
    if (currentAlbumConfig && currentAlbumConfig.tracks && currentTrackIndex < currentAlbumConfig.tracks.length - 1) {
        loadTrack(currentTrackIndex + 1).then(() => { audio.play(); startSyncLoop(); });
    } else {
        if (btnPlay) btnPlay.innerText = "\u25B6";
        if (elCurr) elCurr.innerText = "Experience Complete.";
    }
});

// Track-level scrub
const trackProgressContainer = document.getElementById('track-progress-container');
if (trackProgressContainer) {
    trackProgressContainer.addEventListener('click', (e) => {
        if (!audio.duration) return;
        const clickPercent = e.offsetX / trackProgressContainer.offsetWidth;
        audio.currentTime = clickPercent * audio.duration;
        currentLyricIndex = -1;
        currentWordIndex = -1;
        wordSpansBuilt = false;
    });
}

// Album-level scrub — click jumps to correct track + position
const albumProgressContainer = document.getElementById('album-progress-container');
if (albumProgressContainer) {
    albumProgressContainer.addEventListener('click', (e) => {
        if (typeof albumTotalDuration === 'undefined' || albumTotalDuration <= 0) return;
        const clickPercent = e.offsetX / albumProgressContainer.offsetWidth;
        const albumTime = clickPercent * albumTotalDuration;

        // Find which track this falls in
        let targetTrack = 0;
        for (let i = 0; i < trackCumulativeStarts.length; i++) {
            if (albumTime >= trackCumulativeStarts[i]) targetTrack = i;
        }

        const timeInTrack = albumTime - trackCumulativeStarts[targetTrack];

        if (targetTrack !== currentTrackIndex) {
            loadTrack(targetTrack).then(() => {
                audio.currentTime = Math.max(0, timeInTrack);
                audio.play();
                startSyncLoop();
            });
        } else {
            audio.currentTime = Math.max(0, timeInTrack);
        }
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
