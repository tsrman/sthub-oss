import { describe, it, expect } from 'vitest';

import { bytesToBase64 } from './base64';

describe('bytesToBase64', () => {
  it('encodes a small byte array', () => {
    const bytes = new TextEncoder().encode('hello, streamlit');
    expect(bytesToBase64(bytes)).toBe(Buffer.from(bytes).toString('base64'));
  });

  it('encodes an empty array', () => {
    expect(bytesToBase64(new Uint8Array(0))).toBe('');
  });

  it('encodes a large binary without overflowing the call stack', () => {
    // 1 MB — the naive String.fromCharCode(...bytes) approach dies here.
    const bytes = new Uint8Array(1024 * 1024);
    for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 31 + 7) % 256;
    expect(bytesToBase64(bytes)).toBe(Buffer.from(bytes).toString('base64'));
  });
});
