#!/usr/bin/env node
/**
 * Generate the Armageddon PWA icons as PNGs — no image tooling required.
 *
 * Pure Node (zlib) PNG writer: rasterizes the Armageddon brand mark from the
 * same geometry as src/components/ArmageddonMark.tsx (three silver capsule
 * drops flowing through a band into a gold teardrop) on a warm near-black
 * background, at the requested sizes.
 * Outputs:
 *   public/apple-touch-icon.png  (180x180)
 *   public/icon-192.png          (192x192)
 *   public/icon-512.png          (512x512)
 *
 * Run:  node scripts/gen-icons.mjs
 */

import { deflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

// Design tokens — the Armageddon identity: warm near-black canvas, gold drop.
const BG = { r: 10, g: 11, b: 13 }; // #0a0b0d ink-50 (dark)
const DROP_STOPS = [
  { at: 0.0, c: { r: 0xfe, g: 0xf6, b: 0xd0 } }, // #FEF6D0
  { at: 0.3, c: { r: 0xf6, g: 0xd6, b: 0x8d } }, // #F6D68D
  { at: 0.58, c: { r: 0xc3, g: 0x8f, b: 0x50 } }, // #C38F50
  { at: 0.82, c: { r: 0x6b, g: 0x44, b: 0x23 } }, // #6B4423
  { at: 1.0, c: { r: 0x1e, g: 0x12, b: 0x04 } }, // #1E1204
];
const CAP_STOPS = [
  { at: 0.0, c: { r: 0xff, g: 0xff, b: 0xff } },
  { at: 0.2, c: { r: 0xff, g: 0xff, b: 0xff } },
  { at: 0.3, c: { r: 0xe9, g: 0xe9, b: 0xec } }, // #E9E9EC
  { at: 1.0, c: { r: 0x61, g: 0x64, b: 0x6b } }, // #61646B
];
const BAND_STOPS = [
  { at: 0.0, c: { r: 0x5d, g: 0x5e, b: 0x63 } }, // #5D5E63
  { at: 0.62, c: { r: 0x81, g: 0x7f, b: 0x7d } }, // #817F7D
  { at: 1.0, c: { r: 0xc3, g: 0x8f, b: 0x50 } }, // #C38F50
];

// --- tiny PNG encoder (RGBA8, zlib-deflated, no interlace) -----------------
function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, 'ascii');
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crc]);
}

function encodePNG(width, height, rgba) {
  const raw = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0; // filter: none
    rgba.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

// --- Armageddon mark geometry (viewBox 860x781) -----------------------------
const DROP_BBOX = { x: 386, y: 70, w: 862 - 386, h: 781 - 70 };

// Flatten the teardrop's four cubic beziers into a polygon for ray casting.
const CUBIC = 40; // segments per curve
function cubicPoint(x0, y0, c1x, c1y, c2x, c2y, x1, y1, t) {
  const u = 1 - t;
  return {
    x:
      u * u * u * x0 +
      3 * u * u * t * c1x +
      3 * u * t * t * c2x +
      t * t * t * x1,
    y:
      u * u * u * y0 +
      3 * u * u * t * c1y +
      3 * u * t * t * c2y +
      t * t * t * y1,
  };
}

const TEARDROP = (() => {
  const segs = [
    [630, 70, 855, 70, 865, 160, 862, 400],
    [862, 400, 859, 560, 810, 730, 600, 781],
    [600, 781, 430, 735, 385, 560, 386, 400],
    [386, 400, 387, 160, 405, 70, 630, 70],
  ];
  const poly = [];
  for (const [x0, y0, c1x, c1y, c2x, c2y, x1, y1] of segs) {
    for (let i = 0; i < CUBIC; i++) {
      const p = cubicPoint(x0, y0, c1x, c1y, c2x, c2y, x1, y1, i / CUBIC);
      poly.push(p);
    }
  }
  return poly;
})();

function inPolygon(poly, X, Y) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    if (a.y > Y !== b.y > Y && X < ((b.x - a.x) * (Y - a.y)) / (b.y - a.y) + a.x) {
      inside = !inside;
    }
  }
  return inside;
}

function inRoundedRect(X, Y, x0, y0, w, h, r) {
  const cx = Math.min(Math.max(X, x0 + r), x0 + w - r);
  const cy = Math.min(Math.max(Y, y0 + r), y0 + h - r);
  return (X - cx) * (X - cx) + (Y - cy) * (Y - cy) <= r * r;
}

const CAPSULES = [
  { x0: 5, y0: 0, w: 52, h: 150, r: 26 },
  { x0: 154, y0: 0, w: 52, h: 150, r: 26 },
  { x0: 299, y0: 0, w: 52, h: 150, r: 26 },
];
const BAND = { x0: -10, y0: 94, w: 510, h: 56 };

function stopColor(stops, k) {
  k = Math.max(0, Math.min(1, k));
  for (let i = 0; i < stops.length - 1; i++) {
    const a = stops[i];
    const b = stops[i + 1];
    if (k >= a.at && k <= b.at) {
      const t = (k - a.at) / (b.at - a.at);
      return {
        r: Math.round(a.c.r + (b.c.r - a.c.r) * t),
        g: Math.round(a.c.g + (b.c.g - a.c.g) * t),
        b: Math.round(a.c.b + (b.c.b - a.c.b) * t),
      };
    }
  }
  return stops[stops.length - 1].c;
}

function shade(X, Y) {
  // Drop gradient: radial in bbox space (cx=0.62, cy=0.34, r=0.8).
  if (inPolygon(TEARDROP, X, Y)) {
    const nx = (X - DROP_BBOX.x) / DROP_BBOX.w;
    const ny = (Y - DROP_BBOX.y) / DROP_BBOX.h;
    const d = Math.hypot((nx - 0.62) / 0.8, (ny - 0.34) / 0.8);
    return { ...stopColor(DROP_STOPS, d), a: 255 };
  }
  // Band (drawn under the capsules).
  if (
    X >= BAND.x0 &&
    X <= BAND.x0 + BAND.w &&
    Y >= BAND.y0 &&
    Y <= BAND.y0 + BAND.h
  ) {
    const k = (X - BAND.x0) / BAND.w;
    return { ...stopColor(BAND_STOPS, k), a: 255 };
  }
  // Three capsule drops.
  for (const cap of CAPSULES) {
    if (inRoundedRect(X, Y, cap.x0, cap.y0, cap.w, cap.h, cap.r)) {
      const k = (Y - cap.y0) / cap.h;
      return { ...stopColor(CAP_STOPS, k), a: 255 };
    }
  }
  return { ...BG, a: 255 };
}

function rasterize(size) {
  const rgba = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const p = shade(((x + 0.5) / size) * 860, ((y + 0.5) / size) * 781);
      const i = (y * size + x) * 4;
      rgba[i] = p.r;
      rgba[i + 1] = p.g;
      rgba[i + 2] = p.b;
      rgba[i + 3] = p.a;
    }
  }
  return encodePNG(size, size, rgba);
}

const outDir = resolve(root, 'public');
mkdirSync(outDir, { recursive: true });

for (const [name, size] of [
  ['apple-touch-icon.png', 180],
  ['icon-192.png', 192],
  ['icon-512.png', 512],
]) {
  const file = resolve(outDir, name);
  writeFileSync(file, rasterize(size));
  console.log(`wrote ${name} (${size}x${size})`);
}
