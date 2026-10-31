/**
 * Synthesizes a crisp, subtle mechanical switch sound using the Web Audio API.
 * Completely client-side with zero external assets or network dependencies.
 */
export const playLampClickSound = (isTurningOn) => {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;

    const ctx = new AudioContextClass();
    if (ctx.state === 'suspended') {
      ctx.resume();
    }

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    const now = ctx.currentTime;

    osc.type = 'triangle';
    if (isTurningOn) {
      osc.frequency.setValueAtTime(720, now);
      osc.frequency.exponentialRampToValueAtTime(280, now + 0.035);
    } else {
      osc.frequency.setValueAtTime(360, now);
      osc.frequency.exponentialRampToValueAtTime(160, now + 0.035);
    }

    gain.gain.setValueAtTime(0.07, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start(now);
    osc.stop(now + 0.045);

    setTimeout(() => {
      try {
        ctx.close();
      } catch (err) {}
    }, 100);
  } catch (e) {
    // Fail gracefully if Web Audio is blocked or unsupported
  }
};
