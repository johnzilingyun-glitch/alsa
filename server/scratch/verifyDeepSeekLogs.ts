import { gatewayGenerate } from '../llmGateway.js';
import { logDebug } from '../stockLogger.js';
import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(process.cwd(), '.env') });

async function runTest() {
  const model = 'deepseek-v4-pro';
  const apiKey = process.env.DEEPSEEK_API_KEY;

  if (!apiKey) {
    console.error('❌ DEEPSEEK_API_KEY not found in .env');
    process.exit(1);
  }

  console.log(`🚀 Starting DeepSeek log verification test for model: ${model}...`);
  
  const config = { deepseekApiKey: apiKey };
  const prompt = 'Return only the word "OK" if you can read this.';

  try {
    const result = await gatewayGenerate(prompt, model, (event, data) => {
        logDebug(event, data);
    }, config as any);

    console.log('✅ Gateway Result:', result.text);
    
    // Now check the log file
    const logPath = path.resolve(process.cwd(), 'logs', 'debug_records.log');
    if (fs.existsSync(logPath)) {
        const logs = fs.readFileSync(logPath, 'utf8');
        if (logs.includes('GATEWAY_DEEPSEEK_OK')) {
            console.log('🎉 Verification Successful: "GATEWAY_DEEPSEEK_OK" found in logs!');
        } else {
            console.warn('⚠️  "GATEWAY_DEEPSEEK_OK" NOT found in logs despite success.');
        }
    } else {
        console.error('❌ Log file not found at:', logPath);
    }

  } catch (err) {
    console.error('❌ Test failed:', err);
  }
}

runTest();
