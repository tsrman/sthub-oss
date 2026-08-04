import { describe, it, expect } from 'vitest';

import { normalizeHex } from './MonacoEditor';

describe('normalizeHex', () => {
  it('expands 3-digit hex', () => {
    expect(normalizeHex('#fff', '#000000')).toBe('#ffffff');
  });

  it('expands 4-digit hex, dropping the alpha nibble', () => {
    expect(normalizeHex('#fffa', '#000000')).toBe('#ffffff');
  });

  it('passes 6-digit hex through', () => {
    expect(normalizeHex('#aabbcc', '#000000')).toBe('#aabbcc');
  });

  it('truncates 8-digit hex, dropping the alpha byte', () => {
    expect(normalizeHex('#aabbccdd', '#000000')).toBe('#aabbcc');
  });

  it('falls back on named colours', () => {
    expect(normalizeHex('red', '#000000')).toBe('#000000');
  });

  it('falls back on rgb() notation', () => {
    expect(normalizeHex('rgb(1,2,3)', '#000000')).toBe('#000000');
  });
});
