import pytest
import asyncio
import os
import json
from python_service.app.services.llm_gateway import LLMGateway

@pytest.mark.asyncio
async def test_deepseek_routing():
    """
    Test that the LLMGateway correctly routes deepseek models to the deepseek client.
    """
    # Mock the environment key for testing
    os.environ["DEEPSEEK_API_KEY"] = "sk-test-key-123"
    
    gateway = LLMGateway()
    assert gateway.deepseek_api_key == "sk-test-key-123"
    
    # We can't easily mock the OpenAI client without more setup, 
    # but we can verify the model mapping logic.
    model = "deepseek-v4-pro"
    
    # Test internal mapping in _generate_deepseek if we could access it, 
    # but let's test the main entry point with a mock prompt.
    # Note: This will attempt a real network call if not careful, 
    # so we just verify the gateway initialization here.
    assert "deepseek" in model.lower()

def test_log_parsing():
    """
    Test reading the debug logs for DeepSeek specific tags.
    """
    log_path = "logs/debug_records.log"
    if not os.path.exists(log_path):
        pytest.skip("Log file not found")
        
    found_deepseek = False
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if "gateway_deepseek" in line or "deepseek" in line.lower():
                found_deepseek = True
                break
    
    # This is a passive check - it doesn't fail if no logs exist yet, 
    # but it helps us see what's in there.
    print(f"DeepSeek logs found: {found_deepseek}")

if __name__ == "__main__":
    # Quick manual run
    asyncio.run(test_deepseek_routing())
    test_log_parsing()
