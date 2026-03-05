// zone1_inner.js
// Zone 1: Inner story renderer — phone frame
// Manages A/B crossfade of literal images INSIDE #phone-frame

const Zone1Inner = (() => {
    let imgLayerA, imgLayerB;
    let activeLayer = 'A';
    let lastTriggeredMedia = null;

    function init() {
        imgLayerA = document.getElementById('inner-img-a');
        imgLayerB = document.getElementById('inner-img-b');
    }

    // A/B crossfade INSIDE the phone frame
    function setImage(mediaUrl) {
        if (!mediaUrl || mediaUrl === lastTriggeredMedia) return;
        lastTriggeredMedia = mediaUrl;
        const bust = typeof IMAGE_CACHE_BUSTER !== 'undefined' ? IMAGE_CACHE_BUSTER : '';

        if (activeLayer === 'A') {
            if (imgLayerB) imgLayerB.style.backgroundImage = `url('${mediaUrl}${bust}')`;
            if (imgLayerB) imgLayerB.classList.add('active');
            if (imgLayerA) imgLayerA.classList.remove('active');
            activeLayer = 'B';
        } else {
            if (imgLayerA) imgLayerA.style.backgroundImage = `url('${mediaUrl}${bust}')`;
            if (imgLayerA) imgLayerA.classList.add('active');
            if (imgLayerB) imgLayerB.classList.remove('active');
            activeLayer = 'A';
        }
    }

    // Process media[] sub-timeline for current line
    // Uses pipeline-calculated offsets directly — no beat snapping.
    // The pipeline (fuse.py build_media_array) already computes offsets
    // using structure analysis, intensity, and beat alignment.
    function updateMedia(activeLine, currentTime, albumPath) {
        const mediaArr = activeLine && activeLine.media;
        if (!mediaArr || mediaArr.length === 0) return;

        let chosenMedia = mediaArr[0].url;
        for (let m = 0; m < mediaArr.length; m++) {
            if (!mediaArr[m]) continue;
            const triggerTime = activeLine.start + parseFloat(mediaArr[m].offset || 0);
            if (currentTime >= triggerTime) chosenMedia = mediaArr[m].url;
        }
        if (chosenMedia) {
            setImage(`${albumPath}/${chosenMedia}`);
        }
    }

    function reset() {
        lastTriggeredMedia = null;
        activeLayer = 'A';
        if (imgLayerA) { imgLayerA.classList.add('active'); imgLayerA.style.backgroundImage = ''; }
        if (imgLayerB) { imgLayerB.classList.remove('active'); imgLayerB.style.backgroundImage = ''; }
    }

    return { init, setImage, updateMedia, reset };
})();
