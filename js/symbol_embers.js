// ═══════════════════════════════════════════════════════════════
// Fire Embers — warm-toned spark particles rising through phone frame
// Beat-reactive: surge on kicks, glow on energy
// ═══════════════════════════════════════════════════════════════

const SymbolEmbers = (function () {
    'use strict';

    const MAX_PARTICLES = 40;
    let canvas = null;
    let ctx = null;
    let particles = [];
    let frame = 0;
    let phoneW = 0;
    let phoneH = 0;
    let dpr = 1;

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

    function spawnSymbols() {
        // Spawn 4-6 sparks per line change
        const count = 4 + Math.floor(Math.random() * 3);
        for (let i = 0; i < count; i++) {
            addParticle(i * 6);
        }
    }

    function addParticle(delay) {
        const p = {
            x: 0.08 * phoneW + Math.random() * 0.84 * phoneW,
            y: phoneH + 10,
            baseX: 0,
            vy: -(0.12 + Math.random() * 0.28),
            size: 1.0 + Math.random() * 2.2,
            life: 0,
            maxLife: 1.2 + Math.random() * 0.8,
            hue: 15 + Math.random() * 30,       // orange-gold range
            sat: 70 + Math.random() * 20,
            waveAmp: 0.3 + Math.random() * 0.8,
            waveFreq: 0.01 + Math.random() * 0.008,
            wavePhase: Math.random() * Math.PI * 2,
            seed: Math.random() * 1000,
            delay: delay || 0
        };
        p.baseX = p.x;

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
        if (particles.length === 0) return;

        frame++;
        const bp = beatPulse || 0;

        ctx.clearRect(0, 0, phoneW, phoneH);

        for (let i = particles.length - 1; i >= 0; i--) {
            const p = particles[i];

            // Stagger delay
            if (p.delay > 0) { p.delay--; continue; }

            p.life += 0.0018;

            if (p.life >= p.maxLife) {
                particles.splice(i, 1);
                continue;
            }

            const lifePct = p.life / p.maxLife;

            // Movement: gentle curve, beat surges upward
            p.y += p.vy - bp * 0.4;
            p.baseX += Math.sin(frame * 0.002 + p.seed) * 0.03;
            p.x = p.baseX + Math.sin(frame * p.waveFreq + p.wavePhase) * p.waveAmp * phoneW * 0.04;

            // Size: breathes with beat
            const sizePulse = 1 + Math.sin(frame * 0.025 + p.seed) * 0.15;
            const currentSize = p.size * sizePulse * (1 + bp * 0.5);

            // Fade: ease in/out
            let alpha;
            if (lifePct < 0.08) {
                alpha = lifePct / 0.08;
            } else if (lifePct > 0.6) {
                alpha = 1 - (lifePct - 0.6) / 0.4;
            } else {
                alpha = 1;
            }
            // Beat brightens
            alpha *= (0.25 + bp * 0.35);
            if (alpha < 0.005) continue;

            // Draw: warm dot with soft glow
            const bright = 50 + bp * 15;

            // Outer glow
            ctx.beginPath();
            ctx.arc(p.x, p.y, currentSize * 3, 0, Math.PI * 2);
            ctx.fillStyle = `hsla(${p.hue}, ${p.sat}%, ${bright}%, ${alpha * 0.08})`;
            ctx.fill();

            // Core spark
            ctx.beginPath();
            ctx.arc(p.x, p.y, currentSize, 0, Math.PI * 2);
            ctx.fillStyle = `hsla(${p.hue}, ${p.sat}%, ${bright + 10}%, ${alpha * 0.6})`;
            ctx.fill();
        }
    }

    function clear() {
        particles = [];
        frame = 0;
        if (ctx && canvas) ctx.clearRect(0, 0, phoneW, phoneH);
    }

    return { init, spawnSymbols, tick, clear };
})();
