import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MessageBody } from './AiAssistant';

describe('MessageBody code-block actions', () => {
  it('shows the insert button for a complete fenced block', () => {
    render(
      <MessageBody
        text={'explanation\n```python\nprint(1)\n```\nend'}
        onInsertCode={() => {}}
      />
    );
    expect(screen.getByText('Insert into editor')).toBeInTheDocument();
  });

  it('hides the insert button while the block is still streaming', () => {
    render(<MessageBody text={'```python\nprint(1)'} onInsertCode={() => {}} />);
    expect(screen.queryByText('Insert into editor')).not.toBeInTheDocument();
  });

  it('hides the insert button when only the opening fence arrived', () => {
    render(<MessageBody text={'```python'} onInsertCode={() => {}} />);
    expect(screen.queryByText('Insert into editor')).not.toBeInTheDocument();
  });

  it('shows buttons for all completed blocks in one message', () => {
    render(
      <MessageBody
        text={'```\na=1\n```\ntext\n```\nb=2\n```'}
        onInsertCode={() => {}}
      />
    );
    expect(screen.getAllByText('Insert into editor')).toHaveLength(2);
  });
});
