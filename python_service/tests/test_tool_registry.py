import pytest
from app.services.tools.registry import ToolRegistry

@pytest.fixture
def clean_registry():
    """Provides a fresh ToolRegistry for each test."""
    return ToolRegistry()

def test_tool_registration(clean_registry):
    # Register an async tool
    schema = {"name": "test_search", "description": "A test search tool"}
    
    @clean_registry.register(schema)
    async def mock_search(params):
        return f"Searched for {params.get('query')}"
        
    assert "test_search" in clean_registry.get_registered_names()
    assert len(clean_registry.get_all_schemas()) == 1
    assert clean_registry.get_all_schemas()[0] == schema
    assert not clean_registry.is_computation_tool("test_search")

def test_computation_tool_registration(clean_registry):
    # Register a computation tool (sync)
    schema = {"name": "test_calc", "description": "A test calc tool"}
    
    @clean_registry.register(schema, is_computation=True)
    def mock_calc(params):
        return "Calculated"
        
    assert "test_calc" in clean_registry.get_registered_names()
    assert clean_registry.is_computation_tool("test_calc")

@pytest.mark.asyncio
async def test_tool_execution(clean_registry):
    schema = {"name": "test_search", "description": "Search tool"}
    
    @clean_registry.register(schema)
    async def mock_search(params):
        return f"Searched for {params.get('query')}"
        
    func = clean_registry.get_tool("test_search")
    assert func is not None
    
    result = await func({"query": "AI"})
    assert result == "Searched for AI"

def test_get_nonexistent_tool(clean_registry):
    assert clean_registry.get_tool("not_exist") is None
    assert "not_exist" not in clean_registry.get_registered_names()
