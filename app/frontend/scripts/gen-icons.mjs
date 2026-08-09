#!/usr/bin/env node
/**
 * Generate the CyberRisk AI PWA icons as PNGs — no image tooling required.
 *
 * Pure Node (zlib) PNG writer: draws a solid ink-950 (#0b1220) background with
 * a simple blue shield glyph, rasterized manually at the requested size.
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

// Design tokens (hex → 0..255).
const BG = { r: 11, g: 18, b: 32 }; // ink-950
const SHIELD = { r: 96, g: 165, b: 250 }; // brand-400
const SHIELD_DARK = { r: 59, g: 130, b: 246 }; // brand-500

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

// --- shield glyph rasterization --------------------------------------------
// A shield is a pentagon: flat top, chamfered shoulders, point at the bottom.
// We draw it inside a normalized [0,1] box with the given inset, plus a
// centered "bolt" notch for the shield detail.
function insideShield(px, py, inset = 0.16) {
  // normalized center-of-box coordinates
  const x = px - 0.5;
  const y = py - 0.5;
  const s = 0.5 - inset; // half-extent of the shield shape

  // Shield silhouette (pointing down): top edge at y = -s, sides taper to a
  // point at (0, +s).
  const top = -s;
  const bottom = s;
  const side = (yy) => s * (1 - (yy - top) / (bottom - top)); // half-width at height yy
  if (y < top || y > bottom) return false;
  return Math.abs(x) <= side(y);
}

function inBolt(px, py) {
  // Small vertical "energy" tick in the shield's centre (rounded corners via
  // circle at the bottom). Normalized coords.
  const x = px - 0.5;
  let y = py - 0.5;
  const w = 0.10;
  const top = -0.16;
  const bottom = 0.26;
  if (x < -w || x > w) return false;
  if (y < top) return false;
  if (y <= bottom - w) return true; // rectangular stem
  // rounded cap at the bottom of the tick
  const dx = Math.abs(x);
  const dy = y - (bottom - w);
  return dx * dx + dy * dy <= w * w;
}

function shade(x, y) {
  const onShield = insideShield(x, y, 0.14);
  if (!onShield) return { ...BG, a: 255 };
  const inTick = inBolt(x, y);
  // Slight vertical gradient on the shield for depth.
  const t = Math.max(0, Math.min(1, (y - 0.14) / (0.5 - 0.14)));
  const col = inTick
    ? SHIELD_DARK
    : { r: Math.round(SHIELD.r * 0.92 + 0.08 * 255), g: SHIELD.g, b: SHIELD.b };
  const mix = (a, b, k) => Math.round(a + (b - a) * k);
  const base = {
    r: mix(SHIELD.r, col.r, t * 0.35),
    g: mix(SHIELD.g, col.g, t * 0.35),
    b: mix(SHIELD.b, col.b, t * 0.35),
  };
  return { ...base, a: 255 };
}

function rasterize(size) {
  const rgba = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const p = shade((x + 0.5) / size, (y + 0.5) / size);
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
