import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { HistoryModal } from '../HistoryModal';
import React from 'react';

// Mock the services
vi.mock('../../services/adminService', () => ({
  getHistoryContext: vi.fn().mockResolvedValue([
    { id: '1', stockInfo: { name: 'Stock A', symbol: 'A', lastUpdated: '2026-03-30 10:00:00' } },
    { id: '2', stockInfo: { name: 'Stock B', symbol: 'B', lastUpdated: '2026-03-30 10:00:00' } },
    { id: '3', stockInfo: { name: 'Stock A', symbol: 'A', lastUpdated: '2026-03-30 10:00:00' } },
  ]),
  saveAnalysisToHistory: vi.fn()
}));

vi.mock('../../services/aiService', () => ({
  getHistoryContext: vi.fn().mockResolvedValue([
    { id: '1', stockInfo: { name: 'Stock A', symbol: 'A', lastUpdated: '2026-03-30 10:00:00' } },
    { id: '2', stockInfo: { name: 'Stock B', symbol: 'B', lastUpdated: '2026-03-30 10:00:00' } },
    { id: '3', stockInfo: { name: 'Stock A', symbol: 'A', lastUpdated: '2026-03-30 10:00:00' } },
  ])
}));

describe('HistoryModal Component', () => {
  it('renders history items correctly', async () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    
    render(<HistoryModal isOpen={true} onClose={onClose} onSelect={onSelect} />);
    
    // Wait for items to load by checking for text
    const stockAItems = await screen.findAllByText('Stock A');
    expect(stockAItems.length).toBe(2);
    expect(await screen.findByText('Stock B')).toBeDefined();
    
    const items = screen.getAllByRole('button');
    // 3 items + 1 close button
    expect(items.length).toBeGreaterThanOrEqual(4);
  });

  it('handles items without IDs by generating unique keys', async () => {
    const { getHistoryContext } = await import('../../services/aiService');
    (getHistoryContext as any).mockResolvedValueOnce([
      { stockInfo: { name: 'No ID 1', symbol: 'N1', lastUpdated: '2026-03-30 10:00:00' } },
      { stockInfo: { name: 'No ID 2', symbol: 'N1', lastUpdated: '2026-03-30 10:00:00' } }, // Same symbol/time
    ]);

    const onSelect = vi.fn();
    const onClose = vi.fn();
    
    // If keys are not unique, React will log an error (which we could spy on, but usually render will just work)
    // The main goal is to ensure it renders both items.
    render(<HistoryModal isOpen={true} onClose={onClose} onSelect={onSelect} />);
    
    expect(await screen.findByText('No ID 1')).toBeDefined();
    expect(await screen.findByText('No ID 2')).toBeDefined();
  });
});
