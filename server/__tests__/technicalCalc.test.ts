import { describe, it, expect, vi } from 'vitest';
import axios from 'axios';
import { calcIndicators } from '../indicators/technicalCalc';

const { postMock } = vi.hoisted(() => ({
  postMock: vi.fn()
}));

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      post: postMock
    }))
  }
}));

describe('calcIndicators integration', () => {
  it('should call Python API and map results correctly', async () => {
    const mockedResponse = {
      data: {
        success: true,
        data: [{
          ma_5: 10.5,
          ma_20: 10.2,
          ma_60: 10.0,
          avg_volume_5: 1000,
          avg_volume_20: 900,
          resistance_short: 11.0,
          support_short: 9.0,
          resistance_long: 12.0,
          support_long: 8.0
        }]
      }
    };

    postMock.mockResolvedValue(mockedResponse);

    const result = await calcIndicators([10, 11, 10, 12, 11], [1000, 1100, 1000, 1200, 1100], [12, 12, 12, 12, 12], [9, 9, 9, 9, 9]);

    expect(result).toEqual({
      ma5: 10.5,
      ma20: 10.2,
      ma60: 10.0,
      avgVolume5: 1000,
      avgVolume20: 900,
      resistanceShort: 11.0,
      supportShort: 9.0,
      resistanceLong: 12.0,
      supportLong: 8.0,
      lastClose: 11
    });
  });
});
