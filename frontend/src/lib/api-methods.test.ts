import { describe, it, expect } from 'vitest';
import { getApiErrorMessage } from './api-methods';

describe('getApiErrorMessage', () => {
  it('returns plain string errors as-is', () => {
    expect(getApiErrorMessage('boom')).toBe('boom');
  });

  it('extracts the backend {error: {message}} envelope', () => {
    const err = Object.assign(new Error('Request failed'), {
      response: { data: { error: { code: 'quota_exceeded', message: 'Quota exceeded' } } },
    });
    expect(getApiErrorMessage(err)).toBe('Quota exceeded');
  });

  it('falls back to {detail}', () => {
    const err = Object.assign(new Error('Request failed'), {
      response: { data: { detail: 'Not found' } },
    });
    expect(getApiErrorMessage(err)).toBe('Not found');
  });

  it('falls back to the Error message when no response body', () => {
    expect(getApiErrorMessage(new Error('Network Error'))).toBe('Network Error');
  });

  it('returns a generic message for unknown values', () => {
    expect(getApiErrorMessage(null)).toBe('An error occurred');
    expect(getApiErrorMessage(42)).toBe('An error occurred');
  });
});
