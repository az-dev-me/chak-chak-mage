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

// Minimal fallback used only when no albums_index is available at all.
const fallbackAlbumConfig = {
    album_id: "UNKNOWN",
    title: "The Chak Chak Mage",
    description: "Loading album data...",
    tracks: []
};

// Canonical track titles — used by normalizeAlbumConfig when pipeline config
// only has track_id/slot (no display title).
const TRACK_TITLES = {
    track_01: "Prologue - The Green Booth",
    track_02: "The Orange Box",
    track_03: "The Fire Run",
    track_04: "The Rules",
    track_05: "Muda's Spark",
    track_06: "Two Fires",
    track_07: "The Empty Lighter",
    track_08: "The Fire Was Always There",
    track_09: "Epilogue - The Lesson"
};

// Normalize pipeline config (slot, track_id, audio_path) into player shape (id, title, audioFile, defaultMedia).
function normalizeAlbumConfig(config) {
    if (!config || !config.tracks || !config.tracks.length) return config;
    const tracks = config.tracks.map((t) => {
        const trackId = t.track_id || t.id;
        if (!trackId) return t;
        const slot = t.slot != null ? t.slot : parseInt(trackId.replace("track_", ""), 10);
        const audioFile = t.audio_file || t.audioFile || `${String(slot).padStart(2, "0")} - ${trackId}.mp3`;
        const num = trackId.replace("track_", "");
        return {
            id: trackId,
            title: t.title || TRACK_TITLES[trackId] || trackId,
            audioFile,
            defaultMedia: t.defaultMedia || `bg_t${num}.png`,
            dataVar: `${trackId}_data`
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

function loadAlbumTrackScript(albumId, trackId) {
    const key = `${albumId}:${trackId}`;
    if (trackLoadPromises[key]) {
        return trackLoadPromises[key];
    }

    trackLoadPromises[key] = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = `albums/${albumId}/data/${trackId}.js`;
        script.onload = () => resolve();
        script.onerror = (e) => reject(e);
        document.head.appendChild(script);
    });

    return trackLoadPromises[key];
}

async function fetchTrackData(trackId) {
    const activeAlbumId = currentAlbumId || fallbackAlbumConfig.album_id;
    const albumEntry = getAlbumEntryById(activeAlbumId) || { config: fallbackAlbumConfig };
    const config = albumEntry.config;
    if (!config || !config.tracks) {
        loadedTrackData = { id: trackId, timeline: [] };
        return;
    }
    const item = config.tracks.find(t => t.id === trackId);

    // Prefer albumData[albumId][trackId] if available; otherwise dynamically load the script.
    if (!window.albumData || !window.albumData[activeAlbumId] || !window.albumData[activeAlbumId][trackId]) {
        try {
            await loadAlbumTrackScript(activeAlbumId, trackId);
        } catch (_e) {
            // Script load failed — will try fallbacks below
        }
    }

    if (window.albumData && window.albumData[activeAlbumId] && window.albumData[activeAlbumId][trackId]) {
        loadedTrackData = window.albumData[activeAlbumId][trackId];
        return;
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
