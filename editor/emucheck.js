// Boots a ROM in binjgb for a fixed number of frames and returns the final RGBA frame.
// Kept free of DOM code so it can be tested outside a browser.

const TICKS_PER_FRAME = 70224;
const EVENT_UNTIL_TICKS = 4;
export const SCREEN_W = 160;
export const SCREEN_H = 144;

export async function runRomFrames(Binjgb, romBytes, frames, moduleArgs = {}, colorCurve = 0) {
  const Module = await Binjgb(moduleArgs);
  const size = (romBytes.byteLength + 0x7fff) & ~0x7fff;
  const romPtr = Module._malloc(size);
  new Uint8Array(Module.HEAP8.buffer, romPtr, size).fill(0).set(romBytes);
  const e = Module._emulator_new_simple(romPtr, size, 44100, 4096, colorCurve);
  if (!e) {
    Module._free(romPtr);
    throw new Error('The emulator rejected the ROM.');
  }
  try {
    const target = Module._emulator_get_ticks_f64(e) + frames * TICKS_PER_FRAME;
    while (!(Module._emulator_run_until_f64(e, target) & EVENT_UNTIL_TICKS)) {}
    const ptr = Module._get_frame_buffer_ptr(e);
    const len = Module._get_frame_buffer_size(e);
    return new Uint8Array(Module.HEAP8.buffer, ptr, len).slice();
  } finally {
    Module._emulator_delete(e);
    Module._free(romPtr);
  }
}

// The self-test ROM draws four 40px bands, lightest on the left. Checks that the emulator shows
// four distinct shades getting darker left to right.
export function checkSelftestFrame(rgba) {
  const lum = x => {
    const i = (72 * SCREEN_W + x) * 4;
    return 0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2];
  };
  const bands = [20, 60, 100, 140].map(lum);
  const ok = bands.every((v, i) => i === 0 || v < bands[i - 1] - 8);
  return { ok, bands: bands.map(Math.round) };
}
