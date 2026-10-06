export class Sound {
  constructor() {
    this.enabled = false; this.context = null; this.motor = null;
    this.scene = 'home'; this.musicTimer = null; this.musicNotes = new Set();
  }
  toggle() {
    this.enabled = !this.enabled;
    if (this.enabled) {
      try {
        this.context ||= new (window.AudioContext || window.webkitAudioContext)();
        this.context.resume().then(() => this.startMusic()).catch(() => {});
      }
      catch { this.enabled = false; }
    } else { this.stopMotor(); this.stopMusic(); }
    return this.enabled;
  }
  setScene(scene) {
    this.scene = scene;
    if (scene === 'home') this.startMusic(); else this.stopMusic();
  }
  startMusic() {
    if (!this.enabled || !this.context || this.context.state !== 'running' || this.scene !== 'home' || this.musicTimer !== null) return;
    // Boucle originale « Promenade » : 4 accords, 24 secondes, sans fichier
    // distant ni échantillon. Les notes sont planifiées à l’horloge audio.
    const chords = [[48,60,64,67],[45,60,64,69],[41,60,65,69],[43,59,62,67]];
    const melody = [72,null,76,null,74,null,72,null,79,null,76,null,74,null,71,null];
    let step = 0, next = this.context.currentTime + .08;
    const schedule = () => {
      if (this.context.currentTime - next > 1) next = this.context.currentTime + .05;
      while (next < this.context.currentTime + .2) {
        const chord = chords[Math.floor(step / 16) % 4], beat = step % 16;
        if (beat === 0) for (const note of chord.slice(1)) this.musicNote(note, next, 5.7, .009, 'sine');
        if (beat % 4 === 0) this.musicNote(chord[0], next, .65, .032, 'sine');
        if (beat % 2 === 0) this.musicNote(chord[1 + (beat / 2) % 3] + 12, next, .24, .018, 'triangle');
        const lead = melody[beat];
        if (lead !== null) this.musicNote(lead + (Math.floor(step / 16) % 4 === 1 ? -3 : 0), next, .46, .012, 'sine');
        next += .375; step = (step + 1) % 64;
      }
    };
    schedule(); this.musicTimer = setInterval(schedule, 100);
  }
  musicNote(midi, start, duration, volume, type) {
    const oscillator = this.context.createOscillator(), gain = this.context.createGain();
    oscillator.type = type; oscillator.frequency.value = 440 * 2 ** ((midi - 69) / 12);
    gain.gain.setValueAtTime(0, start); gain.gain.linearRampToValueAtTime(volume, start + .04);
    gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
    oscillator.connect(gain); gain.connect(this.context.destination);
    const voice = {oscillator, gain}; this.musicNotes.add(voice);
    oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); this.musicNotes.delete(voice); };
    oscillator.start(start); oscillator.stop(start + duration + .03);
  }
  stopMusic() {
    clearInterval(this.musicTimer); this.musicTimer = null;
    if (!this.context) return;
    const now = this.context.currentTime;
    for (const {oscillator, gain} of this.musicNotes) {
      gain.gain.cancelScheduledValues(now); gain.gain.setTargetAtTime(0, now, .015); oscillator.stop(now + .06);
    }
  }
  beep(frequency = 580, duration = .07, volume = .04, delay = 0) {
    if (!this.enabled || !this.context) return;
    const start = this.context.currentTime + delay;
    const oscillator = this.context.createOscillator(), gain = this.context.createGain();
    oscillator.type = 'sine'; oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0, start); gain.gain.linearRampToValueAtTime(volume, start + .01);
    gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
    oscillator.connect(gain); gain.connect(this.context.destination);
    oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
    oscillator.start(start); oscillator.stop(start + duration + .02);
  }
  startMotor() {
    this.stopMotor();
    if (!this.enabled || !this.context) return;
    const oscillator = this.context.createOscillator(), gain = this.context.createGain();
    oscillator.type = 'triangle'; oscillator.frequency.value = 70; gain.gain.value = .008;
    oscillator.connect(gain); gain.connect(this.context.destination); oscillator.start();
    oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
    this.motor = { oscillator, gain };
  }
  stopMotor() { if (this.motor) { this.motor.oscillator.stop(); this.motor = null; } }
  finish(won) { this.stopMotor(); [0, 1, 2].forEach(i => this.beep((won ? 520 : 300) * (won ? 1 + i * .25 : 1 - i * .15), .18, .04, i * .12)); }
}
