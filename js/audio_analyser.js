// audio_analyser.js
// Real-time audio analysis using Web Audio API.
//
// Uses captureStream() — taps into the audio for frequency analysis
// WITHOUT rerouting audio output. The <audio> element plays normally.
// No createMediaElementSource(), no audio hijacking, no silence bugs.

const AudioAnalyser = (() => {
    let audioContext = null;
    let analyser = null;
    let sourceNode = null;
    let connected = false;
    let connecting = false;

    const FFT_SIZE = 2048;
    const SMOOTHING = 0.6;

    let frequencyData = null;
    let timeDomainData = null;

    let lastBassEnergy = 0;
    let bassEnergyHistory = null;
    const HISTORY_SIZE = 43;
    let historyIdx = 0;
    let lastBeatTime = 0;
    const MIN_BEAT_INTERVAL = 0.18;

    const state = {
        bass: 0, lowMid: 0, mid: 0, highMid: 0, treble: 0,
        overall: 0, beatPulse: 0, beatDetected: false, spectralCentroid: 0,
    };

    const SPEED = {
        bass: 12, lowMid: 10, mid: 8, highMid: 15, treble: 18,
        overall: 6, beatPulse: 6, spectralCentroid: 5,
    };

    async function connect(audioElement) {
        if (connected || connecting) return connected;
        connecting = true;
        try {
            // Check captureStream support
            const captureFn = audioElement.captureStream || audioElement.mozCaptureStream;
            if (!captureFn) {
                console.warn('AudioAnalyser: captureStream not supported in this browser');
                connecting = false;
                return false;
            }

            // Reuse existing AudioContext + analyser if available (reconnect case)
            if (!audioContext) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            await audioContext.resume();

            if (!analyser) {
                analyser = audioContext.createAnalyser();
                analyser.fftSize = FFT_SIZE;
                analyser.smoothingTimeConstant = SMOOTHING;
                analyser.minDecibels = -90;
                analyser.maxDecibels = -10;
            }

            // captureStream() — analysis only, does NOT touch audio output.
            // The <audio> element keeps playing through its normal path.
            // Fresh stream captures the current audio.src.
            const stream = captureFn.call(audioElement);
            sourceNode = audioContext.createMediaStreamSource(stream);
            sourceNode.connect(analyser);
            // Do NOT connect analyser to audioContext.destination — that would cause echo.

            if (!frequencyData) {
                frequencyData = new Uint8Array(analyser.frequencyBinCount);
                timeDomainData = new Uint8Array(analyser.frequencyBinCount);
                bassEnergyHistory = new Float32Array(HISTORY_SIZE);
            }

            connected = true;
            connecting = false;
            return true;
        } catch (e) {
            console.warn('AudioAnalyser: ' + e.message);
            connecting = false;
            try { if (audioContext) audioContext.close(); } catch(x) {}
            audioContext = null;
            analyser = null;
            sourceNode = null;
            return false;
        }
    }

    function resume() {
        if (audioContext && audioContext.state === 'suspended') {
            audioContext.resume();
        }
    }

    function analyse(dt, audioTime) {
        if (!connected || !analyser) return state;

        try {
            analyser.getByteFrequencyData(frequencyData);
            analyser.getByteTimeDomainData(timeDomainData);
        } catch (e) {
            return state;
        }

        const sampleRate = audioContext.sampleRate;
        const binCount = analyser.frequencyBinCount;
        const nyquist = sampleRate / 2;

        const bassEnd = Math.round(250 / nyquist * binCount);
        const lowMidEnd = Math.round(500 / nyquist * binCount);
        const midEnd = Math.round(2000 / nyquist * binCount);
        const highMidEnd = Math.round(4000 / nyquist * binCount);
        const trebleEnd = Math.round(16000 / nyquist * binCount);

        const rawBass = bandEnergy(1, bassEnd);
        const rawLowMid = bandEnergy(bassEnd, lowMidEnd);
        const rawMid = bandEnergy(lowMidEnd, midEnd);
        const rawHighMid = bandEnergy(midEnd, highMidEnd);
        const rawTreble = bandEnergy(highMidEnd, trebleEnd);

        let rmsSum = 0;
        for (let i = 0; i < timeDomainData.length; i++) {
            const a = (timeDomainData[i] / 128.0) - 1.0;
            rmsSum += a * a;
        }
        const rawOverall = Math.sqrt(rmsSum / timeDomainData.length);

        let wSum = 0, mSum = 0;
        for (let i = 1; i < binCount; i++) {
            const freq = (i / binCount) * nyquist;
            wSum += freq * frequencyData[i];
            mSum += frequencyData[i];
        }
        const rawCentroid = mSum > 0 ? (wSum / mSum) / nyquist : 0;

        const bassSquared = rawBass * rawBass;
        bassEnergyHistory[historyIdx] = bassSquared;
        historyIdx = (historyIdx + 1) % HISTORY_SIZE;

        let avgBass = 0;
        for (let i = 0; i < HISTORY_SIZE; i++) avgBass += bassEnergyHistory[i];
        avgBass /= HISTORY_SIZE;

        const threshold = Math.max(avgBass * 1.4, 0.06);

        state.beatDetected = false;
        if (bassSquared > threshold &&
            bassSquared > lastBassEnergy &&
            (audioTime - lastBeatTime) > MIN_BEAT_INTERVAL) {
            state.beatDetected = true;
            lastBeatTime = audioTime;
            state.beatPulse = Math.min(rawBass * 2.5, 1.0);
        }
        lastBassEnergy = bassSquared;

        smoothVal('bass', rawBass, dt);
        smoothVal('lowMid', rawLowMid, dt);
        smoothVal('mid', rawMid, dt);
        smoothVal('highMid', rawHighMid, dt);
        smoothVal('treble', rawTreble, dt);
        smoothVal('overall', rawOverall, dt);
        smoothVal('spectralCentroid', rawCentroid, dt);

        if (!state.beatDetected) {
            state.beatPulse += (0 - state.beatPulse) * (1 - Math.exp(-SPEED.beatPulse * dt));
        }

        return state;
    }

    function bandEnergy(startBin, endBin) {
        if (startBin >= endBin) return 0;
        let sum = 0;
        for (let i = startBin; i < endBin; i++) sum += frequencyData[i];
        return sum / ((endBin - startBin) * 255);
    }

    function smoothVal(key, target, dt) {
        const sp = SPEED[key] || 8;
        state[key] += (target - state[key]) * (1 - Math.exp(-sp * dt));
    }

    function getState() { return state; }
    function isActive() { return connected && audioContext && audioContext.state === 'running'; }

    function disconnect() {
        if (sourceNode) {
            try { sourceNode.disconnect(); } catch (_) {}
            sourceNode = null;
        }
        connected = false;
        connecting = false;
        // Keep audioContext + analyser alive — just detach the old source
    }

    function reconnect(audioElement) {
        disconnect();
        return connect(audioElement);
    }

    function reset() {
        lastBassEnergy = 0;
        historyIdx = 0;
        lastBeatTime = 0;
        if (bassEnergyHistory) bassEnergyHistory.fill(0);
        Object.keys(state).forEach(k => { state[k] = typeof state[k] === 'boolean' ? false : 0; });
    }

    return { connect, disconnect, reconnect, resume, analyse, getState, isActive, reset };
})();
