import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FileTree } from './FileTree';
import type { StreamlitFileSummary } from '@/lib/types';

const files: StreamlitFileSummary[] = [
  { path: 'app.py', content_type: 'text/x-python', size: 1, is_entrypoint: true, updated_at: '' },
  { path: 'data.csv', content_type: 'text/csv', size: 1, is_entrypoint: false, updated_at: '' },
];

function renderTree(overrides: Partial<React.ComponentProps<typeof FileTree>> = {}) {
  const props = {
    files,
    active: 'app.py',
    onSelect: vi.fn(),
    onUpload: vi.fn(),
    onDelete: vi.fn(),
    onCreateFile: vi.fn(),
    onRenameFile: vi.fn(),
    ...overrides,
  };
  render(<FileTree {...props} />);
  return props;
}

afterEach(() => vi.restoreAllMocks());

describe('FileTree', () => {
  it('creates a new file from the prompt value', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('helper.py');
    const props = renderTree();
    await userEvent.click(screen.getByTitle('New file'));
    expect(props.onCreateFile).toHaveBeenCalledWith('helper.py');
  });

  it('does not create a file when the prompt is cancelled', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue(null);
    const props = renderTree();
    await userEvent.click(screen.getByTitle('New file'));
    expect(props.onCreateFile).not.toHaveBeenCalled();
  });

  it('renames a non-protected file', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('renamed.csv');
    const props = renderTree();
    // Only data.csv is renamable; app.py/requirements.txt are protected.
    await userEvent.click(screen.getByTitle('Rename'));
    expect(props.onRenameFile).toHaveBeenCalledWith('data.csv', 'renamed.csv');
  });

  it('blocks creating a file that already exists', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('data.csv');
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {});
    const props = renderTree();
    await userEvent.click(screen.getByTitle('New file'));
    expect(props.onCreateFile).not.toHaveBeenCalled();
    expect(alertSpy).toHaveBeenCalled();
  });
});
