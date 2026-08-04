import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useParamsMock } = vi.hoisted(() => ({ useParamsMock: vi.fn() }));

vi.mock('next/navigation', () => ({ useParams: useParamsMock }));

import { useStreamlitId } from './useStreamlitId';

describe('useStreamlitId', () => {
  beforeEach(() => useParamsMock.mockReset());

  it('returns the string dynamic streamlit id from the current route', () => {
    useParamsMock.mockReturnValue({ id: 'streamlit-42' });

    expect(renderHook(() => useStreamlitId()).result.current).toBe('streamlit-42');
  });

  it('normalizes a catch-all route value to its first segment', () => {
    useParamsMock.mockReturnValue({ id: ['streamlit-42', 'settings'] });

    expect(renderHook(() => useStreamlitId()).result.current).toBe('streamlit-42');
  });
});
