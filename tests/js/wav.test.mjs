import { test } from "node:test";
import assert from "node:assert/strict";
import { encodeWav, resample } from "../../static/js/wav.js";

test("encodes a 24 kHz mono 16-bit WAV header", async () => {
  const blob = encodeWav(new Float32Array([0, 1, -1, 0.5]));
  const buf = new DataView(await blob.arrayBuffer());
  const tag = (o) => String.fromCharCode(...[0, 1, 2, 3].map((i) => buf.getUint8(o + i)));
  assert.equal(tag(0), "RIFF"); assert.equal(tag(8), "WAVE"); assert.equal(tag(36), "data");
  assert.equal(buf.getUint32(24, true), 24000); assert.equal(buf.getUint16(22, true), 1);
  assert.equal(buf.getUint16(34, true), 16); assert.equal(buf.getUint32(40, true), 8);
  assert.equal(buf.getInt16(46, true), 32767); assert.equal(buf.getInt16(48, true), -32768);
});

test("resamples 48k to 24k by half", () => {
  assert.equal(resample(new Float32Array(480), 48000).length, 240);
  const same = new Float32Array(10);
  assert.equal(resample(same, 24000), same);
});
