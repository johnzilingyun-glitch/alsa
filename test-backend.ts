
import axios from 'axios';

async function testRealtimeApi() {
  console.log('Testing /api/stock/realtime...');
  try {
    const response = await axios.get('http://localhost:3000/api/stock/realtime?symbol=600519&market=A-Share');
    console.log('Realtime API Response:', JSON.stringify(response.data, null, 2));
  } catch (error: any) {
    console.error('Realtime API Error:', error.message);
    if (error.response) {
      console.error('Status:', error.response.status);
      console.error('Data:', error.response.data);
    }
  }
}

async function testMarketOverviewApi() {
  console.log('\nTesting /api/market/overview...');
  try {
    const response = await axios.get('http://localhost:3000/api/market/overview');
    console.log('Market Overview API Response:', JSON.stringify(response.data, null, 2));
  } catch (error: any) {
    console.error('Market Overview API Error:', error.message);
  }
}

async function testAdminApis() {
  console.log('\nTesting Admin APIs...');
  try {
    const history = await axios.get('http://localhost:3000/api/history/context');
    console.log('History Context API Success, items:', history.data.length);
    
    const save = await axios.post('http://localhost:3000/api/history/save', {
      type: 'test',
      data: { message: 'test' }
    });
    console.log('Save Analysis API Success:', save.data.success);
    
    const logs = await axios.get('http://localhost:3000/api/logs/optimization');
    console.log('Optimization Logs API Success, items:', logs.data.length);
  } catch (error: any) {
    console.error('Admin API Error:', error.message);
  }
}

async function testBatchRealtimeApi() {
  console.log('\nTesting /api/stock/realtime with multiple symbols...');
  try {
    const symbols = '000001.SS,399001.SZ,399006.SZ,000300.SS,^HSI';
    const response = await axios.get(`http://localhost:3000/api/stock/realtime?symbols=${symbols}`);
    console.log('Batch Realtime API Success, items:', response.data.length);
  } catch (error: any) {
    console.error('Batch Realtime API Error:', error.message);
  }
}

async function runTests() {
  await testRealtimeApi();
  await testBatchRealtimeApi();
  await testAdminApis();
}

runTests();
