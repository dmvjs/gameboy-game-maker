// Game Boy Color colors are 15-bit: 5 bits (0-31) per channel. The editor stores colors that way
// so anything you can pick is exactly what the hardware shows.

export const DMG_SHADES = [[255, 255, 255], [170, 170, 170], [85, 85, 85], [0, 0, 0]];

export const expand = v => (v << 3) | (v >> 2);
export const snap = v8 => Math.round(Math.min(255, Math.max(0, v8)) * 31 / 255);

export const to8 = ([r, g, b]) => [expand(r), expand(g), expand(b)];
export const from8 = ([r, g, b]) => [snap(r), snap(g), snap(b)];

export function sameColor(a, b) {
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2];
}

export function hex(c5) {
  return '#' + to8(c5).map(v => v.toString(16).padStart(2, '0')).join('');
}

export function parseHex(text) {
  const m = /^#?([0-9a-f]{6}|[0-9a-f]{3})$/i.exec(text.trim());
  if (!m) return null;
  let h = m[1];
  if (h.length === 3) h = [...h].map(ch => ch + ch).join('');
  return from8([0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)));
}

// Perceived brightness, 0-255.
export function luminance(c5) {
  const [r, g, b] = to8(c5);
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

// How a color looks on a real Game Boy Color screen, which is darker and less saturated than a
// modern display. Same curve as the Gambatte emulator.
export function gbcScreen([r, g, b]) {
  return [
    Math.min(255, (r * 13 + g * 2 + b) >> 1),
    Math.min(255, (g * 3 + b) << 1),
    Math.min(255, (r * 3 + g * 2 + b * 11) >> 1),
  ];
}

export function rgbToHsv([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  let h = 0;
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h = (h * 60 + 360) % 360;
  }
  return [h, max ? d / max : 0, max];
}

export function hsvToRgb([h, s, v]) {
  const c = v * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = v - c;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}
