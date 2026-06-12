import { getMarketOverview } from './src/services/marketService.js';
import { useConfigStore } from './src/stores/useConfigStore.js';
useConfigStore.getState().setApiKey(process.env.GEMINI_API_KEY);
getMarketOverview(undefined, 'US-Share', true).then(res => console.log('Summary:', res.marketSummary?.substring(0, 50))).catch(e => console.error(e));
