import { describe, it, expect } from 'vitest';
import { extractJsonBlock, parseJsonResponse } from '../services/aiService';

describe('AI Service Helpers', () => {
  describe('extractJsonBlock', () => {
    it('should extract JSON from markdown fences', () => {
      const raw = 'Here is the result:\n```json\n{"key": "value"}\n```\nHope this helps!';
      expect(extractJsonBlock(raw)).toBe('{"key": "value"}');
    });

    it('should extract JSON from plain markdown fences', () => {
      const raw = '```\n{"key": "value"}\n```';
      expect(extractJsonBlock(raw)).toBe('{"key": "value"}');
    });

    it('should return raw string if it starts with {', () => {
      const raw = '{"key": "value"}';
      expect(extractJsonBlock(raw)).toBe('{"key": "value"}');
    });

    it('should find braces if no fences are present', () => {
      const raw = 'Some text before {"key": "value"} some text after';
      expect(extractJsonBlock(raw)).toBe('{"key": "value"}');
    });

    it('should throw error if no JSON is found', () => {
      const raw = 'Just some text without braces';
      expect(() => extractJsonBlock(raw)).toThrow('Gemini returned a non-JSON response');
    });

    it('should strip Gemini citation markers before extraction', () => {
      const raw = '[cite: analysis] {"key": "value"} [cite: 1]';
      expect(extractJsonBlock(raw)).toBe('{"key": "value"}');
    });

    it('should handle citation-only response gracefully', () => {
      const raw = '[cite: analysis report section 2]';
      expect(() => extractJsonBlock(raw)).toThrow('Gemini returned a non-JSON response');
    });

    it('should strip cite_start/cite_end markers', () => {
      const raw = '[cite_start]Some ref[cite_end] {"key": "value"}';
      expect(extractJsonBlock(raw)).toBe('{"key": "value"}');
    });
  });

  describe('parseJsonResponse', () => {
    it('should parse valid JSON', () => {
      const raw = '```json\n{"symbol": "AAPL", "price": 150}\n```';
      const result = parseJsonResponse<{ symbol: string; price: number }>(raw);
      expect(result.symbol).toBe('AAPL');
      expect(result.price).toBe(150);
    });

    it('should throw error for invalid JSON', () => {
      const raw = '```json\n{"symbol": "AAPL", "price": 150\n```'; // Missing closing brace
      expect(() => parseJsonResponse(raw)).toThrow('Failed to parse Gemini JSON response');
    });

    it('should handle trailing commas', () => {
      const raw = '{"name": "test", "value": 42, }';
      const result = parseJsonResponse<{ name: string; value: number }>(raw);
      expect(result.name).toBe('test');
      expect(result.value).toBe(42);
    });

    it('should handle unescaped double quotes inside string values', () => {
      const raw = '{"summary": "The CEO said "growth is strong" in Q3", "score": 85}';
      const result = parseJsonResponse<{ summary: string; score: number }>(raw);
      expect(result.score).toBe(85);
      expect(result.summary).toContain('growth is strong');
    });

    it('should handle trailing commas in arrays', () => {
      const raw = '{"items": ["a", "b", "c", ], "count": 3}';
      const result = parseJsonResponse<{ items: string[]; count: number }>(raw);
      expect(result.items).toEqual(['a', 'b', 'c']);
    });

    it('should handle NaN and Infinity in values', () => {
      const raw = '{"value": NaN, "max": Infinity, "min": -Infinity}';
      const result = parseJsonResponse<any>(raw);
      expect(result.value).toBeNull();
      expect(result.max).toBeNull();
    });
  });
});
