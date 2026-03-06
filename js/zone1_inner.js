// zone1_inner.js
// Zone 1: Inner story renderer — phone frame
// Manages A/B crossfade of literal images INSIDE #phone-frame

const Zone1Inner = (() => {
    let imgLayerA, imgLayerB;
    let activeLayer = 'A';
    let lastTriggeredMedia = null;
    let captionEl = null;
    let captionTimer = null;
    const CAPTION_SHOW_MS = 3000;

    function init() {
        imgLayerA = document.getElementById('inner-img-a');
        imgLayerB = document.getElementById('inner-img-b');
        captionEl = document.getElementById('scene-caption');
    }

    // Extract short scene description from full query (remove "Wide shot:", etc.)
    function extractCaption(query) {
        if (!query) return '';
        let text = query
            .replace(/^(Wide|Close|Medium|Extreme|Aerial|Low[- ]angle|High[- ]angle)\s*(shot|view|establishing)?:?\s*/i, '')
            .trim();
        // Truncate to first sentence or 80 chars
        const dotIdx = text.indexOf('. ');
        if (dotIdx > 10 && dotIdx < 80) text = text.substring(0, dotIdx + 1);
        if (text.length > 80) text = text.substring(0, 77) + '...';
        return text;
    }

    function showCaption(query) {
        if (!captionEl || !query) return;
        const text = extractCaption(query);
        if (!text) return;
        captionEl.textContent = text;
        captionEl.classList.add('caption-visible');
        clearTimeout(captionTimer);
        captionTimer = setTimeout(() => {
            captionEl.classList.remove('caption-visible');
        }, CAPTION_SHOW_MS);
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

        let chosenMedia = mediaArr[0];
        for (let m = 0; m < mediaArr.length; m++) {
            if (!mediaArr[m]) continue;
            const triggerTime = activeLine.start + parseFloat(mediaArr[m].offset || 0);
            if (currentTime >= triggerTime) chosenMedia = mediaArr[m];
        }
        if (chosenMedia && chosenMedia.url) {
            const fullUrl = `${albumPath}/${chosenMedia.url}`;
            if (fullUrl !== lastTriggeredMedia) {
                showCaption(chosenMedia.query);
            }
            setImage(fullUrl);
        }
    }

    function reset() {
        lastTriggeredMedia = null;
        activeLayer = 'A';
        clearTimeout(captionTimer);
        if (captionEl) captionEl.classList.remove('caption-visible');
        if (imgLayerA) { imgLayerA.classList.add('active'); imgLayerA.style.backgroundImage = ''; }
        if (imgLayerB) { imgLayerB.classList.remove('active'); imgLayerB.style.backgroundImage = ''; }
    }

    return { init, setImage, updateMedia, reset };
})();
