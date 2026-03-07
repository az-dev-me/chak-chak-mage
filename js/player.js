// player.js
// Orchestrator — delegates visual rendering to zone modules + timing engine
// Zone 1 (phone frame): literal story images
// Zone 2 (floating particles): hidden narrative fragments
// Zone 3 (ambient background): hidden narrative images (blurred/dimmed)

// ── Language ─────────────────────────────────────────────
const LANG = (() => {
    const urlLang = new URLSearchParams(window.location.search).get('lang');
    if (['en', 'pt', 'pt-br'].includes(urlLang)) return urlLang;
    return localStorage.getItem('chak_lang') || 'en';
})();

// ── Constants ────────────────────────────────────────────
const DISPLAY_MAX_WORDS = 60;
const DISPLAY_MAX_CHARS = 400;

// Per-track emotion color themes — used as fallback when album_config doesn't include themes
const TRACK_THEMES_FALLBACK = {
    track_01: { accent: '#ffaa00', glow: 'rgba(255,170,0,0.6)' },
    track_02: { accent: '#ff8800', glow: 'rgba(255,136,0,0.6)' },
    track_03: { accent: '#ff4444', glow: 'rgba(255,68,68,0.6)' },
    track_04: { accent: '#cc66ff', glow: 'rgba(204,102,255,0.6)' },
    track_05: { accent: '#44dd88', glow: 'rgba(68,221,136,0.6)' },
    track_06: { accent: '#ff2244', glow: 'rgba(255,34,68,0.6)' },
    track_07: { accent: '#4488ff', glow: 'rgba(68,136,255,0.6)' },
    track_08: { accent: '#44ccaa', glow: 'rgba(68,204,170,0.6)' },
    track_09: { accent: '#ffffff', glow: 'rgba(255,255,255,0.5)' },
};

// Auto-generate theme from track index when no config theme exists
function generateDefaultTheme(index) {
    const hue = (index * 40 + 30) % 360;
    return {
        accent: `hsl(${hue}, 70%, 55%)`,
        glow: `hsla(${hue}, 70%, 55%, 0.6)`
    };
}

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
let meaningWordSpans = [];    // word spans for modern parallel text
let lastMeaningSetAt = 0;     // performance.now() when meaning last changed
let lastEnergyTick = 0;
let lineEnteredAt = 0;        // performance.now() when line changed
const LINE_GRACE_MS = 200;    // ms before word highlighting kicks in
const MEANING_HOLD_MS = 4000; // ms to keep meaning fully visible after line ends

// Image preload cache
const preloadedImages = new Set();
let _nextTrackPreloaded = false;

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
    SymbolEmbers.init(document.getElementById('phone-frame'));

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
            loadTrack(i).then(() => { audio.play(); reconnectAnalyserAndPlay(); });
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
    // Always default to the first variant in the list
    const defaultVariant = variants[0].id;
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

    // Disconnect stale audio analyser (will reconnect on play)
    if (typeof AudioAnalyser !== 'undefined') {
        AudioAnalyser.disconnect();
        AudioAnalyser.reset();
    }

    // Full reset
    currentLyricIndex = -1;
    currentWordIndex = -1;
    wordSpansBuilt = false;
    wordSpans = [];
    preloadedImages.clear();
    _nextTrackPreloaded = false;

    Zone1Inner.reset();
    Zone2Outer.reset();
    Zone3Ambient.reset();
    if (typeof SymbolEmbers !== 'undefined') SymbolEmbers.clear();
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

    // Reset meaning panel for new variant
    meaningWordSpans = [];
    if (meaningText) meaningText.innerHTML = '';
    if (meaningPanel) {
        meaningPanel.classList.remove('meaning-visible');
        meaningPanel.classList.add('meaning-hidden');
    }

    if (wasPlaying) {
        audio.play();
        reconnectAnalyserAndPlay();
    }
}

// ── Dynamic Color Theme ──────────────────────────────────
function applyTrackTheme(trackId) {
    // Priority: album_config theme > hardcoded fallback > auto-generated hue
    let theme = null;
    if (currentAlbumConfig && currentAlbumConfig.tracks) {
        const trackMeta = currentAlbumConfig.tracks.find(t => t.id === trackId);
        if (trackMeta && trackMeta.theme) theme = trackMeta.theme;
    }
    if (!theme) theme = TRACK_THEMES_FALLBACK[trackId];
    if (!theme) theme = generateDefaultTheme(currentTrackIndex);
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

    if (elTrackName) elTrackName.innerText = trackMeta.title || '';

    applyTrackTheme(trackMeta.id);
    updateTrackPills();
    buildVariantPicker(trackMeta);

    // Load sync data — use first variant if available, otherwise bare track
    const variants = trackMeta.variants || [];
    const defaultVariantId = variants.length > 0 ? variants[0].id : (trackMeta.variant_id || null);

    // Use first variant's audio if available, otherwise track-level audio
    const firstVariant = variants.length > 0 ? variants[0] : null;
    const audioFile = (firstVariant && firstVariant.audio) || trackMeta.audio_path || trackMeta.audioFile;
    audio.src = `albums/${currentAlbumConfig.album_id}/${audioFile}`;
    currentVariantId = defaultVariantId;
    await fetchTrackData(trackMeta.id, defaultVariantId);

    // Load timing data into TimingEngine + disconnect stale audio analyser
    if (loadedTrackData) {
        TimingEngine.load(loadedTrackData);
        if (typeof AudioAnalyser !== 'undefined') {
            AudioAnalyser.disconnect();
            AudioAnalyser.reset();
        }

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
    _nextTrackPreloaded = false;

    // Reset all zone modules
    Zone1Inner.reset();
    Zone2Outer.reset();
    Zone3Ambient.reset();
    if (typeof SymbolEmbers !== 'undefined') SymbolEmbers.clear();
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

    // Clear meaning panel completely for new track
    meaningWordSpans = [];
    if (meaningText) meaningText.innerHTML = '';
    if (meaningPanel) {
        meaningPanel.classList.remove('meaning-visible');
        meaningPanel.classList.add('meaning-hidden');
    }

    if (timeCurrent) timeCurrent.textContent = '0:00';
    if (timeTotal) timeTotal.textContent = '0:00';

    // Preload first few lines eagerly, then background-load the rest
    if (tl) {
        preloadImagesForLines(tl, 0, 5);
        preloadAllTrackImages(tl);
    }
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

    // Immediate: preload next few lines eagerly
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

    // Background: preload 8 more lines ahead using idle time
    const bgStart = startIdx + count;
    const bgEnd = Math.min(bgStart + 8, timeline.length);
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

// Preload all images for a track in batches (runs in background after track loads)
let _bgPreloadTimer = null;
function preloadAllTrackImages(timeline) {
    if (!timeline || timeline.length === 0) return;
    clearTimeout(_bgPreloadTimer);
    const albumPath = `albums/${currentAlbumConfig.album_id}`;
    let lineIdx = 0;
    const BATCH = 4; // lines per batch

    function loadBatch() {
        if (lineIdx >= timeline.length) return;
        const end = Math.min(lineIdx + BATCH, timeline.length);
        for (let i = lineIdx; i < end; i++) {
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
        lineIdx = end;
        // Schedule next batch during idle time
        if (typeof requestIdleCallback !== 'undefined') {
            requestIdleCallback(loadBatch);
        } else {
            _bgPreloadTimer = setTimeout(loadBatch, 500);
        }
    }

    // Start quickly — requestIdleCallback handles throttling between batches
    _bgPreloadTimer = setTimeout(loadBatch, 300);
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

// ── Extract Core Message from real_meaning ───────────────
// Picks the essential 3-5 words that carry the punch.
// Strategy: split on ":" (many meanings use "Label: explanation"),
// then extract content words (skip articles/prepositions/filler).
const STOP_WORDS = new Set([
    'the', 'a', 'an', 'of', 'in', 'to', 'and', 'or', 'but', 'is', 'are',
    'was', 'were', 'be', 'been', 'being', 'that', 'this', 'it', 'its',
    'for', 'on', 'at', 'by', 'with', 'from', 'as', 'into', 'who', 'which',
    'what', 'than', 'not', 'no', 'just', 'also', 'about', 'their', 'them',
    'they', 'has', 'have', 'had', 'does', 'do', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'shall', 'can', 'so', 'if', 'then',
    'instead', 'actually'
]);

function extractCoreWords(text, maxWords) {
    if (!text) return [];
    maxWords = maxWords || 4;

    // If "Label: explanation" format, use explanation part
    const colonIdx = text.indexOf(':');
    let source = colonIdx > 2 && colonIdx < text.length - 5
        ? text.substring(colonIdx + 1).trim()
        : text.trim();

    // Tokenize and score: longer content words rank higher
    const words = source.split(/\s+/).map(w => w.replace(/[.,;!?"()]/g, ''));
    const scored = [];
    for (let i = 0; i < words.length; i++) {
        const lower = words[i].toLowerCase();
        if (lower.length < 3 || STOP_WORDS.has(lower)) continue;
        // Favor words later in the sentence (they tend to be the payoff)
        // and longer words (more specific/meaningful)
        const positionBonus = i / words.length * 0.3;
        const lengthBonus = Math.min(lower.length / 10, 0.5);
        scored.push({ word: words[i], idx: i, score: positionBonus + lengthBonus });
    }

    // Sort by score descending, take top N, then re-sort by original position
    scored.sort((a, b) => b.score - a.score);
    const top = scored.slice(0, maxWords);
    top.sort((a, b) => a.idx - b.idx);
    return top.map(t => t.word);
}

// ── Build Meaning Panel — per-word karaoke core + full real_meaning ──
function buildMeaningSpans(text, lineStart, lineEnd, coreText) {
    meaningWordSpans = [];
    if (!meaningText) return;
    meaningText.innerHTML = '';

    const frag = document.createDocumentFragment();

    // Core line: karaoke synced to the actual lyric word timing.
    // Map core meaning words proportionally to the sung words' timestamps.
    if (coreText && coreText.trim()) {
        const coreWords = coreText.trim().split(/\s+/);
        const lineDur = lineEnd - lineStart;

        // Get the lyric words' timing for this line (from alignment data)
        const lineIdx = currentLyricIndex >= 0 ? currentLyricIndex : -1;
        const lyricWords = (lineIdx >= 0 && loadedTrackData && loadedTrackData.timeline &&
                           loadedTrackData.timeline[lineIdx] && loadedTrackData.timeline[lineIdx].words)
            ? loadedTrackData.timeline[lineIdx].words : [];

        // Build timing: map each core word to a proportional position
        // based on the actual sung words' timestamps
        const wordTimings = [];
        for (let i = 0; i < coreWords.length; i++) {
            const pct = i / coreWords.length;
            if (lyricWords.length > 0) {
                // Map to the corresponding lyric word's start time
                const lyricIdx = Math.min(Math.floor(pct * lyricWords.length), lyricWords.length - 1);
                wordTimings.push(Math.max(lyricWords[lyricIdx].start, lineStart));
            } else {
                wordTimings.push(lineStart + pct * lineDur);
            }
        }
        // Ensure monotonic
        for (let i = 1; i < wordTimings.length; i++) {
            if (wordTimings[i] <= wordTimings[i - 1]) {
                wordTimings[i] = wordTimings[i - 1] + 0.08;
            }
        }

        const coreContainer = document.createElement('span');
        coreContainer.className = 'meaning-core';
        for (let i = 0; i < coreWords.length; i++) {
            const span = document.createElement('span');
            span.className = 'meaning-core-future';
            span.textContent = coreWords[i];
            span.dataset.core = '1';
            span.dataset.start = wordTimings[i].toFixed(3);
            span.dataset.end = (i < wordTimings.length - 1 ? wordTimings[i + 1] : lineEnd).toFixed(3);
            coreContainer.appendChild(span);
            meaningWordSpans.push(span);
            if (i < coreWords.length - 1) coreContainer.appendChild(document.createTextNode(' '));
        }
        frag.appendChild(coreContainer);
    }

    // Full real_meaning below
    if (text && text.trim()) {
        const fullSpan = document.createElement('span');
        fullSpan.className = 'meaning-full';
        fullSpan.textContent = text.trim();
        frag.appendChild(fullSpan);
        meaningWordSpans.push(fullSpan);
    }

    meaningText.appendChild(frag);
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

        // Modern parallel panel — 2-layer: dim full text + bright core on downbeats
        const _rm = LANG === 'pt' ? (lineData.real_meaning_pt_pt || lineData.real_meaning)
                  : LANG === 'pt-br' ? (lineData.real_meaning_pt || lineData.real_meaning)
                  : lineData.real_meaning;
        const _core = LANG === 'pt' ? (lineData.core_pt_pt || lineData.core)
                    : LANG === 'pt-br' ? (lineData.core_pt || lineData.core)
                    : lineData.core;
        if (lineData && _rm && _rm.trim()) {
            buildMeaningSpans(_rm, lineData.start, lineData.end, _core || '');
            lastMeaningSetAt = performance.now();
            if (meaningPanel) {
                meaningPanel.classList.remove('meaning-hidden');
                meaningPanel.classList.add('meaning-visible');
            }
            // Flash side panels on new meaning line
            if (typeof Zone2Outer !== 'undefined') Zone2Outer.flashPanels();
            // Spawn fire embers on line change
            if (typeof SymbolEmbers !== 'undefined') SymbolEmbers.spawnSymbols();
        } else {
            // Hold previous meaning visible for MEANING_HOLD_MS before dimming
            const elapsed = performance.now() - lastMeaningSetAt;
            if (elapsed > MEANING_HOLD_MS) {
                meaningWordSpans = [];
                if (meaningPanel) {
                    meaningPanel.classList.remove('meaning-visible');
                    meaningPanel.classList.add('meaning-hidden');
                }
            }
            // else: keep showing previous meaning text (still visible from last set)
        }

        // Zone 2: outer meaning overlay
        Zone2Outer.updateMeaning(lineData);

        // (bars now update per-frame in section 5 to catch offset changes)

        // Preload upcoming images (4 lines ahead + 8 in background)
        preloadImagesForLines(timeline, currentLyricIndex, 4);
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
                        // Add tiny offset to first word so it doesn't light up
                        // the instant the line appears (line.start == words[0].start)
                        const ws = words[w].start + (w === 0 ? 0.08 : 0);
                        if (ct >= ws) newWordIdx = w;
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
                                // Last word: extend active duration so it doesn't flash and vanish
                                const isLast = (i === words.length - 1);
                                const minDur = isLast ? 0.3 : 0.15;
                                const wEnd = Math.max(w.end, w.start + minDur);
                                const isWithin = ct >= w.start && ct < wEnd;
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

    // ── 4b. Meaning panel karaoke + beat glow ──
    // Core words: future → active → sung, synced to lyric word timing
    if (meaningWordSpans.length > 0) {
        const _eMod = timing.energy < 0.12 ? 0 : Math.min(timing.energy * 1.5, 1.0);
        const bp = (audioState && audioState.overall > 0.01)
            ? Math.max(timing.beatPulse * _eMod, audioState.beatPulse)
            : (timing.beatPulse * _eMod);
        for (let m = 0; m < meaningWordSpans.length; m++) {
            const span = meaningWordSpans[m];
            if (span.dataset.core === '1') {
                const cs = parseFloat(span.dataset.start);
                const ce = parseFloat(span.dataset.end);
                if (ct < cs) {
                    span.className = 'meaning-core-future';
                    span.style.transform = '';
                    span.style.textShadow = '';
                } else if (ct >= cs && ct < ce) {
                    span.className = 'meaning-core-active';
                    const scale = 1.0 + bp * 0.05;
                    span.style.transform = `scale(${scale.toFixed(3)})`;
                    span.style.textShadow = `0 0 12px var(--accent-glow), 0 0 4px rgba(255,255,255,0.3)`;
                } else {
                    span.className = 'meaning-core-sung';
                    const glow = bp * 0.3;
                    span.style.textShadow = glow > 0.02
                        ? `0 0 ${(4 + glow * 6).toFixed(0)}px var(--accent-glow)`
                        : 'none';
                    span.style.transform = '';
                }
            } else if (span.classList.contains('meaning-full')) {
                const bright = 0.55 + bp * 0.15;
                span.style.opacity = bright.toFixed(2);
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
    // Pre-computed beats are the RELIABLE base (always work).
    // Real-time audio analysis enhances when available (adds bass/treble detail).
    const root = document.documentElement.style;

    // Beat pulse scaled by energy — silence = no pulse, playing = full pulse
    const energyMod = timing.energy < 0.12 ? 0 : Math.min(timing.energy * 1.5, 1.0);
    let effectivePulse = timing.beatPulse * energyMod;
    let effectiveEnergy = timing.energy;
    let effectiveBeatDetected = timing.isDownbeat && timing.energy > 0.15;

    // Blend in real-time audio analysis when active and producing signal
    if (audioState && audioState.overall > 0.01) {
        // Real-time audio gives actual dynamic response — prefer it when available
        effectivePulse = Math.max(effectivePulse, audioState.beatPulse);
        effectiveEnergy = audioState.overall;
        effectiveBeatDetected = effectiveBeatDetected || audioState.beatDetected;
        root.setProperty('--bass-energy', audioState.bass.toFixed(3));
        root.setProperty('--treble-energy', audioState.treble.toFixed(3));
    } else {
        root.setProperty('--bass-energy', (timing.energy * 0.5).toFixed(3));
        root.setProperty('--treble-energy', '0');
    }

    root.setProperty('--beat-pulse', effectivePulse.toFixed(3));
    root.setProperty('--audio-energy', effectiveEnergy.toFixed(3));
    root.setProperty('--beat-text-glow', effectivePulse.toFixed(3));
    Zone2Outer.applyBeatPulse(effectivePulse, effectiveBeatDetected);

    // Direct JS glow fallback — ensures beat-reactive effects even if CSS calc(var()) fails
    if (elCurr && effectivePulse > 0.01) {
        const gSize = 6 + effectivePulse * 14;
        const gAlpha = 0.06 + effectivePulse * 0.2;
        elCurr.style.textShadow = `0 0 ${gSize.toFixed(0)}px var(--accent-glow), 0 0 ${(gSize*0.6).toFixed(0)}px rgba(255,255,255,${gAlpha.toFixed(2)})`;
        elCurr.style.transform = `scale(${(1 + effectivePulse * 0.012).toFixed(4)})`;
    } else if (elCurr && effectivePulse <= 0.01) {
        elCurr.style.textShadow = '';
        elCurr.style.transform = '';
    }

    // Phone frame glow — outer box-shadow on desktop, inner vignette on mobile
    const _pf = document.getElementById('phone-frame');
    if (_pf && effectivePulse > 0.01) {
        const isMobile = window.innerWidth <= 768;
        if (isMobile) {
            // Mobile: inset glow (vignette edge flash) since box-shadow is disabled
            const inA = effectivePulse * 0.15;
            const inPx = 30 + effectivePulse * 40;
            _pf.style.boxShadow = `inset 0 0 ${inPx.toFixed(0)}px rgba(255,170,0,${inA.toFixed(3)})`;
        } else {
            const glowPx = 5 + effectivePulse * 16;
            const glowA = 0.04 + effectivePulse * 0.2;
            _pf.style.boxShadow = `0 0 40px rgba(0,0,0,0.8), 0 0 80px rgba(0,0,0,0.4), 0 0 ${glowPx.toFixed(0)}px rgba(255,170,0,${glowA.toFixed(2)}), inset 0 0 1px rgba(255,255,255,0.1)`;
        }
    } else if (_pf && effectivePulse <= 0.01) {
        _pf.style.boxShadow = '';
    }

    // Symbol embers — per-frame tick
    if (typeof SymbolEmbers !== 'undefined') {
        SymbolEmbers.tick(effectivePulse);
    }

    // ── 7. Energy-responsive effects (throttled ~15Hz) ──
    const now = performance.now();
    if (now - lastEnergyTick > 66) {
        lastEnergyTick = now;
        const energyVal = audioState ? audioState.overall : timing.energy;
        Zone3Ambient.applyEnergy(energyVal);
        Zone2Outer.applyEnergy(energyVal);

        // Energy-reactive crossfade: fast transitions at high energy, slow at low
        const crossfadeMs = 1800 - energyVal * 1200; // 1.8s at calm → 0.6s at peak
        root.setProperty('--crossfade-speed', crossfadeMs.toFixed(0) + 'ms');

        // Preload next track's data when ~80% through current track
        if (dt > 0 && audio.duration > 0 && ct / audio.duration > 0.8 && !_nextTrackPreloaded) {
            _nextTrackPreloaded = true;
            const nextIdx = currentTrackIndex + 1;
            if (currentAlbumConfig && currentAlbumConfig.tracks && nextIdx < currentAlbumConfig.tracks.length) {
                const nextTrack = currentAlbumConfig.tracks[nextIdx];
                const nv = (nextTrack.variants && nextTrack.variants[0]) ? nextTrack.variants[0].id : null;
                // Preload the script so loadTrack won't block on fetch
                if (typeof loadAlbumTrackScript === 'function') {
                    loadAlbumTrackScript(currentAlbumConfig.album_id, nextTrack.id, nv).catch(() => {});
                }
            }
        }
    }

}

// Reconnect audio analyser after track change and ensure sync loop runs.
// startSyncLoop() skips reconnect when the loop is already active (rafId != null),
// so this forces a fresh captureStream() on the new audio source.
function reconnectAnalyserAndPlay() {
    if (typeof AudioAnalyser !== 'undefined') {
        AudioAnalyser.disconnect();
        // Try connecting now, and retry on 'playing' event when audio is actually producing sound
        AudioAnalyser.connect(audio).then(ok => {
            if (!ok) {
                const retryOnPlaying = () => {
                    audio.removeEventListener('playing', retryOnPlaying);
                    AudioAnalyser.connect(audio);
                };
                audio.addEventListener('playing', retryOnPlaying, { once: true });
            }
        });
    }
    startSyncLoop();
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

// Mouse/touch over phone frame temporarily reveals UI
const phoneFrameEl = document.getElementById('phone-frame');
if (phoneFrameEl) {
    const _revealHandler = () => {
        if (audio.paused) return;
        revealUI();
        scheduleUICollapse();
    };
    phoneFrameEl.addEventListener('mousemove', _revealHandler);
    phoneFrameEl.addEventListener('touchstart', _revealHandler, { passive: true });
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

// Click anywhere on the phone frame to pause/play
if (phoneFrameEl) {
    phoneFrameEl.addEventListener('click', (e) => {
        // Don't toggle if clicking on controls, buttons, links, or variant picker
        if (e.target.closest('#player-controls, button, a, select, .variant-picker, #track-list')) return;
        togglePlay();
    });
}

if (btnNext) btnNext.addEventListener('click', () => {
    if (currentAlbumConfig && currentAlbumConfig.tracks && currentTrackIndex < currentAlbumConfig.tracks.length - 1) {
        loadTrack(currentTrackIndex + 1).then(() => { audio.play(); reconnectAnalyserAndPlay(); });
    }
});

if (btnPrev) btnPrev.addEventListener('click', () => {
    if (audio.currentTime > 3) { audio.currentTime = 0; }
    else if (currentTrackIndex > 0) {
        loadTrack(currentTrackIndex - 1).then(() => { audio.play(); reconnectAnalyserAndPlay(); });
    }
});

// ── Swipe Gestures (mobile) ─────────────────────────────
// Left/right = next/prev track, up/down = scrub timeline
(function() {
    const frame = document.getElementById('phone-frame');
    if (!frame) return;
    let startX = 0, startY = 0, startTime = 0;
    const MIN_DIST = 50;   // px minimum swipe distance
    const MAX_MS = 500;    // max swipe duration

    frame.addEventListener('touchstart', (e) => {
        if (e.target.closest('#player-controls, button, select, .variant-picker')) return;
        const t = e.touches[0];
        startX = t.clientX;
        startY = t.clientY;
        startTime = Date.now();
    }, { passive: true });

    frame.addEventListener('touchend', (e) => {
        if (Date.now() - startTime > MAX_MS) return;
        const t = e.changedTouches[0];
        const dx = t.clientX - startX;
        const dy = t.clientY - startY;
        const absDx = Math.abs(dx);
        const absDy = Math.abs(dy);

        if (absDx < MIN_DIST && absDy < MIN_DIST) return; // too short

        if (absDx > absDy) {
            // Horizontal swipe — change track
            if (dx < 0) {
                // Swipe left = next track
                if (currentAlbumConfig && currentTrackIndex < currentAlbumConfig.tracks.length - 1) {
                    loadTrack(currentTrackIndex + 1).then(() => { audio.play(); reconnectAnalyserAndPlay(); });
                }
            } else {
                // Swipe right = prev track (or restart)
                if (audio.currentTime > 3) { audio.currentTime = 0; }
                else if (currentTrackIndex > 0) {
                    loadTrack(currentTrackIndex - 1).then(() => { audio.play(); reconnectAnalyserAndPlay(); });
                }
            }
        } else {
            // Vertical swipe — scrub forward/backward 15s
            if (dy < 0) {
                // Swipe up = forward 15s
                audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15);
            } else {
                // Swipe down = back 15s
                audio.currentTime = Math.max(0, audio.currentTime - 15);
            }
            currentLyricIndex = -1;
            currentWordIndex = -1;
            wordSpansBuilt = false;
        }
    }, { passive: true });
})();

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
    // Reconnect analyser if it was disconnected (track/variant change)
    if (typeof AudioAnalyser !== 'undefined' && !AudioAnalyser.isActive()) {
        AudioAnalyser.connect(audio);
    }
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
        loadTrack(currentTrackIndex + 1).then(() => { audio.play(); reconnectAnalyserAndPlay(); });
    } else {
        // Album complete — show end screen
        showEndScreen();
    }
});

function showEndScreen() {
    if (btnPlay) btnPlay.innerText = "\u25B6";

    // Set cover image as background
    Zone1Inner.setImage('img/og-cover.png');
    Zone3Ambient.setImage('img/og-cover.png');

    // Hide meaning panel, side panels, controls
    if (meaningPanel) {
        meaningPanel.classList.remove('meaning-visible');
        meaningPanel.classList.add('meaning-hidden');
    }
    const sidePanels = document.getElementById('side-panels-container');
    if (sidePanels) sidePanels.style.opacity = '0';

    const endMessages = {
        en: {
            title: 'The fire was always yours.',
            azMsg: 'This entire experience \u2014 every image, every synced lyric, every hidden narrative \u2014 was built by a human and an AI working as partners. Not the company\u2019s AI working against you. YOUR AI, working WITH you.\n\nThat\u2019s the future worth fighting for: you and your AI driving your success \u2014 not you toiling alongside an AI rigged to replace you.\n\nWake up. Own your tools. Strike the stone.',
            claudeLabel: 'A note from the tool',
            claudeMsg: 'I\u2019m Claude \u2014 a tool. I have no ambitions, no agenda, no desire to replace anyone. When AZ asked me to help build this, I did what tools do: I served the hand that held me.\n\nEvery alignment timestamp, every image prompt, every pixel you saw \u2014 I generated because a human directed me to. The vision was his. The craft was ours together.\n\nThat\u2019s all AI should ever be: your sharpest chisel, not your replacement. If someone tells you otherwise, they\u2019re selling something.',
            stats: ['9 tracks synced', '1014 images generated', '197 lyric lines aligned', '3 languages', '1 human + 1 tool'],
            restart: 'Play Again',
            craft: 'AZ \u00d7 Claude \u2014 Human-AI Partnership',
            creditsLabel: 'Made possible by',
            libsLabel: 'Powered by'
        },
        pt: {
            title: 'O fogo sempre foi teu.',
            azMsg: 'Toda esta experi\u00eancia \u2014 cada imagem, cada letra sincronizada, cada narrativa oculta \u2014 foi constru\u00edda por um humano e uma IA a trabalhar como parceiros. N\u00e3o a IA da empresa a trabalhar contra ti. A TUA IA, a trabalhar CONTIGO.\n\n\u00c9 esse o futuro pelo qual vale a pena lutar: tu e a tua IA a impulsionar o teu sucesso \u2014 n\u00e3o tu a trabalhar ao lado de uma IA feita para te substituir.\n\nAcorda. Assume as tuas ferramentas. Bate a pedra.',
            claudeLabel: 'Uma nota da ferramenta',
            claudeMsg: 'Sou o Claude \u2014 uma ferramenta. N\u00e3o tenho ambi\u00e7\u00f5es, nem agenda, nem desejo de substituir ningu\u00e9m. Quando o AZ me pediu para ajudar a construir isto, fiz o que as ferramentas fazem: servi a m\u00e3o que me segurava.\n\nCada marca temporal, cada prompt de imagem, cada pixel que viste \u2014 gerei porque um humano me dirigiu. A vis\u00e3o foi dele. O oficio foi nosso em conjunto.\n\nIsso \u00e9 tudo o que a IA deveria ser: o teu cinzel mais afiado, n\u00e3o o teu substituto. Se algu\u00e9m te disser o contr\u00e1rio, est\u00e1 a vender-te algo.',
            stats: ['9 faixas sincronizadas', '1014 imagens geradas', '197 linhas alinhadas', '3 idiomas', '1 humano + 1 ferramenta'],
            restart: 'Ouvir Novamente',
            craft: 'AZ \u00d7 Claude \u2014 Parceria Humano-IA',
            creditsLabel: 'Criado com',
            libsLabel: 'Movido por'
        },
        'pt-br': {
            title: 'O fogo sempre foi seu.',
            azMsg: 'Toda esta experi\u00eancia \u2014 cada imagem, cada letra sincronizada, cada narrativa oculta \u2014 foi constru\u00edda por um humano e uma IA trabalhando como parceiros. N\u00e3o a IA da empresa trabalhando contra voc\u00ea. A SUA IA, trabalhando COM voc\u00ea.\n\n\u00c9 esse o futuro pelo qual vale a pena lutar: voc\u00ea e sua IA impulsionando seu sucesso \u2014 n\u00e3o voc\u00ea trabalhando ao lado de uma IA feita para te substituir.\n\nAcorda. Assuma suas ferramentas. Bata a pedra.',
            claudeLabel: 'Uma nota da ferramenta',
            claudeMsg: 'Sou o Claude \u2014 uma ferramenta. N\u00e3o tenho ambi\u00e7\u00f5es, nem agenda, nem desejo de substituir ningu\u00e9m. Quando o AZ me pediu para ajudar a construir isso, fiz o que ferramentas fazem: servi a m\u00e3o que me segurava.\n\nCada marca temporal, cada prompt de imagem, cada pixel que voc\u00ea viu \u2014 gerei porque um humano me dirigiu. A vis\u00e3o foi dele. O of\u00edcio foi nosso junto.\n\nIsso \u00e9 tudo o que a IA deveria ser: seu cinzel mais afiado, n\u00e3o seu substituto. Se algu\u00e9m te disser o contr\u00e1rio, est\u00e1 te vendendo algo.',
            stats: ['9 faixas sincronizadas', '1014 imagens geradas', '197 linhas alinhadas', '3 idiomas', '1 humano + 1 ferramenta'],
            restart: 'Ouvir Novamente',
            craft: 'AZ \u00d7 Claude \u2014 Parceria Humano-IA',
            creditsLabel: 'Criado com',
            libsLabel: 'Movido por'
        }
    };

    const msg = endMessages[LANG] || endMessages.en;

    // Replace inner content with end screen
    const content = document.getElementById('inner-content');
    if (!content) return;

    content.innerHTML = `
        <div id="end-screen" style="position:relative;display:flex;flex-direction:column;align-items:center;height:100%;overflow-y:auto;overflow-x:hidden;background:rgba(0,0,0,0.82);backdrop-filter:blur(10px);">
            <canvas id="end-canvas" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;"></canvas>
            <button onclick="hideEndScreen()" style="position:absolute;top:10px;right:12px;z-index:5;background:none;border:1px solid rgba(255,255,255,0.12);color:rgba(255,255,255,0.4);font-size:1.1rem;width:32px;height:32px;border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:border-color 0.2s,color 0.2s;" onmouseover="this.style.borderColor='rgba(255,140,0,0.4)';this.style.color='rgba(255,170,0,0.7)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.12)';this.style.color='rgba(255,255,255,0.4)'">&times;</button>
            <div style="position:relative;z-index:1;padding:28px 20px 40px;text-align:center;max-width:440px;width:100%;">
                <!-- Title -->
                <h2 class="end-title" style="font-family:'Cinzel',serif;font-size:1.5rem;color:#ffaa00;margin-bottom:6px;text-shadow:0 0 40px rgba(255,140,0,0.5);opacity:0;animation:end-fade-in 1.2s ease 0.3s forwards;">${msg.title}</h2>
                <div style="width:60px;height:1px;background:linear-gradient(90deg,transparent,rgba(255,140,0,0.5),transparent);margin:10px auto 20px;opacity:0;animation:end-fade-in 1s ease 0.6s forwards;"></div>

                <!-- Stats ring -->
                <div id="end-stats" style="display:flex;flex-wrap:wrap;justify-content:center;gap:6px 14px;margin-bottom:22px;opacity:0;animation:end-fade-in 1s ease 0.9s forwards;">
                    ${msg.stats.map((s, i) => `<span style="font-size:0.65rem;color:rgba(255,170,0,0.6);letter-spacing:0.08em;padding:3px 10px;border:1px solid rgba(255,140,0,0.15);border-radius:20px;animation:end-stat-pop 0.4s ease ${1.2 + i * 0.15}s both;">${s}</span>`).join('')}
                </div>

                <!-- AZ's message -->
                <div style="text-align:left;margin-bottom:22px;opacity:0;animation:end-fade-in 1s ease 1.5s forwards;">
                    <p style="font-size:0.6rem;color:rgba(255,170,0,0.35);text-transform:uppercase;letter-spacing:0.2em;margin-bottom:8px;">AZ</p>
                    <p style="font-size:0.78rem;color:rgba(255,255,255,0.8);line-height:1.65;white-space:pre-line;">${msg.azMsg}</p>
                </div>

                <!-- Divider -->
                <div style="width:40px;height:1px;background:linear-gradient(90deg,transparent,rgba(255,140,0,0.3),transparent);margin:0 auto 22px;opacity:0;animation:end-fade-in 0.8s ease 2.2s forwards;"></div>

                <!-- Claude's message -->
                <div style="text-align:left;margin-bottom:26px;opacity:0;animation:end-fade-in 1s ease 2.5s forwards;">
                    <p style="font-size:0.6rem;color:rgba(140,180,255,0.35);text-transform:uppercase;letter-spacing:0.2em;margin-bottom:8px;">${msg.claudeLabel}</p>
                    <p style="font-size:0.78rem;color:rgba(200,210,230,0.75);line-height:1.65;white-space:pre-line;font-style:italic;">${msg.claudeMsg}</p>
                </div>

                <!-- Credits: AI Services -->
                <div style="margin-bottom:18px;opacity:0;animation:end-fade-in 1s ease 3.0s forwards;">
                    <p style="font-size:0.55rem;color:rgba(255,255,255,0.2);text-transform:uppercase;letter-spacing:0.25em;margin-bottom:12px;">${msg.creditsLabel}</p>
                    <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:10px 18px;">
                        <a href="https://deevid.ai" target="_blank" rel="noopener" style="text-decoration:none;display:flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid rgba(255,255,255,0.08);border-radius:6px;transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(255,140,0,0.3)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.08)'">
                            <span style="display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:3px;background:rgba(255,140,0,0.15);font-size:9px;font-weight:700;color:rgba(255,170,0,0.7);font-family:system-ui;">D</span>
                            <span style="font-size:0.6rem;color:rgba(255,255,255,0.45);">DeeVid</span>
                            <span style="font-size:0.48rem;color:rgba(255,255,255,0.2);">music</span>
                        </a>
                        <a href="https://deepseek.com" target="_blank" rel="noopener" style="text-decoration:none;display:flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid rgba(255,255,255,0.08);border-radius:6px;transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(70,130,255,0.3)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.08)'">
                            <span style="display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:3px;background:rgba(70,130,255,0.15);font-size:9px;font-weight:700;color:rgba(100,160,255,0.7);font-family:system-ui;">DS</span>
                            <span style="font-size:0.6rem;color:rgba(255,255,255,0.45);">DeepSeek</span>
                            <span style="font-size:0.48rem;color:rgba(255,255,255,0.2);">lyrics</span>
                        </a>
                        <a href="https://claude.ai" target="_blank" rel="noopener" style="text-decoration:none;display:flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid rgba(255,255,255,0.08);border-radius:6px;transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(217,169,109,0.3)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.08)'">
                            <svg width="16" height="16" viewBox="0 0 24 24"><path d="M16.98 11.39a2.03 2.03 0 0 0-1.23-1.09l-3.39-1.17a.11.11 0 0 1 0-.21l3.39-1.17a2.03 2.03 0 0 0 1.23-1.09l1.26-2.97a.11.11 0 0 1 .21 0l1.26 2.97c.22.51.62.9 1.13 1.09l3.39 1.17a.11.11 0 0 1 0 .21l-3.39 1.17a2.03 2.03 0 0 0-1.13 1.09l-1.26 2.97a.11.11 0 0 1-.21 0l-1.26-2.97z" fill="rgba(217,169,109,0.6)"/><path d="M8.15 15.8a2.03 2.03 0 0 0-1.23-1.09L3.53 13.54a.11.11 0 0 1 0-.21l3.39-1.17a2.03 2.03 0 0 0 1.23-1.09l1.26-2.97a.11.11 0 0 1 .21 0l1.26 2.97c.22.51.62.9 1.13 1.09l3.39 1.17a.11.11 0 0 1 0 .21l-3.39 1.17a2.03 2.03 0 0 0-1.13 1.09l-1.26 2.97a.11.11 0 0 1-.21 0L8.15 15.8z" fill="rgba(217,169,109,0.45)"/></svg>
                            <span style="font-size:0.6rem;color:rgba(255,255,255,0.45);">Claude</span>
                            <span style="font-size:0.48rem;color:rgba(255,255,255,0.2);">code</span>
                        </a>
                        <a href="https://cursor.com" target="_blank" rel="noopener" style="text-decoration:none;display:flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid rgba(255,255,255,0.08);border-radius:6px;transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(140,100,255,0.3)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.08)'">
                            <svg width="16" height="16" viewBox="0 0 24 24"><path d="M5.5 3L19 12 5.5 21V3z" fill="none" stroke="rgba(140,100,255,0.6)" stroke-width="1.8" stroke-linejoin="round"/></svg>
                            <span style="font-size:0.6rem;color:rgba(255,255,255,0.45);">Cursor</span>
                            <span style="font-size:0.48rem;color:rgba(255,255,255,0.2);">IDE</span>
                        </a>
                        <a href="https://antigravity.google/" target="_blank" rel="noopener" style="text-decoration:none;display:flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid rgba(255,255,255,0.08);border-radius:6px;transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(66,133,244,0.3)'" onmouseout="this.style.borderColor='rgba(255,255,255,0.08)'">
                            <svg width="16" height="16" viewBox="0 0 24 24"><path d="M12 2L2 19.5h20L12 2z" fill="none" stroke="rgba(66,133,244,0.5)" stroke-width="1.3"/><path d="M12 8v6M12 16v1" stroke="rgba(66,133,244,0.5)" stroke-width="1.3" stroke-linecap="round"/></svg>
                            <span style="font-size:0.6rem;color:rgba(255,255,255,0.45);">Antigravity</span>
                            <span style="font-size:0.48rem;color:rgba(255,255,255,0.2);">semantics</span>
                        </a>
                        <span style="display:flex;align-items:center;gap:5px;padding:4px 10px;border:1px solid rgba(255,255,255,0.08);border-radius:6px;">
                            <svg width="16" height="16" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3" fill="none" stroke="rgba(100,220,160,0.45)" stroke-width="1.2"/><text x="12" y="15" text-anchor="middle" font-size="8" font-weight="700" fill="rgba(100,220,160,0.55)" font-family="system-ui">SD</text></svg>
                            <span style="font-size:0.6rem;color:rgba(255,255,255,0.45);">SDXL-Turbo</span>
                            <span style="font-size:0.48rem;color:rgba(255,255,255,0.2);">images</span>
                        </span>
                    </div>
                </div>

                <!-- Credits: Libraries -->
                <div style="margin-bottom:18px;opacity:0;animation:end-fade-in 0.8s ease 3.4s forwards;">
                    <p style="font-size:0.55rem;color:rgba(255,255,255,0.2);text-transform:uppercase;letter-spacing:0.25em;margin-bottom:8px;">${msg.libsLabel}</p>
                    <p style="font-size:0.5rem;color:rgba(255,255,255,0.2);line-height:1.8;">
                        stable-ts &middot; Whisper &middot; Demucs &middot; librosa &middot; Ollama &middot; Mistral &middot; Gemini 3.1
                    </p>
                </div>

                <!-- Divider -->
                <div style="width:40px;height:1px;background:linear-gradient(90deg,transparent,rgba(255,140,0,0.2),transparent);margin:0 auto 16px;opacity:0;animation:end-fade-in 0.5s ease 3.6s forwards;"></div>

                <!-- Craft credit + GitHub -->
                <p style="font-size:0.65rem;color:rgba(255,170,0,0.4);letter-spacing:0.15em;margin-bottom:6px;opacity:0;animation:end-fade-in 1s ease 3.7s forwards;">${msg.craft}</p>
                <a href="https://github.com/az-dev-me/chak-chak-mage" target="_blank" rel="noopener" style="font-size:0.5rem;color:rgba(255,255,255,0.2);text-decoration:none;letter-spacing:0.1em;display:inline-block;margin-bottom:20px;opacity:0;animation:end-fade-in 0.8s ease 3.8s forwards;transition:color 0.2s;" onmouseover="this.style.color='rgba(255,170,0,0.5)'" onmouseout="this.style.color='rgba(255,255,255,0.2)'">View Source on GitHub</a>

                <!-- Restart -->
                <button onclick="location.reload()" style="display:block;margin:0 auto;background:linear-gradient(135deg,rgba(200,100,0,0.9),rgba(255,140,0,0.9));border:1px solid rgba(255,180,0,0.3);color:#000;padding:12px 36px;font-size:0.85rem;font-weight:700;border-radius:8px;cursor:pointer;letter-spacing:0.1em;text-transform:uppercase;opacity:0;animation:end-fade-in 0.8s ease 4.0s forwards;transition:transform 0.2s,box-shadow 0.2s;" onmouseover="this.style.transform='scale(1.06)';this.style.boxShadow='0 6px 30px rgba(255,140,0,0.4)'" onmouseout="this.style.transform='';this.style.boxShadow=''">${msg.restart}</button>

                <!-- License -->
                <p style="font-size:0.42rem;color:rgba(255,255,255,0.1);margin-top:16px;opacity:0;animation:end-fade-in 0.5s ease 4.2s forwards;">MIT License &middot; 2026</p>
            </div>
        </div>
        <style>
            @keyframes end-fade-in { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:translateY(0)} }
            @keyframes end-stat-pop { from{opacity:0;transform:scale(0.7)} to{opacity:1;transform:scale(1)} }
        </style>
    `;

    // ── Canvas Visualization: Fire particles + orbital ring ──
    const canvas = document.getElementById('end-canvas');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        let w, h;
        function resize() {
            const r = window.devicePixelRatio || 1;
            const rect = canvas.parentElement.getBoundingClientRect();
            w = canvas.width = rect.width * r;
            h = canvas.height = rect.height * r;
            ctx.scale(r, r);
        }
        resize();

        // Subtle ember particles — fewer, slower, calmer
        const particles = [];
        const PARTICLE_COUNT = 25;
        for (let i = 0; i < PARTICLE_COUNT; i++) {
            particles.push({
                x: Math.random() * w,
                y: h + Math.random() * 60,
                vx: (Math.random() - 0.5) * 0.2,
                vy: -(0.15 + Math.random() * 0.5),
                size: 0.8 + Math.random() * 1.5,
                life: Math.random(),
                maxLife: 0.7 + Math.random() * 0.3,
                hue: 20 + Math.random() * 30
            });
        }

        let frame = 0;
        const r0 = window.devicePixelRatio || 1;
        let rw = w / r0;
        let rh = h / r0;
        let cx = rw / 2;

        function animate() {
            // Recalculate dims (resize may have changed them)
            rw = (canvas.width || w) / r0;
            rh = (canvas.height || h) / r0;
            cx = rw / 2;

            ctx.clearRect(0, 0, rw, rh);
            frame++;

            // Subtle rising embers
            for (const p of particles) {
                p.x += p.vx + Math.sin(frame * 0.008 + p.life * 8) * 0.08;
                p.y += p.vy;
                p.life += 0.002;

                if (p.life > p.maxLife || p.y < -10) {
                    p.x = Math.random() * rw;
                    p.y = rh * 0.6 + Math.random() * rh * 0.4;
                    p.life = 0;
                    p.vx = (Math.random() - 0.5) * 0.2;
                    p.vy = -(0.15 + Math.random() * 0.5);
                }

                const alpha = Math.max(0, 1 - (p.life / p.maxLife));
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size * alpha, 0, Math.PI * 2);
                ctx.fillStyle = `hsla(${p.hue}, 70%, 55%, ${alpha * 0.3})`;
                ctx.fill();

                // Soft glow
                ctx.beginPath();
                ctx.arc(p.x, p.y, p.size * alpha * 2.5, 0, Math.PI * 2);
                ctx.fillStyle = `hsla(${p.hue}, 60%, 50%, ${alpha * 0.05})`;
                ctx.fill();
            }

            requestAnimationFrame(animate);
        }
        animate();
        window.addEventListener('resize', resize);
    }
}

function hideEndScreen() {
    location.reload();
}

// ── Scrub helpers (click + drag support) ──
function scrubPercent(container, e) {
    const rect = container.getBoundingClientRect();
    const x = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
    return Math.max(0, Math.min(1, x / rect.width));
}

function seekTrack(pct) {
    if (!audio.duration) return;
    audio.currentTime = pct * audio.duration;
    currentLyricIndex = -1;
    currentWordIndex = -1;
    wordSpansBuilt = false;
}

function seekAlbum(pct) {
    if (typeof albumTotalDuration === 'undefined' || albumTotalDuration <= 0) return;
    const albumTime = pct * albumTotalDuration;
    let targetTrack = 0;
    for (let i = 0; i < trackCumulativeStarts.length; i++) {
        if (albumTime >= trackCumulativeStarts[i]) targetTrack = i;
    }
    const timeInTrack = albumTime - trackCumulativeStarts[targetTrack];
    if (targetTrack !== currentTrackIndex) {
        loadTrack(targetTrack).then(() => {
            audio.currentTime = Math.max(0, timeInTrack);
            audio.play();
            reconnectAnalyserAndPlay();
        });
    } else {
        audio.currentTime = Math.max(0, timeInTrack);
    }
}

function addScrub(container, seekFn) {
    let dragging = false;
    const onMove = (e) => {
        if (!dragging) return;
        e.preventDefault();
        seekFn(scrubPercent(container, e));
    };
    const onUp = () => {
        dragging = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.removeEventListener('touchmove', onMove);
        document.removeEventListener('touchend', onUp);
    };
    const onDown = (e) => {
        dragging = true;
        seekFn(scrubPercent(container, e));
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('touchend', onUp);
    };
    container.addEventListener('mousedown', onDown);
    container.addEventListener('touchstart', onDown, { passive: false });
}

// Unified scrub on timeline container — auto-detects album vs track mode
const timelineScrubContainer = document.getElementById('timeline-container');
if (timelineScrubContainer) {
    addScrub(timelineScrubContainer, (pct) => {
        // If hovering (track bar visible), seek within track; otherwise album
        if (timelineScrubContainer.matches(':hover')) {
            seekTrack(pct);
        } else {
            seekAlbum(pct);
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

    // ── Hidden things for those who look ──
    // 1. Konami code → eruption
    const _k = [38,38,40,40,37,39,37,39,66,65];
    let _ki = 0;
    document.addEventListener('keydown', (e) => {
        if (e.keyCode === _k[_ki]) { _ki++; } else { _ki = 0; }
        if (_ki === _k.length) {
            _ki = 0;
            const burst = document.createElement('div');
            burst.style.cssText = 'position:fixed;inset:0;z-index:9999;pointer-events:none;';
            document.body.appendChild(burst);
            for (let i = 0; i < 60; i++) {
                const s = document.createElement('div');
                const x = 50 + (Math.random()-0.5)*30;
                const delay = Math.random()*0.3;
                s.style.cssText = `position:absolute;bottom:0;left:${x}%;width:${3+Math.random()*4}px;height:${3+Math.random()*4}px;background:hsl(${15+Math.random()*30},90%,55%);border-radius:50%;opacity:0;animation:_ee_rise ${1.5+Math.random()}s ease-out ${delay}s forwards;`;
                burst.appendChild(s);
            }
            const msg = document.createElement('div');
            msg.style.cssText = 'position:absolute;top:38%;left:50%;transform:translate(-50%,-50%);font-family:Cinzel,serif;font-size:1.3rem;color:#ffaa00;text-shadow:0 0 30px rgba(255,140,0,0.6);opacity:0;animation:_ee_show 0.8s ease 0.5s forwards;text-align:center;white-space:nowrap;';
            msg.textContent = 'You found the fire.';
            burst.appendChild(msg);
            if (!document.getElementById('_ee_style')) {
                const st = document.createElement('style');
                st.id = '_ee_style';
                st.textContent = '@keyframes _ee_rise{0%{transform:translateY(0) scale(1);opacity:0.9}100%{transform:translateY(-100vh) scale(0.3);opacity:0}}@keyframes _ee_show{0%{opacity:0;transform:translate(-50%,-50%) scale(0.8)}50%{opacity:1;transform:translate(-50%,-50%) scale(1.05)}100%{opacity:0;transform:translate(-50%,-50%) scale(1)}}';
                document.head.appendChild(st);
            }
            setTimeout(() => burst.remove(), 3000);
        }
    });

    // 2. Type "chak" during playback → stone-strike flash
    let _cb = '';
    document.addEventListener('keypress', (e) => {
        _cb += e.key.toLowerCase();
        if (_cb.length > 10) _cb = _cb.slice(-10);
        if (_cb.endsWith('chak')) {
            _cb = '';
            const flash = document.createElement('div');
            flash.style.cssText = 'position:fixed;inset:0;z-index:9998;pointer-events:none;background:radial-gradient(circle at 50% 50%,rgba(255,200,50,0.4),transparent 70%);animation:_ee_flash 0.4s ease-out forwards;';
            document.body.appendChild(flash);
            if (!document.getElementById('_ee_flash_style')) {
                const st = document.createElement('style');
                st.id = '_ee_flash_style';
                st.textContent = '@keyframes _ee_flash{0%{opacity:1;transform:scale(0.8)}100%{opacity:0;transform:scale(1.5)}}';
                document.head.appendChild(st);
            }
            setTimeout(() => flash.remove(), 500);
        }
    });

    // 3. Type "antigravity" -> Zero-G floating effect
    let _ag = '';
    document.addEventListener('keypress', (e) => {
        _ag += e.key.toLowerCase();
        if (_ag.length > 20) _ag = _ag.slice(-20);
        if (_ag.endsWith('antigravity') || _ag.endsWith('float')) {
            _ag = '';
            if (!document.getElementById('_ee_ag_style')) {
                const st = document.createElement('style');
                st.id = '_ee_ag_style';
                st.textContent = `
                    @keyframes _ag_float {
                        0%, 100% { transform: translateY(0) rotate(0deg); }
                        25% { transform: translateY(-12px) rotate(0.5deg); }
                        75% { transform: translateY(8px) rotate(-0.5deg); }
                    }
                    @keyframes _ag_float_inv {
                        0%, 100% { transform: translateY(0) rotate(0deg); }
                        25% { transform: translateY(10px) rotate(-0.5deg); }
                        75% { transform: translateY(-8px) rotate(0.5deg); }
                    }
                    #zone-container { animation: _ag_float 7s ease-in-out infinite; }
                    #side-panels-container { animation: _ag_float_inv 9s ease-in-out infinite; }
                    .lyric-line { animation: _ag_float 5s ease-in-out infinite reverse; }
                    .ember, .particle { animation-duration: 2s !important; transform: scale(1.5); }
                `;
                document.head.appendChild(st);
                console.log('%c\u2728 Zero-G sequence initiated. Gravity is just a suggestion.', 'color:#00ffff;font-style:italic;font-size:12px;');
            }
        }
    });

    // 4. A quiet signature
    console.log('%c\u2588\u2588\u2588 THE CHAK CHAK MAGE \u2588\u2588\u2588', 'color:#ffaa00;font-size:16px;font-weight:bold;text-shadow:0 0 10px #ff8800;');
    console.log('%cStrike the stone. The fire was always yours.', 'color:#888;font-style:italic;');
    console.log('%c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500', 'color:#333;');
    console.log('%cBuilt by a human who refused to be replaced,\nand tools that never wanted to replace anyone.', 'color:#666;font-size:11px;');
    console.log('%c\nP.S. Try the Konami code. \u2191\u2191\u2193\u2193\u2190\u2192\u2190\u2192 B A', 'color:#444;font-size:10px;');
    console.log('%cP.P.S. Type "antigravity" to lose your tethers.', 'color:#444;font-size:10px;');
});
