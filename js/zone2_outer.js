// zone2_outer.js
// Zone 2: Hidden narrative layer — outside the phone frame
// Bars (4 edges with gradient masks), side panels (left/right of phone),
// meaning overlay, beat-synced brightness, energy-reactive

const Zone2Outer = (() => {
    const bars = {};
    let meaningOverlay, meaningText;
    let lastBarUrls = {};
    let burstContainer, burstPanels;
    let burstActive = false;
    let lastBurstImageIdx = 0;
    let lastSectionIdx = -1;

    // Side panels: fixed left/right panels showing hidden narrative
    let sidePanels = {};
    let lastSidePanelUrls = {};

    function init() {
        ['top', 'right', 'bottom', 'left'].forEach(dir => {
            const el = document.querySelector(`.bar-${dir}`);
            if (el) {
                bars[dir] = {
                    layerA: el.querySelector('.bar-layer-a'),
                    layerB: el.querySelector('.bar-layer-b'),
                    activeLayer: 'A'
                };
            }
        });
        meaningOverlay = document.getElementById('hidden-meaning-overlay');
        meaningText = document.getElementById('hidden-meaning-text');
        burstContainer = document.getElementById('burst-container');
        burstPanels = burstContainer ? burstContainer.querySelectorAll('.burst-panel') : [];

        // Side panels: repurposed orbit modals as fixed panels
        ['left', 'right'].forEach(side => {
            const el = document.getElementById(`side-panel-${side}`);
            if (el) {
                sidePanels[side] = {
                    layerA: el.querySelector('.side-img-a'),
                    layerB: el.querySelector('.side-img-b'),
                    activeLayer: 'A'
                };
            }
        });
    }

    // A/B crossfade for a specific bar direction
    function setBarImage(dir, url) {
        const bar = bars[dir];
        if (!bar || !url || url === lastBarUrls[dir]) return;
        lastBarUrls[dir] = url;
        const bust = typeof IMAGE_CACHE_BUSTER !== 'undefined' ? IMAGE_CACHE_BUSTER : '';

        if (bar.activeLayer === 'A') {
            if (bar.layerB) bar.layerB.style.backgroundImage = `url('${url}${bust}')`;
            if (bar.layerB) bar.layerB.classList.add('active');
            if (bar.layerA) bar.layerA.classList.remove('active');
            bar.activeLayer = 'B';
        } else {
            if (bar.layerA) bar.layerA.style.backgroundImage = `url('${url}${bust}')`;
            if (bar.layerA) bar.layerA.classList.add('active');
            if (bar.layerB) bar.layerB.classList.remove('active');
            bar.activeLayer = 'A';
        }
    }

    // A/B crossfade for a side panel
    function setSidePanelImage(side, url) {
        const panel = sidePanels[side];
        if (!panel || !url || url === lastSidePanelUrls[side]) return;
        lastSidePanelUrls[side] = url;
        const bust = typeof IMAGE_CACHE_BUSTER !== 'undefined' ? IMAGE_CACHE_BUSTER : '';

        if (panel.activeLayer === 'A') {
            if (panel.layerB) panel.layerB.style.backgroundImage = `url('${url}${bust}')`;
            if (panel.layerB) panel.layerB.classList.add('active');
            if (panel.layerA) panel.layerA.classList.remove('active');
            panel.activeLayer = 'B';
        } else {
            if (panel.layerA) panel.layerA.style.backgroundImage = `url('${url}${bust}')`;
            if (panel.layerA) panel.layerA.classList.add('active');
            if (panel.layerB) panel.layerB.classList.remove('active');
            panel.activeLayer = 'A';
        }
    }

    // Distribute hidden_media across bars AND side panels
    // Bars: top/bottom = WIDE establishing, left/right = SCENE/MOMENT
    // Side panels: left = WIDE establishing, right = MOMENT close-up
    function updateBars(activeLine, currentTime, albumPath) {
        const hiddenArr = activeLine && activeLine.hidden_media;
        if (!hiddenArr || hiddenArr.length === 0) return;

        // Collect all triggered hidden images by offset
        const triggered = [];
        for (let h = 0; h < hiddenArr.length; h++) {
            const hm = hiddenArr[h];
            if (!hm || !hm.url) continue;
            const trigTime = activeLine.start + parseFloat(hm.offset || 0);
            if (currentTime >= trigTime) {
                triggered.push(`${albumPath}/${hm.url}`);
            }
        }
        // Fallback: use first available
        if (triggered.length === 0 && hiddenArr[0] && hiddenArr[0].url) {
            triggered.push(`${albumPath}/${hiddenArr[0].url}`);
        }
        if (triggered.length === 0) return;

        // Distribute across bars — different images per direction
        // Top/bottom = first triggered (WIDE establishing shot)
        // Left/right = last triggered (latest offset = SCENE or MOMENT)
        const wideUrl = triggered[0];
        const sceneUrl = triggered.length > 1 ? triggered[triggered.length - 1] : triggered[0];

        setBarImage('top', wideUrl);
        setBarImage('bottom', wideUrl);
        setBarImage('left', sceneUrl);
        setBarImage('right', sceneUrl);

        // Side panels: left = WIDE establishing, right = latest (SCENE/MOMENT)
        setSidePanelImage('left', wideUrl);
        setSidePanelImage('right', sceneUrl);
    }

    // Meaning overlay — now handled inside phone frame by player.js
    function updateMeaning(activeLine) {
        // External overlay permanently hidden; meaning panel is inside #phone-frame
        return;
    }

    // Beat pulse: CSS custom properties for text glow, strip border, bar brightness, downbeat flash
    function applyBeatPulse(beatPulse, isDownbeat) {
        // Text glow: every beat
        document.documentElement.style.setProperty('--beat-text-glow', beatPulse.toFixed(3));

        // Meaning strip border: every beat (gold shimmer)
        const borderAlpha = 0.12 + beatPulse * 0.35;
        document.documentElement.style.setProperty('--beat-strip-border', borderAlpha.toFixed(3));

        // Bar brightness: every beat
        const brightness = beatPulse * 0.03;
        document.documentElement.style.setProperty('--beat-brightness', brightness.toFixed(4));

        // Downbeat flash: stronger brightness on measure start (every 4th beat)
        if (isDownbeat && beatPulse > 0.5) {
            document.documentElement.style.setProperty('--beat-bg-flash', (beatPulse * 0.8).toFixed(3));
        } else {
            // Fast decay
            const current = parseFloat(
                document.documentElement.style.getPropertyValue('--beat-bg-flash') || '0'
            );
            document.documentElement.style.setProperty('--beat-bg-flash', (current * 0.85).toFixed(3));
        }
    }

    // Energy-reactive bar brightness + narrative frame opacity
    function applyEnergy(energy) {
        const barBrightness = 0.25 + energy * 0.40;
        document.documentElement.style.setProperty('--bar-brightness', barBrightness.toFixed(3));

        // Narrative frame opacity
        const frame = document.getElementById('narrative-frame');
        if (frame) {
            frame.style.opacity = energy < 0.2
                ? (0.4 + energy * 2).toFixed(2)
                : (0.6 + energy * 0.4).toFixed(2);
        }

        // Side panels: more visible at higher energy
        const sideContainer = document.getElementById('side-panels-container');
        if (sideContainer) {
            const sideOpacity = 0.4 + energy * 0.5;
            sideContainer.style.opacity = sideOpacity.toFixed(2);
        }
    }

    // Burst: rapid image flash on high-energy + beat moments
    function updateBurst(energy, beatPulse, albumPath, timeline, lineIdx) {
        if (!burstContainer || !timeline) return;

        if (energy > 0.85 && !burstActive) {
            burstContainer.classList.add('burst-on');
            burstContainer.classList.remove('burst-off');
            burstActive = true;
        } else if (energy <= 0.75 && burstActive) {
            burstContainer.classList.remove('burst-on');
            burstContainer.classList.add('burst-off');
            burstActive = false;
            burstPanels.forEach(p => p.classList.remove('flash'));
        }

        if (burstActive && beatPulse > 0.7 && burstPanels.length > 0) {
            const pool = [];
            for (let d = -2; d <= 2; d++) {
                const idx = lineIdx + d;
                if (idx >= 0 && idx < timeline.length) {
                    const hm = timeline[idx].hidden_media;
                    if (hm) hm.forEach(m => { if (m && m.url) pool.push(m.url); });
                }
            }
            if (pool.length === 0) return;

            const bust = typeof IMAGE_CACHE_BUSTER !== 'undefined' ? IMAGE_CACHE_BUSTER : '';
            burstPanels.forEach((panel, i) => {
                const imgIdx = (lastBurstImageIdx + i) % pool.length;
                panel.style.backgroundImage = `url('${albumPath}/${pool[imgIdx]}${bust}')`;
                panel.classList.add('flash');
                setTimeout(() => panel.classList.remove('flash'), 120);
            });
            lastBurstImageIdx = (lastBurstImageIdx + burstPanels.length) % Math.max(pool.length, 1);
        }
    }

    // Section change
    function onSectionChange(sectionIdx, timeline, currentTime, albumPath) {
        if (sectionIdx === lastSectionIdx) return;
        lastSectionIdx = sectionIdx;

        let nearestLine = null;
        for (let i = 0; i < timeline.length; i++) {
            if (timeline[i].start <= currentTime && timeline[i].hidden_media && timeline[i].hidden_media.length > 0) {
                nearestLine = timeline[i];
            }
        }
        if (nearestLine) {
            updateBars(nearestLine, currentTime, albumPath);
        }
    }

    // Chorus pulse
    function chorusPulse() {
        document.documentElement.style.setProperty('--beat-brightness', '0.15');
        document.documentElement.style.setProperty('--ambient-brightness', '0.35');
        setTimeout(() => {
            document.documentElement.style.setProperty('--beat-brightness', '0');
        }, 300);
    }

    function reset() {
        lastBarUrls = {};
        lastSidePanelUrls = {};
        burstActive = false;
        lastBurstImageIdx = 0;
        lastSectionIdx = -1;
        if (burstContainer) {
            burstContainer.classList.remove('burst-on');
            burstContainer.classList.add('burst-off');
            burstPanels.forEach(p => { p.classList.remove('flash'); p.style.backgroundImage = ''; });
        }
        ['top', 'right', 'bottom', 'left'].forEach(dir => {
            const bar = bars[dir];
            if (!bar) return;
            bar.activeLayer = 'A';
            if (bar.layerA) { bar.layerA.classList.add('active'); bar.layerA.style.backgroundImage = ''; }
            if (bar.layerB) { bar.layerB.classList.remove('active'); bar.layerB.style.backgroundImage = ''; }
        });
        ['left', 'right'].forEach(side => {
            const panel = sidePanels[side];
            if (!panel) return;
            panel.activeLayer = 'A';
            if (panel.layerA) { panel.layerA.classList.add('active'); panel.layerA.style.backgroundImage = ''; }
            if (panel.layerB) { panel.layerB.classList.remove('active'); panel.layerB.style.backgroundImage = ''; }
        });
        if (meaningOverlay) {
            meaningOverlay.classList.remove('hidden-meaning-on');
            meaningOverlay.classList.add('hidden-meaning-off');
        }
    }

    return { init, updateBars, updateMeaning, applyBeatPulse, applyEnergy,
             updateBurst, onSectionChange, chorusPulse, reset };
})();
