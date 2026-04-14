import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock global fetch
global.fetch = vi.fn();

// Mock process.env
process.env.GEMINI_API_KEY = 'test-api-key';
