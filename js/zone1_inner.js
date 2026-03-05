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
    // Beat-aligned cutting: snap image changes to nearest beat (±100ms, Vatakis & Spence 2006)
    function updateMedia(activeLine, currentTime, albumPath, beatTimes) {
        const mediaArr = activeLine && activeLine.media;
        if (!mediaArr || mediaArr.length === 0) return;

        let chosenMedia = mediaArr[0].url;
        for (let m = 0; m < mediaArr.length; m++) {
            if (!mediaArr[m]) continue;
            let triggerTime = activeLine.start + parseFloat(mediaArr[m].offset || 0);
            // Snap to nearest beat within ±100ms tolerance
            if (beatTimes && beatTimes.length > 0) {
                let nearestBeat = triggerTime;
                let minDist = Infinity;
                for (let b = 0; b < beatTimes.length; b++) {
                    const dist = Math.abs(beatTimes[b] - triggerTime);
                    if (dist < minDist) { minDist = dist; nearestBeat = beatTimes[b]; }
                    if (beatTimes[b] > triggerTime + 0.5) break;
                }
                if (minDist < 0.1) triggerTime = nearestBeat;
            }
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
