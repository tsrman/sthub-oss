import { describe, it, expect } from 'vitest';
import { getLanguageFromPath, isTextFile, isImageFile, isTextPath } from './syntax';

describe('getLanguageFromPath', () => {
  it('maps known extensions', () => {
    expect(getLanguageFromPath('app.py')).toBe('python');
    expect(getLanguageFromPath('a.ts')).toBe('typescript');
    expect(getLanguageFromPath('c.yml')).toBe('yaml');
    expect(getLanguageFromPath('readme.md')).toBe('markdown');
  });

  it('falls back to plaintext for unknown/extensionless', () => {
    expect(getLanguageFromPath('data.bin')).toBe('plaintext');
    expect(getLanguageFromPath('Dockerfile')).toBe('plaintext');
  });
});

describe('isTextFile / isImageFile', () => {
  it('detects text content types', () => {
    expect(isTextFile('text/plain')).toBe(true);
    expect(isTextFile('application/json')).toBe(true);
    expect(isTextFile('image/png')).toBe(false);
  });

  it('detects image content types', () => {
    expect(isImageFile('image/png')).toBe(true);
    expect(isImageFile('image/svg+xml')).toBe(true);
    expect(isImageFile('text/plain')).toBe(false);
  });
});

describe('isTextPath', () => {
  it('recognises known text extensions', () => {
    expect(isTextPath('requirements.txt')).toBe(true);
    expect(isTextPath('config.toml')).toBe(true);
    expect(isTextPath('app.py')).toBe(true);
  });

  it('rejects binary/unknown extensions', () => {
    expect(isTextPath('logo.png')).toBe(false);
    expect(isTextPath('archive')).toBe(false);
  });
});
