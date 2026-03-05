// zone3_ambient.js
// Zone 3: Ambient emotional field
// Fullscreen blurred/dimmed background — shows HIDDEN narrative images (modern parallel)
// Creates dual-narrative effect: literal story inside phone, modern parallel in background

const Zone3Ambient = (() => {
    let layerA, layerB, vignette;
    let activeLayer = 'A';
    let lastAmbientImage = null;

    function init() {
        layerA = document.getElementById('ambient-layer-a');
        layerB = document.getElementById('ambient-layer-b');
        vignette = document.getElementById('vignette-overlay');
    }

    function setImage(mediaUrl) {
        if (!mediaUrl || mediaUrl === lastAmbientImage) return;
        lastAmbientImage = mediaUrl;
        const bust = typeof IMAGE_CACHE_BUSTER !== 'undefined' ? IMAGE_CACHE_BUSTER : '';

        if (activeLayer === 'A') {
            if (layerB) layerB.style.backgroundImage = `url('${mediaUrl}${bust}')`;
            if (layerB) layerB.classList.add('active');
            if (layerA) layerA.classList.remove('active');
            activeLayer = 'B';
        } else {
            if (layerA) layerA.style.backgroundImage = `url('${mediaUrl}${bust}')`;
            if (layerA) layerA.classList.add('active');
            if (layerB) layerB.classList.remove('active');
            activeLayer = 'A';
        }
    }

    function applyEnergy(energy) {
        // Ambient brightness: visible at low energy, quite bright at high
        const brightness = 0.18 + energy * 0.30;
        document.documentElement.style.setProperty('--ambient-brightness', brightness.toFixed(3));

        // Vignette: deeper at quiet sections
        if (vignette) {
            vignette.style.opacity = (1.0 - energy * 0.4).toFixed(2);
        }
    }

    function reset() {
        lastAmbientImage = null;
        activeLayer = 'A';
        if (layerA) { layerA.classList.add('active'); layerA.style.backgroundImage = ''; }
        if (layerB) { layerB.classList.remove('active'); layerB.style.backgroundImage = ''; }
    }

    return { init, setImage, applyEnergy, reset };
})();
