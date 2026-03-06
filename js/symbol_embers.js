// ═══════════════════════════════════════════════════════════════
// Symbol Embers — Grayscale emoji particles rising through phone frame
// Spawned on each meaning line change, tailored to hidden narrative
// ═══════════════════════════════════════════════════════════════

const SymbolEmbers = (function () {
    'use strict';

    // ── Symbol map: trackId → lineIndex → [emoji, emoji] ──
    const SYMBOLS = {
        track_01: {
            0: ['\u{1F4F1}','\u{1F3B0}'], 1: ['\u{1F451}','\u26A1'], 2: ['\u{1F994}','\u{1F50C}']
        },
        track_02: {
            0: ['\u{1F30D}','\u{1F441}\uFE0F'], 1: ['\u{1F4F1}','\u{1F6D0}'], 2: ['\u{1F4C8}','\u{1F4A5}'],
            3: ['\u{1F4F8}','\u2B50'], 4: ['\u{1F9CE}','\u2728'], 5: ['\u{1F451}','\u{1FA91}'],
            6: ['\u2122\uFE0F','\u26EA'], 7: ['\u{1F52E}','\u{1F937}'], 8: ['\u{1F501}','\u{1F9E0}'],
            9: ['\u{1F3C3}','\u{1F4BC}'], 10: ['\u23F0','\u{1F480}'], 11: ['\u{1F3F7}\uFE0F','\u{1F512}'],
            12: ['\u2705','\u{1F4A1}'], 13: ['\u{1F4E2}','\u{1F3A4}'], 14: ['\u{1F4CA}','\u{1F3AF}'],
            15: ['\u{1FA9E}','\u2753'], 16: ['\u{1F4D6}','\u{1F30A}'], 17: ['\u{1F3E6}','\u{1F507}'],
            18: ['\u{1F3C3}','\u{1F4B0}'], 19: ['\u{1F439}','\u{1F3A1}'], 20: ['\u{1F3A8}','\u{1FAD7}'],
            21: ['\u{1FAA4}','\u{1F504}'], 22: ['\u{1F910}','\u{1F4DD}'], 23: ['\u{1F994}','\u270A'],
            24: ['\u{1F3AD}','\u{1F517}']
        },
        track_03: {
            0: ['\u23F0','\u{1F514}'], 1: ['\u{1F4F2}','\u{1F3C1}'], 2: ['\u{1F4BC}','\u26D3\uFE0F'],
            3: ['\u{1F3C3}','\u{1FAE3}'], 4: ['\u{1F44F}','\u{1F624}'], 5: ['\u{1F4CA}','\u{1F4B9}'],
            6: ['\u{1F4C9}','\u{1F630}'], 7: ['\u{1F3D4}\uFE0F','\u{1FAD7}'], 8: ['\u{1F687}','\u{1F4A8}'],
            9: ['\u{1F465}','\u26FD'], 10: ['\u{1F525}','\u{1F480}'], 11: ['\u{1F4C9}','\u2753'],
            12: ['\u{1F4CB}','\u{1F926}'], 13: ['\u{1F9D8}','\u{1F19A}'], 14: ['\u2699\uFE0F','\u{1F9CE}'],
            15: ['\u{1F631}','\u{1F300}'], 16: ['\u{1F3ED}','\u{1F504}'], 17: ['\u{1F3AA}','\u{1F4FA}'],
            18: ['\u{1F400}','\u267E\uFE0F'], 19: ['\u{1F947}','\u{1F494}'], 20: ['\u{1F501}','\u267E\uFE0F']
        },
        track_04: {
            0: ['\u{1F4E1}','\u{1FAE7}'], 1: ['\u{1F4DC}','\u2694\uFE0F'], 2: ['\u{1F3DB}\uFE0F','\u{1F446}'],
            3: ['\u{1F3DB}\uFE0F','\u{1F447}'], 4: ['\u{1F4CB}','\u{1F916}'], 5: ['\u{1F4F0}','\u{1F5E3}\uFE0F'],
            6: ['\u{1F6AB}','\u{1F525}'], 7: ['\u{1F476}','\u{1F453}'], 8: ['\u2699\uFE0F','\u{1F6D0}'],
            9: ['\u{1F52E}','\u{1F9F2}'], 10: ['\u{1F3F0}','\u{1F377}'], 11: ['\u{1F464}','\u{1F3DD}\uFE0F'],
            12: ['\u{1F4F1}','\u26EA'], 13: ['\u{1F4E6}','\u{1F451}'], 14: ['\u{1F527}','\u{1F649}'],
            15: ['\u2728','\u{1F648}'], 16: ['\u2753','\u{1F504}'], 17: ['\u{1F4E2}','\u{1F6AB}'],
            18: ['\u270A','\u2122\uFE0F'], 19: ['\u{1F441}\uFE0F','\u23F3'], 20: ['\u{1F9DF}','\u{1F4AC}'],
            21: ['\u{1F9A0}','\u{1F50A}'], 22: ['\u2699\uFE0F','\u{1F504}']
        },
        track_05: {
            0: ['\u{1F441}\uFE0F','\u{1F92B}'], 1: ['\u{1F52C}','\u{1F33F}'], 2: ['\u{1F9D8}','\u{1F30A}'],
            3: ['\u{1F6B6}','\u{1F4A1}'], 4: ['\u{1FAA8}','\u{1F932}'], 5: ['\u{1F528}','\u{1F331}'],
            6: ['\u{1FAA8}','\u{1FAA8}'], 7: ['\u{1F52C}','\u26A1'], 8: ['\u{1F513}','\u{1F4AB}'],
            9: ['\u{1F6B6}','\u270B'], 10: ['\u{1F463}','\u{1FAA8}'], 11: ['\u{1F305}','\u{1F4AA}'],
            12: ['\u{1F4D6}','\u{1F54A}\uFE0F'], 13: ['\u{1F9F1}','\u{1F193}'], 14: ['\u262F\uFE0F','\u270C\uFE0F'],
            15: ['\u{1F3AD}','\u{1F494}'], 16: ['\u{1F4B2}','\u2753'], 17: ['\u{1F513}','\u{1F628}'],
            18: ['\u26A0\uFE0F','\u{1F4DC}'], 19: ['\u{1F4E1}','\u{1F310}'], 20: ['\u{1F5D1}\uFE0F','\u{1F4F1}'],
            21: ['\u{1F6B6}','\u{1F33F}'], 22: ['\u{1FAA8}','\u23F8\uFE0F'], 23: ['\u{1F525}','\u{1F464}'],
            24: ['\u270A','\u{1F525}']
        },
        track_06: {
            0: ['\u{1F3DB}\uFE0F','\u{1F4E2}'], 1: ['\u{1FAE3}','\u267E\uFE0F'], 2: ['\u274C','\u{1F507}'],
            3: ['\u{1F916}','\u{1F3F3}\uFE0F'], 4: ['\u{1F441}\uFE0F','\u270B'], 5: ['\u{1F9E0}','\u26A1'],
            6: ['\u{1F3A9}','\u{1F3AA}'], 7: ['\u{1F310}','\u{1F513}'], 8: ['\u{1F534}','\u{1F535}'],
            9: ['\u{1F525}','\u{1F630}'], 10: ['\u{1F4E2}','\u{1F573}\uFE0F'], 11: ['\u2753','\u2702\uFE0F'],
            12: ['\u{1F3F4}','\u2694\uFE0F'], 13: ['\u270A','\u{1F3F4}'], 14: ['\u{1F9CD}','\u2696\uFE0F'],
            15: ['\u{1F5E3}\uFE0F','\u{1F9CA}'], 16: ['\u{1F4E6}','\u26A1'], 17: ['\u{1F631}','\u{1F311}'],
            18: ['\u{1F3AD}','\u{1F3F7}\uFE0F'], 19: ['\u{1F91D}','\u{1F311}'], 20: ['\u26FD','\u{1F4A8}'],
            21: ['\u{1F937}','\u{1F5D1}\uFE0F'], 22: ['\u{1F4BC}','\u{1F6AA}']
        },
        track_07: {
            0: ['\u{1F3DA}\uFE0F','\u{1F6E9}\uFE0F'], 1: ['\u{1F994}','\u{1F33F}'], 2: ['\u{1F440}','\u{1F614}'],
            3: ['\u{1F4F1}','\u2694\uFE0F'], 4: ['\u{1F4E6}','\u{1F388}'], 5: ['\u{1F6D2}','\u{1F3C3}'],
            6: ['\u{1F411}','\u2728'], 7: ['\u{1F4F1}','\u{1F480}'], 8: ['\u{1FAE7}','\u{1F4C9}'],
            9: ['\u{1F4E6}','\u{1FAD7}'], 10: ['\u{1F5D1}\uFE0F','\u{1F3D4}\uFE0F'], 11: ['\u{1F6AA}','\u{1F333}'],
            12: ['\u{1F30D}','\u{1F932}'], 13: ['\u{1F636}','\u{1F494}'], 14: ['\u23EA','\u{1F527}'],
            15: ['\u{1F525}','\u{1F44B}'], 16: ['\u{1F4F1}','\u{1F5D1}\uFE0F'], 17: ['\u{1F938}','\u2728'],
            18: ['\u{1F504}','\u{1F411}'], 19: ['\u26FD','\u{1F6AB}'], 20: ['\u{1F994}','\u{1F331}']
        },
        track_08: {
            0: ['\u{1F4FA}','\u{1F311}'], 1: ['\u{1F994}','\u{1F45F}'], 2: ['\u{1F9EC}','\u{1F504}'],
            3: ['\u{1F4F1}','\u{1F527}'], 4: ['\u{1F527}','\u{1F6D0}'], 5: ['\u{1F446}','\u{1FA9E}'],
            6: ['\u{1F5A5}\uFE0F','\u{1F9E0}'], 7: ['\u{1F3C3}','\u{1F56F}\uFE0F'], 8: ['\u{1FAF3}','\u{1F525}'],
            9: ['\u{1FAA8}','\u{1F193}'], 10: ['\u{1F9CD}','\u270B'], 11: ['\u{1F4E2}','\u{1F3C3}'],
            12: ['\u{1F3A9}','\u{1F4E3}'], 13: ['\u{1F3A8}','\u{1F926}'], 14: ['\u{1F7E0}','\u{1F535}'],
            15: ['\u{1F4CA}','\u{1F54A}\uFE0F'], 16: ['\u{1FAA8}','\u23F3'], 17: ['\u{1F9D8}','\u23F3'],
            18: ['\u{1F4F1}','\u{1FAA8}']
        },
        track_09: {
            0: ['\u{1F504}','\u{1F4A1}'], 1: ['\u{1F9E0}','\u{1F501}'], 2: ['\u{1F527}','\u2694\uFE0F'],
            3: ['\u2753','\u{1F30D}'], 4: ['\u{1F4F1}','\u{1FAE3}'], 5: ['\u{1F916}','\u{1F512}'],
            6: ['\u{1F91D}','\u26D3\uFE0F'], 7: ['\u{1F525}','\u270A'], 8: ['\u{1FAA8}','\u2728']
        }
    };

    const MAX_PARTICLES = 50;
    let canvas = null;
    let ctx = null;
    let particles = [];
    let frame = 0;
    let phoneW = 0;
    let phoneH = 0;
    let dpr = 1;
    let pendingSpawns = []; // queue for staggered spawns
    let lastTrackId = '';
    let lastLineIndex = -1;

    function init(phoneFrame) {
        if (!phoneFrame) return;
        canvas = document.createElement('canvas');
        canvas.id = 'symbol-embers-canvas';
        canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;z-index:2;pointer-events:none;';
        phoneFrame.appendChild(canvas);
        ctx = canvas.getContext('2d');
        resize();
        window.addEventListener('resize', resize);
    }

    function resize() {
        if (!canvas || !canvas.parentElement) return;
        dpr = window.devicePixelRatio || 1;
        const rect = canvas.parentElement.getBoundingClientRect();
        phoneW = rect.width;
        phoneH = rect.height;
        canvas.width = phoneW * dpr;
        canvas.height = phoneH * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    // Build a flat pool of all emojis for a given track (or medley components)
    let cachedPool = [];
    let cachedPoolTrack = '';

    function getPool(trackId) {
        if (trackId === cachedPoolTrack && cachedPool.length > 0) return cachedPool;
        cachedPoolTrack = trackId;
        cachedPool = [];

        // For medleys (track_01 = tracks 1+2+3), merge all component pools
        const trackIds = trackId === 'track_01'
            ? ['track_01', 'track_02', 'track_03']
            : [trackId];

        for (const tid of trackIds) {
            const trackMap = SYMBOLS[tid];
            if (!trackMap) continue;
            for (const key in trackMap) {
                for (const emoji of trackMap[key]) {
                    if (cachedPool.indexOf(emoji) === -1) cachedPool.push(emoji);
                }
            }
        }
        return cachedPool;
    }

    function spawnSymbols(lineIndex, trackId) {
        // Try exact match first
        const trackMap = SYMBOLS[trackId];
        let emojis = trackMap && trackMap[lineIndex];

        // Fallback: pick from pool
        if (!emojis || emojis.length === 0) {
            const pool = getPool(trackId);
            if (pool.length === 0) return;
            emojis = [
                pool[Math.floor(Math.random() * pool.length)],
                pool[Math.floor(Math.random() * pool.length)]
            ];
        }

        lastTrackId = trackId;
        lastLineIndex = lineIndex;

        // Spawn 3-4 symbols per line for more visual presence
        const count = 3 + Math.floor(Math.random() * 2);
        for (let i = 0; i < count; i++) {
            const emoji = emojis[i % emojis.length] || emojis[0];
            if (i === 0) {
                addParticle(emoji);
            } else {
                pendingSpawns.push({ emoji, delay: 8 + i * 12 });
            }
        }
    }

    function addParticle(emoji) {
        // Curved path: each particle gets a unique horizontal sine wave
        const waveAmp = 0.6 + Math.random() * 1.2;   // amplitude of horizontal curve
        const waveFreq = 0.012 + Math.random() * 0.01; // frequency of curve
        const wavePhase = Math.random() * Math.PI * 2;  // starting phase

        const p = {
            emoji: emoji,
            x: 0.1 * phoneW + Math.random() * 0.8 * phoneW,
            y: phoneH + 20,
            baseX: 0, // set after x is known
            vy: -(0.18 + Math.random() * 0.32),
            opacity: 0.28 + Math.random() * 0.14,
            size: 18 + Math.random() * 16,
            sizeBase: 0, // set below
            rotation: (Math.random() - 0.5) * 0.6,
            rotSpeed: (Math.random() - 0.5) * 0.012, // much faster rotation
            life: 0,
            maxLife: 1.4 + Math.random() * 0.6,
            // Curve params
            waveAmp: waveAmp,
            waveFreq: waveFreq,
            wavePhase: wavePhase,
            // Size pulsing
            sizePulseSpeed: 0.03 + Math.random() * 0.02,
            sizePulseAmp: 0.12 + Math.random() * 0.1,
            seed: Math.random() * 1000
        };
        p.baseX = p.x;
        p.sizeBase = p.size;

        if (particles.length >= MAX_PARTICLES) {
            let oldest = 0;
            for (let i = 1; i < particles.length; i++) {
                if (particles[i].life > particles[oldest].life) oldest = i;
            }
            particles[oldest] = p;
        } else {
            particles.push(p);
        }
    }

    function tick(beatPulse) {
        if (!ctx || !canvas) return;
        if (particles.length === 0 && pendingSpawns.length === 0) return;

        frame++;
        const bp = beatPulse || 0;

        // Handle staggered spawns
        for (let i = pendingSpawns.length - 1; i >= 0; i--) {
            pendingSpawns[i].delay--;
            if (pendingSpawns[i].delay <= 0) {
                addParticle(pendingSpawns[i].emoji);
                pendingSpawns.splice(i, 1);
            }
        }

        // Clear
        ctx.clearRect(0, 0, phoneW, phoneH);

        for (let i = particles.length - 1; i >= 0; i--) {
            const p = particles[i];
            p.life += 0.0015;

            if (p.life >= p.maxLife) {
                particles.splice(i, 1);
                continue;
            }

            const lifePct = p.life / p.maxLife;

            // Curved path: sinusoidal horizontal drift
            p.y += p.vy - bp * 0.25;
            p.baseX += Math.sin(frame * 0.003 + p.seed) * 0.05; // very slow global drift
            p.x = p.baseX + Math.sin(frame * p.waveFreq + p.wavePhase) * p.waveAmp * phoneW * 0.06;

            // Rotation: accelerates slightly as it rises, with beat bump
            p.rotation += p.rotSpeed + bp * 0.02 * Math.sign(p.rotSpeed);

            // Size pulsing: breathes in and out
            const sizePulse = 1 + Math.sin(frame * p.sizePulseSpeed + p.seed) * p.sizePulseAmp;
            const currentSize = p.sizeBase * sizePulse * (1 + bp * 0.08);

            // Fade: smooth ease-in at start, ease-out at end
            let alpha;
            if (lifePct < 0.1) {
                alpha = p.opacity * (lifePct / 0.1); // fade in over first 10%
            } else if (lifePct > 0.7) {
                alpha = p.opacity * (1 - (lifePct - 0.7) / 0.3); // fade out over last 30%
            } else {
                alpha = p.opacity;
            }

            if (alpha < 0.005) continue;

            // Render
            ctx.save();
            ctx.filter = 'grayscale(1) brightness(0.7)';
            ctx.globalAlpha = alpha;
            ctx.translate(p.x, p.y);
            ctx.rotate(p.rotation);
            ctx.font = Math.round(currentSize) + 'px serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(p.emoji, 0, 0);
            ctx.restore();
        }
    }

    function clear() {
        particles = [];
        pendingSpawns = [];
        frame = 0;
        lastTrackId = '';
        lastLineIndex = -1;
        cachedPoolTrack = '';
        cachedPool = [];
        if (ctx && canvas) ctx.clearRect(0, 0, phoneW, phoneH);
    }

    return { init, spawnSymbols, tick, clear };
})();
