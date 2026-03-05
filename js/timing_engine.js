// timing_engine.js
// Temporal coordinator — processes beat_times, energy_curve, sections, transition_points
// Provides timing state for all zone modules to consume

const TimingEngine = (() => {
    let beatTimes = [];
    let energyCurve = [];
    let sections = [];
    let transitionPoints = [];
    let bpm = 120;

    let lastBeatIdx = 0;
    let lastTransitionIdx = 0;
    let lastBeatTime = 0;
    let currentSectionIdx = -1;
    let beatCount = 0;

    const BEAT_DECAY = 0.08; // seconds for pulse decay
    const BEATS_PER_BAR = 4; // assume 4/4 time

    const listeners = { beat: [], sectionChange: [], transitionPoint: [] };

    function load(trackData) {
        beatTimes = trackData.beat_times || [];
        energyCurve = trackData.energy_curve || [];
        sections = trackData.sections || [];
        transitionPoints = trackData.transition_points || [];
        bpm = trackData.bpm || 120;
        reset();
    }

    function tick(currentTime) {
        const result = {
            energy: getEnergy(currentTime),
            beatPulse: 0,
            section: null,
            sectionChanged: false,
            isTransitionPoint: false,
            isDownbeat: false,
            beatCount: 0,
        };

        // Beat detection — advance through beat_times
        while (lastBeatIdx < beatTimes.length && currentTime >= beatTimes[lastBeatIdx]) {
            lastBeatTime = beatTimes[lastBeatIdx];
            lastBeatIdx++;
            beatCount++;
            for (const cb of listeners.beat) cb(lastBeatTime);
        }
        result.beatCount = beatCount;
        result.isDownbeat = (beatCount > 0 && beatCount % BEATS_PER_BAR === 1);

        // Beat pulse: exponential decay from last beat
        const timeSinceBeat = currentTime - lastBeatTime;
        if (timeSinceBeat >= 0 && timeSinceBeat < BEAT_DECAY) {
            result.beatPulse = 1.0 - (timeSinceBeat / BEAT_DECAY);
        }

        // Section tracking
        for (let i = 0; i < sections.length; i++) {
            if (currentTime >= sections[i].start && currentTime < sections[i].end) {
                if (i !== currentSectionIdx) {
                    currentSectionIdx = i;
                    result.sectionChanged = true;
                    for (const cb of listeners.sectionChange) cb(sections[i], i);
                }
                result.section = sections[i];
                break;
            }
        }

        // Transition point detection (within ±50ms window)
        while (lastTransitionIdx < transitionPoints.length &&
               currentTime >= transitionPoints[lastTransitionIdx] - 0.05) {
            if (currentTime <= transitionPoints[lastTransitionIdx] + 0.05) {
                result.isTransitionPoint = true;
                for (const cb of listeners.transitionPoint) cb(transitionPoints[lastTransitionIdx]);
            }
            lastTransitionIdx++;
        }

        return result;
    }

    // Binary search energy lookup with linear interpolation
    function getEnergy(time) {
        if (!energyCurve || energyCurve.length === 0) return 0.5;
        if (time <= energyCurve[0][0]) return energyCurve[0][1];
        const last = energyCurve[energyCurve.length - 1];
        if (time >= last[0]) return last[1];

        let lo = 0, hi = energyCurve.length - 1;
        while (lo < hi - 1) {
            const mid = (lo + hi) >> 1;
            if (energyCurve[mid][0] <= time) lo = mid;
            else hi = mid;
        }
        const t0 = energyCurve[lo][0], t1 = energyCurve[hi][0];
        const v0 = energyCurve[lo][1], v1 = energyCurve[hi][1];
        const frac = (t1 > t0) ? (time - t0) / (t1 - t0) : 0;
        return v0 + frac * (v1 - v0);
    }

    function on(event, callback) {
        if (listeners[event]) listeners[event].push(callback);
    }

    function reset() {
        lastBeatIdx = 0;
        lastTransitionIdx = 0;
        lastBeatTime = 0;
        currentSectionIdx = -1;
        beatCount = 0;
    }

    function getBpm() { return bpm; }

    return { load, tick, getEnergy, getBpm, on, reset };
})();
