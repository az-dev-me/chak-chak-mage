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

// Per-track emotion color themes
const TRACK_THEMES = {
    track_01: { accent: '#ffaa00', glow: 'rgba(255,170,0,0.6)' },     // gold — power/origin
    track_02: { accent: '#ff8800', glow: 'rgba(255,136,0,0.6)' },     // amber — worship/cult
    track_03: { accent: '#ff4444', glow: 'rgba(255,68,68,0.6)' },     // red — urgency/burnout
    track_04: { accent: '#cc66ff', glow: 'rgba(204,102,255,0.6)' },   // purple — dogma/division
    track_05: { accent: '#44dd88', glow: 'rgba(68,221,136,0.6)' },    // green — hope/discovery
    track_06: { accent: '#ff2244', glow: 'rgba(255,34,68,0.6)' },     // crimson — conflict
    track_07: { accent: '#4488ff', glow: 'rgba(68,136,255,0.6)' },    // blue — melancholy/escape
    track_08: { accent: '#44ccaa', glow: 'rgba(68,204,170,0.6)' },    // teal — reflection/hope
    track_09: { accent: '#ffffff', glow: 'rgba(255,255,255,0.5)' },   // white — clarity/truth
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
let meaningWordSpans = [];    // word spans for modern parallel text
let lastMeaningSetAt = 0;     // performance.now() when meaning last changed
let lastEnergyTick = 0;
let lineEnteredAt = 0;        // performance.now() when line changed
const LINE_GRACE_MS = 200;    // ms before word highlighting kicks in
const MEANING_HOLD_MS = 2500; // ms to keep meaning fully visible after line ends

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

    // Reset meaning panel for new variant
    meaningWordSpans = [];
    if (meaningText) meaningText.innerHTML = '';
    if (meaningPanel) {
        meaningPanel.classList.remove('meaning-visible');
        meaningPanel.classList.add('meaning-hidden');
    }

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
    'instead', 'actually', 'instead'
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

    // Core line: per-word spans with beat-snapped timing
    if (coreText && coreText.trim()) {
        const coreWords = coreText.trim().split(/\s+/);

        // Collect beats within this line for snap targets
        const allBeats = (loadedTrackData && loadedTrackData.beat_times) || [];
        const lineBeats = [];
        for (let b = 0; b < allBeats.length; b++) {
            if (allBeats[b] >= lineStart - 0.05 && allBeats[b] <= lineEnd + 0.05) {
                lineBeats.push(allBeats[b]);
            }
        }

        // Spread words evenly, snap to nearest beat
        const lineDur = lineEnd - lineStart;
        const wordTimings = [];
        for (let i = 0; i < coreWords.length; i++) {
            const ideal = lineStart + (i / coreWords.length) * lineDur;
            let snapped = ideal;
            if (lineBeats.length > 0) {
                let bestDist = Infinity;
                for (let b = 0; b < lineBeats.length; b++) {
                    const dist = Math.abs(lineBeats[b] - ideal);
                    if (dist < bestDist) { bestDist = dist; snapped = lineBeats[b]; }
                }
                if (bestDist > 0.4) snapped = ideal;
            }
            wordTimings.push(snapped);
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
                    const lineStart = activeLine.start;
                    const lineEnd = activeLine.end;
                    for (let w = 0; w < words.length; w++) {
                        // Clamp: only consider words whose start is within/after line start
                        const ws = Math.max(words[w].start, lineStart);
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
                                const wStart = Math.max(w.start, lineStart);
                                const wEnd = Math.max(w.end, wStart + 0.05);
                                const isWithin = ct >= wStart && ct < wEnd;
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

    // ── 4b. Meaning panel karaoke + beat sync ──
    // Core words: future → active → sung with beat-driven glow
    // Full text: breathe opacity with beat
    if (meaningWordSpans.length > 0) {
        const bp = (audioState ? audioState.beatPulse : timing.beatPulse) || 0;
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
                    if (span.className !== 'meaning-core-active') {
                        if (typeof Zone2Outer !== 'undefined') Zone2Outer.flashPanels();
                    }
                    span.className = 'meaning-core-active';
                    const scale = 1.0 + bp * 0.12;
                    span.style.transform = `scale(${scale.toFixed(3)})`;
                } else {
                    span.className = 'meaning-core-sung';
                    const glow = bp * 0.5;
                    span.style.textShadow = glow > 0.02
                        ? `0 0 ${(5 + glow * 10).toFixed(0)}px var(--accent-glow)`
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

        // Energy-reactive crossfade: fast transitions at high energy, slow at low
        const crossfadeMs = 1800 - energyVal * 1200; // 1.8s at calm → 0.6s at peak
        root.setProperty('--crossfade-speed', crossfadeMs.toFixed(0) + 'ms');
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

// Click anywhere on the phone frame to pause/play (reuses phoneFrame from line ~851)
if (phoneFrame) {
    phoneFrame.addEventListener('click', (e) => {
        // Don't toggle if clicking on controls, buttons, links, or variant picker
        if (e.target.closest('#player-controls, button, a, select, .variant-picker, #track-list')) return;
        togglePlay();
    });
}

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
                    loadTrack(currentTrackIndex + 1).then(() => { audio.play(); startSyncLoop(); });
                }
            } else {
                // Swipe right = prev track (or restart)
                if (audio.currentTime > 3) { audio.currentTime = 0; }
                else if (currentTrackIndex > 0) {
                    loadTrack(currentTrackIndex - 1).then(() => { audio.play(); startSyncLoop(); });
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
            startSyncLoop();
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
});
