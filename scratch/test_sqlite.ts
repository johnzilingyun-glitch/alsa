import { createAnalysisRepository } from './server/repositories/analysisRepository.js';

async function testRepo() {
  const repo = createAnalysisRepository();
  const analysisId = 'test_' + Date.now();
  
  console.log('Saving analysis...');
  await repo.save({
    analysisId,
    kind: 'stock',
    symbol: '600519',
    market: 'A-Share',
    status: 'completed',
    promptVersion: 'v1',
    model: 'gemini-2.0-flash-exp',
    outputPayload: { summary: 'test' }
  });
  
  console.log('Fetching analysis...');
  const result = await repo.getById(analysisId);
  console.log('Result:', result);
  
  console.log('Fetching latest for 600519...');
  const latest = await repo.getLatestStockAnalysis('600519', 'A-Share');
  console.log('Latest:', latest);
  
  process.exit(0);
}

testRepo().catch(err => {
  console.error(err);
  process.exit(1);
});
