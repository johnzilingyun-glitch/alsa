import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

const { lucideMock } = vi.hoisted(() => {
  const icons = ['MessageSquare', 'Send', 'Loader2', 'Share2', 'CheckCircle2', 'ChevronDown', 'ChevronUp'];
  const m: Record<string, any> = {};
  icons.forEach(n => { m[n] = () => null; });
  return { lucideMock: m };
});
vi.mock('lucide-react', () => lucideMock);

vi.mock('motion/react', () => ({
  motion: { div: ({ children, ...props }: any) => <div {...props}>{children}</div> },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}));

import { useAnalysisStore } from '../../../stores/useAnalysisStore';
import { useUIStore } from '../../../stores/useUIStore';

import { ChatSection } from '../ChatSection';

const defaultProps = { onSendChatReport: vi.fn(), onChat: vi.fn() };

beforeEach(() => {
  useAnalysisStore.setState({ chatMessage: '', chatHistory: [] });
  useUIStore.setState({ isChatting: false, isGeneratingReport: false, isSendingReport: false, reportStatus: null });
});

describe('ChatSection', () => {
  it('renders chat title and prompts', () => {
    render(<ChatSection {...defaultProps} />);
    expect(screen.getByText('analysis.tools.chat_title')).toBeTruthy();
    expect(screen.getByText('analysis.tools.chat_description')).toBeTruthy();
  });

  it('shows chat history messages', () => {
    useAnalysisStore.setState({
      chatHistory: [
        { id: '1', role: 'user', content: 'Is this a good buy?' },
        { id: '2', role: 'ai', content: 'Based on fundamentals...' },
      ],
    });
    render(<ChatSection {...defaultProps} />);
    expect(screen.getByText('Is this a good buy?')).toBeTruthy();
    expect(screen.getByText('Based on fundamentals...')).toBeTruthy();
  });

  it('calls onChat when send button clicked with message', () => {
    useAnalysisStore.setState({ chatMessage: 'test question' });
    const onChat = vi.fn();
    render(<ChatSection {...defaultProps} onChat={onChat} />);
    const sendBtns = screen.getAllByRole('button').filter(b => !b.disabled && b.innerHTML);
    fireEvent.click(sendBtns[sendBtns.length - 1]);
    expect(onChat).toHaveBeenCalled();
  });

  it('shows loading indicator when isChatting', () => {
    useUIStore.setState({ isChatting: true });
    render(<ChatSection {...defaultProps} />);
    expect(screen.getByText('analysis.tools.ai_thinking')).toBeTruthy();
  });

  it('shows success status on report sent', () => {
    useUIStore.setState({ reportStatus: 'success' });
    useAnalysisStore.setState({ chatHistory: [{ id: '1', role: 'user', content: 'x' }] });
    render(<ChatSection {...defaultProps} />);
    expect(screen.getByText('analysis.actions.sent')).toBeTruthy();
  });

  it('toggles collapse state', () => {
    render(<ChatSection {...defaultProps} />);
    fireEvent.click(screen.getByTitle('收起'));
    expect(screen.getByTitle('展开')).toBeTruthy();
  });
});
