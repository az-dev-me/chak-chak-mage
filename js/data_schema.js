// data_schema.js
// Handles the loading and structuring of Album Data
//
// Core data contracts (stable shapes):
// - AlbumConfig: albums/<ALBUM_ID>/album_config.json
// - TrackData: albums/<ALBUM_ID>/data/track_0X.js
// - MediaManifest: albums/<ALBUM_ID>/media_manifest.json
//
// See DATA_CONTRACTS.md for full field-level documentation.

let currentAlbumConfig = null;
let currentAlbumId = null;

// Cache-buster: appended to all image URLs to defeat browser caching of old pipeline images
// Change this value (or set to Date.now()) after each pipeline regeneration
const IMAGE_CACHE_BUSTER = `?v=${Date.now()}`;

// Minimal fallback used only when no albums_index is available at all.
const fallbackAlbumConfig = {
    album_id: "UNKNOWN",
    title: "The Chak Chak Mage",
    description: "Loading album data...",
    tracks: []
};

// Track titles come from album_config.json. This is just a generic fallback.

// Normalize pipeline config (slot, track_id, audio_path) into player shape (id, title, audioFile, defaultMedia).
function normalizeAlbumConfig(config) {
    if (!config || !config.tracks || !config.tracks.length) return config;
    const tracks = config.tracks.map((t) => {
        const trackId = t.track_id || t.id;
        if (!trackId) return t;
        const slot = t.slot != null ? t.slot : parseInt(trackId.replace("track_", ""), 10);
        const audioFile = t.audio_path || t.audio_file || t.audioFile || `${String(slot).padStart(2, "0")} - ${trackId}.mp3`;
        const num = trackId.replace("track_", "");
        return {
            id: trackId,
            title: t.title || `Track ${num}`,
            audioFile,
            defaultMedia: t.defaultMedia || `bg_t${num}.png`,
            dataVar: `${trackId}_data`,
            variant_id: t.variant_id || null,
            variants: t.variants || [],
            theme: t.theme || null
        };
    });
    return { ...config, tracks };
}

// Registry: use generated window.albumRegistry (from js/albums_index.js) when present; else fallback.
let albumRegistry = [];

if (typeof window !== "undefined" && window.albumRegistry && window.albumRegistry.length > 0) {
    albumRegistry = window.albumRegistry.map((entry) => ({
        ...entry,
        config: normalizeAlbumConfig(entry.config || entry)
    }));
} else {
    albumRegistry = [
        { album_id: fallbackAlbumConfig.album_id, title: fallbackAlbumConfig.title, description: fallbackAlbumConfig.description, config: fallbackAlbumConfig }
    ];
}

currentAlbumId = albumRegistry[0].album_id;
currentAlbumConfig = albumRegistry[0].config;

function getAlbumEntryById(albumId) {
    if (!albumId || !Array.isArray(albumRegistry)) return null;
    return albumRegistry.find(a => a.album_id === albumId) || null;
}

// Global Store for currently loaded track data (lyrics & media events)
let loadedTrackData = null;

const trackLoadPromises = {};

function loadAlbumTrackScript(albumId, trackId, variantId) {
    const dataKey = variantId ? `${trackId}_${variantId}` : trackId;
    const key = `${albumId}:${dataKey}`;
    if (trackLoadPromises[key]) {
        return trackLoadPromises[key];
    }

    trackLoadPromises[key] = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = `albums/${albumId}/data/${dataKey}.js?v=${Date.now()}`;
        script.onload = () => resolve();
        script.onerror = (e) => reject(e);
        document.head.appendChild(script);
    });

    return trackLoadPromises[key];
}

async function fetchTrackData(trackId, variantId) {
    const activeAlbumId = currentAlbumId || fallbackAlbumConfig.album_id;
    const albumEntry = getAlbumEntryById(activeAlbumId) || { config: fallbackAlbumConfig };
    const config = albumEntry.config;
    if (!config || !config.tracks) {
        loadedTrackData = { id: trackId, timeline: [] };
        return;
    }
    const item = config.tracks.find(t => t.id === trackId);
    const dataKey = variantId ? `${trackId}_${variantId}` : trackId;

    // Prefer albumData[albumId][dataKey] if available; otherwise dynamically load the script.
    if (!window.albumData || !window.albumData[activeAlbumId] || !window.albumData[activeAlbumId][dataKey]) {
        try {
            await loadAlbumTrackScript(activeAlbumId, trackId, variantId);
        } catch (_e) {
            // Script load failed — will try fallbacks below
        }
    }

    if (window.albumData && window.albumData[activeAlbumId] && window.albumData[activeAlbumId][dataKey]) {
        loadedTrackData = window.albumData[activeAlbumId][dataKey];
        return;
    }

    // Fallback: try base track data if variant data not found
    if (variantId) {
        // Ensure base track script is loaded
        if (!window.albumData || !window.albumData[activeAlbumId] || !window.albumData[activeAlbumId][trackId]) {
            try {
                await loadAlbumTrackScript(activeAlbumId, trackId);
            } catch (_e2) { /* base script also missing */ }
        }
        if (window.albumData && window.albumData[activeAlbumId] && window.albumData[activeAlbumId][trackId]) {
            loadedTrackData = window.albumData[activeAlbumId][trackId];
            return;
        }
    }

    // Fallback to legacy globals if they still exist.
    if (item && item.dataVar && window[item.dataVar]) {
        loadedTrackData = window[item.dataVar];
    } else {
        loadedTrackData = {
            id: trackId,
            timeline: []
        };
    }
}

// ── Album Duration Tracking (for dual timeline) ──
let trackDurations = [];
let albumTotalDuration = 0;
let trackCumulativeStarts = [];

async function loadAlbumDurations(albumId, trackCount) {
    trackDurations = [];
    trackCumulativeStarts = [0];
    albumTotalDuration = 0;

    const promises = [];
    for (let i = 1; i <= trackCount; i++) {
        const trackId = `track_${String(i).padStart(2, '0')}`;
        promises.push(
            fetch(`albums/${albumId}/data/${trackId}.structure.json`)
                .then(r => r.ok ? r.json() : null)
                .then(d => ({ index: i - 1, duration: d ? d.duration : 180 }))
                .catch(() => ({ index: i - 1, duration: 180 }))
        );
    }

    const results = await Promise.all(promises);
    results.sort((a, b) => a.index - b.index);
    results.forEach(r => {
        trackDurations.push(r.duration);
        albumTotalDuration += r.duration;
    });

    trackCumulativeStarts = [0];
    for (let i = 0; i < trackDurations.length - 1; i++) {
        trackCumulativeStarts.push(trackCumulativeStarts[i] + trackDurations[i]);
    }
}

// Load durations for a custom queue of {trackIndex, variantId} entries
// Used when "ALL VERSIONS" is active to show the full extended timeline
async function loadQueueDurations(albumId, queue, albumConfig) {
    trackDurations = [];
    trackCumulativeStarts = [0];
    albumTotalDuration = 0;

    const promises = queue.map((entry, i) => {
        const trackMeta = albumConfig.tracks[entry.trackIndex];
        const trackId = trackMeta.track_id || trackMeta.id;
        // Try variant-specific structure file first, fallback to base track
        const variantFile = entry.variantId
            ? `albums/${albumId}/data/${trackId}_${entry.variantId}.structure.json`
            : `albums/${albumId}/data/${trackId}.structure.json`;
        const baseFile = `albums/${albumId}/data/${trackId}.structure.json`;

        return fetch(variantFile)
            .then(r => r.ok ? r.json() : fetch(baseFile).then(r2 => r2.ok ? r2.json() : null))
            .then(d => ({ index: i, duration: d ? d.duration : 180 }))
            .catch(() => ({ index: i, duration: 180 }));
    });

    const results = await Promise.all(promises);
    results.sort((a, b) => a.index - b.index);
    results.forEach(r => {
        trackDurations.push(r.duration);
        albumTotalDuration += r.duration;
    });

    trackCumulativeStarts = [0];
    for (let i = 0; i < trackDurations.length - 1; i++) {
        trackCumulativeStarts.push(trackCumulativeStarts[i] + trackDurations[i]);
    }
}

// Load structure data (sections, transition_points) from .structure.json
// Called after fetchTrackData — supplements track data if not already present.
async function loadStructureData(albumId, trackId) {
    if (!loadedTrackData) return;
    // Skip if structure data already exists in track data
    if (loadedTrackData.sections && loadedTrackData.sections.length > 0) return;

    try {
        const resp = await fetch(`albums/${albumId}/data/${trackId}.structure.json`);
        if (resp.ok) {
            const data = await resp.json();
            loadedTrackData.sections = data.sections || [];
            loadedTrackData.transition_points = data.transition_points || [];
            // Re-load timing engine with updated data
            if (typeof TimingEngine !== 'undefined') {
                TimingEngine.load(loadedTrackData);
            }
        }
    } catch (_e) {
        // Structure data not available — non-critical
    }
}
