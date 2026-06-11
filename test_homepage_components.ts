import fs from 'fs';

async function fetchWithTimeout(url: string, options: any, timeout = 10000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return response;
  } catch (err) {
    clearTimeout(id);
    throw err;
  }
}

async function testLLMGenerate() {
  console.log('\n--- 测试 1: 基础 LLM 生成 (MarketOverview 依赖) ---');
  try {
    const res = await fetchWithTimeout('http://127.0.0.1:3000/api/llm/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'deepseek-chat',
        params: { contents: '你好，请用一句话描述今天的天气。' },
        config: { deepseekApiKey: 'sk-invalid-test-key' } // Simulate invalid key
      })
    });
    const data = await res.json();
    console.log('LLM API 返回结果:', data);
    if (!data.success) {
      console.log('✅ 正确: API 返回了错误状态，而不是悄悄崩溃或隐藏错误。');
      console.log('错误信息为:', data.error);
    }
  } catch (err: any) {
    console.error('❌ 请求异常:', err.message);
  }
}

async function testSectorScan() {
  console.log('\n--- 测试 2: 板块扫描 (SectorScanner) ---');
  try {
    const res = await fetchWithTimeout('http://127.0.0.1:3000/api/sector/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'deepseek-chat',
        force: true,
        deepseek_api_key: 'sk-invalid-test-key'
      })
    });
    const data = await res.json();
    console.log('Sector Scan 返回结果:', data);
    if (data.success && data.data?.job_id) {
      console.log(`✅ 正确: 成功创建扫描任务 ${data.data.job_id}`);
      
      // Cancel it immediately to save resources
      await fetchWithTimeout(`http://127.0.0.1:3000/api/sector/run/${data.data.job_id}/cancel`, { method: 'POST' });
      console.log('已取消该测试任务');
    } else {
      console.log('扫描失败原因:', data.error);
    }
  } catch (err: any) {
    console.error('❌ 请求异常:', err.message);
  }
}

async function testSerenityAlpha() {
  console.log('\n--- 测试 3: 专属研判 (SerenityAlphaAnalyst) ---');
  try {
    const res = await fetchWithTimeout('http://127.0.0.1:3000/api/sector/serenity-analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sector_name: '低空经济',
        model: 'deepseek-chat',
        force: true,
        deepseek_api_key: 'sk-invalid-test-key'
      })
    });
    const data = await res.json();
    console.log('Serenity Alpha 返回结果:', data);
    if (data.success && data.data?.job_id) {
      console.log(`✅ 正确: 成功创建研判任务 ${data.data.job_id}`);
      
      // Cancel it immediately
      await fetchWithTimeout(`http://127.0.0.1:3000/api/sector/analyze/${data.data.job_id}/cancel`, { method: 'POST' });
      console.log('已取消该测试任务');
    } else {
      console.log('研判失败原因:', data.error);
    }
  } catch (err: any) {
    console.error('❌ 请求异常:', err.message);
  }
}

async function runTests() {
  console.log('开始审核主页依赖的后端接口及错误抛出机制...');
  await testLLMGenerate();
  await testSectorScan();
  await testSerenityAlpha();
  console.log('\n审核完成。');
}

runTests();
