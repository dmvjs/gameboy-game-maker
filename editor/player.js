// Runs a ROM live in binjgb and draws it to a canvas.

import { SCREEN_W, SCREEN_H } from './emucheck.js';

const TICKS_PER_SECOND = 4194304;
const EVENT_NEW_FRAME = 1;
const EVENT_AUDIO_BUFFER_FULL = 2;
const EVENT_UNTIL_TICKS = 4;
const AUDIO_FRAMES = 1024;        // ~21 ms per chunk: short, so sounds follow the buttons closely
const AUDIO_LEAD = 0.05;          // seconds of sound scheduled ahead of the speakers
const VOLUME = 2;                 // one channel peaks near 0.28: clear, not loud

// One audio context for the page. Browsers only start it after a click or key press.
let audioCtx = null;
export function audioContext() {
  if (!audioCtx && window.AudioContext) audioCtx = new AudioContext({ latencyHint: 'interactive' });
  if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
  return audioCtx;
}

// Clear the "Game Boy Color enhanced" header flag so the emulator boots as an original Game Boy.
// The ROM then detects original hardware and takes its grayscale path, like a real DMG would.
export function asOriginalGameBoy(rom) {
  const r = rom.slice();
  r[0x143] = 0;
  let x = 0;
  for (let i = 0x134; i < 0x14d; i++) x = (x - r[i] - 1) & 0xff;
  r[0x14d] = x;
  return r;
}

export class Player {
  static muted = localStorage.getItem('gbstage.muted') === '1';

  static async create(Binjgb, rom, canvas, { colorCurve = 0 } = {}) {
    return new Player(await Binjgb(), rom, canvas, colorCurve);
  }

  constructor(Module, rom, canvas, colorCurve) {
    this.Module = Module;
    const size = (rom.byteLength + 0x7fff) & ~0x7fff;
    this.romPtr = Module._malloc(size);
    new Uint8Array(Module.HEAP8.buffer, this.romPtr, size).fill(0).set(rom);
    this.audio = audioContext();
    const rate = this.audio ? this.audio.sampleRate : 44100;
    this.e = Module._emulator_new_simple(this.romPtr, size, rate, AUDIO_FRAMES, colorCurve);
    if (!this.e) {
      Module._free(this.romPtr);
      throw new Error('The emulator rejected the ROM.');
    }
    this.joypad = Module._joypad_new();
    Module._emulator_set_default_joypad_callback(this.e, this.joypad);
    this.ctx = canvas.getContext('2d');
    this.image = this.ctx.createImageData(SCREEN_W, SCREEN_H);
    this.raf = 0;
    this.last = 0;
    if (this.audio) {
      // The emulator's output is unsigned and quiet (one channel peaks near 0.14): boost it and
      // filter out the DC offset so sounds start and stop without clicks.
      this.out = this.audio.createGain();
      this.out.gain.value = Player.muted ? 0 : VOLUME;
      this.dc = this.audio.createBiquadFilter();
      this.dc.type = 'highpass';
      this.dc.frequency.value = 20;
      this.out.connect(this.dc);
      this.dc.connect(this.audio.destination);
      this.playAt = 0;
    }
  }

  // Schedule one chunk of the emulator's sound (unsigned 8-bit stereo) right after the last one.
  pushAudio() {
    if (!this.audio) return;
    const M = this.Module;
    const samples = new Uint8Array(M.HEAP8.buffer, M._get_audio_buffer_ptr(this.e), M._get_audio_buffer_capacity(this.e));
    const frames = Math.min(AUDIO_FRAMES, samples.length >> 1);
    const now = this.audio.currentTime;
    if (this.playAt < now || this.playAt > now + 4 * AUDIO_LEAD) this.playAt = now + AUDIO_LEAD;  // fell behind or ran ahead: resync
    const buf = this.audio.createBuffer(2, frames, this.audio.sampleRate);
    const left = buf.getChannelData(0), right = buf.getChannelData(1);
    for (let i = 0; i < frames; i++) {
      left[i] = samples[2 * i] / 255;
      right[i] = samples[2 * i + 1] / 255;
    }
    const src = this.audio.createBufferSource();
    src.buffer = buf;
    src.connect(this.out);
    if (this.rec) src.connect(this.rec.sound);
    src.start(this.playAt);
    this.playAt += frames / this.audio.sampleRate;
  }

  setMuted(muted) {
    Player.muted = muted;
    if (this.out) this.out.gain.value = muted ? 0 : VOLUME;
  }

  // Run the emulator for `seconds` of Game Boy time and show the last complete frame. (The frame
  // buffer fills in line by line, so copying it mid-frame would show half of one frame and half
  // of the next.)
  step(seconds) {
    const M = this.Module;
    const target = M._emulator_get_ticks_f64(this.e) + seconds * TICKS_PER_SECOND;
    for (;;) {
      const event = M._emulator_run_until_f64(this.e, target);
      if (event & EVENT_AUDIO_BUFFER_FULL) this.pushAudio();
      if (event & EVENT_NEW_FRAME) {
        this.image.data.set(new Uint8Array(M.HEAP8.buffer, M._get_frame_buffer_ptr(this.e), M._get_frame_buffer_size(this.e)));
      }
      if (event & EVENT_UNTIL_TICKS) break;
    }
    this.ctx.putImageData(this.image, 0, 0);
    if (this.rec) this.rec.ctx.drawImage(this.ctx.canvas, 0, 0, this.rec.canvas.width, this.rec.canvas.height);
  }

  // Record the session to a video: the screen at 4x (sharp pixels) and the game's sound, heard or muted.
  // stopRecording() resolves to { blob, ext }.
  startRecording() {
    if (this.rec || !window.MediaRecorder) return false;
    const canvas = document.createElement('canvas');
    canvas.width = SCREEN_W * 4; canvas.height = SCREEN_H * 4;
    const ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    const tracks = canvas.captureStream(60).getVideoTracks();
    let sound = null;
    if (this.audio) {                   // the same sound as the speakers get, at full volume
      sound = this.audio.createGain();
      sound.gain.value = VOLUME;
      const dc = this.audio.createBiquadFilter();
      dc.type = 'highpass'; dc.frequency.value = 20;
      const dest = this.audio.createMediaStreamDestination();
      sound.connect(dc); dc.connect(dest);
      tracks.push(...dest.stream.getAudioTracks());
    }
    // QuickTime's: H.264 and AAC in an MP4/QuickTime container, saved as .mov (Safari, and Chrome since 2024);
    // a browser without it (Firefox) records WebM.
    const type = ['video/mp4;codecs=avc1.42E01E,mp4a.40.2', 'video/mp4;codecs=avc1,mp4a', 'video/mp4',
                  'video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm']
      .find(t => MediaRecorder.isTypeSupported(t)) || '';
    const recorder = new MediaRecorder(new MediaStream(tracks), { mimeType: type, videoBitsPerSecond: 4e6 });
    const chunks = [];
    recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    recorder.start(1000);
    this.rec = { canvas, ctx, sound, recorder, chunks, ext: type.startsWith('video/mp4') ? 'mov' : 'webm' };
    ctx.drawImage(this.ctx.canvas, 0, 0, canvas.width, canvas.height);
    return true;
  }

  stopRecording() {
    const rec = this.rec;
    if (!rec) return Promise.resolve(null);
    this.rec = null;
    return new Promise(resolve => {
      rec.recorder.onstop = () => {
        if (rec.sound) rec.sound.disconnect();
        resolve({ blob: new Blob(rec.chunks, { type: rec.recorder.mimeType }), ext: rec.ext });
      };
      rec.recorder.stop();
    });
  }

  start() {
    const frame = now => {
      this.raf = requestAnimationFrame(frame);
      const dt = this.last ? Math.min((now - this.last) / 1000, 1 / 20) : 1 / 60;
      this.last = now;
      this.step(dt);
    };
    this.raf = requestAnimationFrame(frame);
  }

  // button: 'up' | 'down' | 'left' | 'right' | 'A' | 'B' | 'start' | 'select'
  setButton(button, pressed) {
    if (this.e) this.Module[`_set_joyp_${button}`](this.e, pressed ? 1 : 0);
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    if (this.out) { this.out.disconnect(); this.dc.disconnect(); this.out = null; }
    if (this.e) {
      for (const b of ['up', 'down', 'left', 'right', 'A', 'B', 'start', 'select']) this.setButton(b, false);
      this.Module._emulator_delete(this.e);
      this.Module._joypad_delete(this.joypad);
      this.Module._free(this.romPtr);
      this.e = 0;
    }
  }
}
