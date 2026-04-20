import dotenv from "dotenv";

// Mock localStorage for Node.js
if (typeof localStorage === 'undefined') {
  (global as any).localStorage = {
    getItem: () => null,
    setItem: () => null,
    removeItem: () => null,
  };
}

dotenv.config();

// Mock import.meta.env for Node.js
if (typeof (import.meta as any).env === 'undefined') {
  (import.meta as any).env = {
    VITE_GEMINI_API_KEY: process.env.GEMINI_API_KEY || ''
  };
}

async function testSearchPipeline() {
  console.log("🚀 Starting Search Pipeline Validation...");
  
  // Dynamic import after mocking to avoid top-level ReferenceError in stores
  const { createAI, generateAndParseJsonWithRetry, DUCKDUCKGO_TOOLS } = await import("../src/services/geminiService.js" as any);
  
  const ai = createAI();
  const testSymbol = "NVDA";
  
  const prompt = [
    {
      role: "user",
      parts: [{
        text: `You are a Deep Research Specialist. Use the duckduckgo_search tool to find the latest stock price and 24h news for ${testSymbol}. 
        Then return a JSON object with: { "price": string, "top_news": string[], "analysis": string }`
      }]
    }
  ];

  try {
    console.log("📡 Sending request to Gemini (Flash model + DDGS)...");
    const result = await generateAndParseJsonWithRetry(ai, {
      model: "gemini-3.1-flash-lite-preview",
      contents: prompt,
    }, {
      tools: DUCKDUCKGO_TOOLS,
      role: 'Deep Research Specialist',
      responseMimeType: "application/json"
    });

    console.log("✅ Pipeline Success!");
    console.log("📊 Result:", JSON.stringify(result, null, 2));
  } catch (err) {
    console.error("❌ Pipeline Failed:", err);
  }
}

testSearchPipeline();
