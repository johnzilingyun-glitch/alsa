import axios from 'axios';
import dotenv from 'dotenv';

dotenv.config();

const SEARXNG_URL = process.env.SEARXNG_URL || 'http://localhost:8080';
const TEST_QUERIES = [
  'Tencent stock analysis 2026',
  '英伟达 AI 芯片 财报',
  'S&P 500 historical volatility',
  'Bitcoin price trend next 6 months'
];

interface SearXNGResult {
  title: string;
  url: string;
  content: string;
  publishedDate?: string;
  engines?: string[];
}

interface SearXNGResponse {
  results: SearXNGResult[];
  infoboxes?: any[];
  suggestions?: string[];
}

async function runTest() {
  console.log('🚀 Starting SearXNG Stability & Accuracy Test');
  console.log(`📡 Instance URL: ${SEARXNG_URL}`);
  console.log('------------------------------------------');

  let totalSuccess = 0;
  let totalLatency = 0;
  const latencies: number[] = [];

  // 1. Stability Test (10 sequential requests)
  console.log('\n[1/3] Performance & Stability Test (10 Requests)...');
  for (let i = 1; i <= 10; i++) {
    const startTime = Date.now();
    try {
      const response = await axios.get(`${SEARXNG_URL}/search`, {
        params: { q: 'test', format: 'json' },
        timeout: 10000
      });
      if (response.status === 200) {
        const latency = Date.now() - startTime;
        latencies.push(latency);
        totalLatency += latency;
        totalSuccess++;
        console.log(`  Iter ${i}: SUCCESS (${latency}ms)`);
      } else {
        console.log(`  Iter ${i}: FAILED (HTTP ${response.status})`);
      }
    } catch (err: any) {
      console.log(`  Iter ${i}: ERROR (${err.message})`);
    }
  }

  const successRate = (totalSuccess / 10) * 100;
  const avgLatency = totalSuccess > 0 ? (totalLatency / totalSuccess).toFixed(2) : 'N/A';

  console.log(`\n📊 Results:`);
  console.log(`  - Success Rate: ${successRate}%`);
  console.log(`  - Avg Latency: ${avgLatency}ms`);
  console.log(`  - Min/Max Latency: ${latencies.length > 0 ? Math.min(...latencies) : 0}ms / ${latencies.length > 0 ? Math.max(...latencies) : 0}ms`);

  if (successRate < 80) {
    console.warn('⚠️ WARNING: Success rate is below 80%. Stability may be an issue.');
  }

  // 2. Schema Validation
  console.log('\n[2/3] Schema Validation...');
  try {
    const res = await axios.get(`${SEARXNG_URL}/search`, {
      params: { q: 'financial news', format: 'json' },
      timeout: 10000
    });
    const data = res.data as SearXNGResponse;
    const hasResults = data.results && Array.isArray(data.results);
    const firstResult = data.results?.[0];
    const hasFields = firstResult && firstResult.title && (firstResult.url || firstResult.link) && (firstResult.content || firstResult.snippet);

    if (hasResults && hasFields) {
      console.log('  ✅ JSON Schema verified (results, title, url/link, content/snippet present)');
    } else {
      console.log('  ❌ JSON Schema invalid or missing fields');
      console.log('  Sample Data:', JSON.stringify(firstResult, null, 2).slice(0, 500));
    }
  } catch (err: any) {
    console.log(`  ❌ Schema validation failed: ${err.message}`);
  }

  // 3. Accuracy & Relevance Test
  console.log('\n[3/3] Accuracy & Relevance Test...');
  for (const query of TEST_QUERIES) {
    try {
      const startTime = Date.now();
      const res = await axios.get(`${SEARXNG_URL}/search`, {
        params: { q: query, format: 'json' },
        timeout: 10000
      });
      const data = res.data as SearXNGResponse;
      const latency = Date.now() - startTime;

      const count = data.results?.length || 0;
      const relevanceKeywords = query.split(' ').filter(k => k.length > 2);
      let matchCount = 0;

      data.results?.slice(0, 5).forEach(r => {
        const text = ((r.title || '') + ' ' + (r.content || r.snippet || '')).toLowerCase();
        relevanceKeywords.forEach(k => {
          if (text.includes(k.toLowerCase())) matchCount++;
        });
      });

      const relevanceScore = relevanceKeywords.length > 0 ? (matchCount / (relevanceKeywords.length * 5)) * 100 : 0;

      console.log(`  Query: "${query}"`);
      console.log(`    - Results: ${count}`);
      console.log(`    - Relevance Score: ${relevanceScore.toFixed(0)}%`);
      console.log(`    - Latency: ${latency}ms`);
    } catch (err: any) {
      console.log(`  Query: "${query}" - FAILED (${err.message})`);
    }
  }

  console.log('\n------------------------------------------');
  console.log('✅ SearXNG Test Suite Finished');
}

runTest();
