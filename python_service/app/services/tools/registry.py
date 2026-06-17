from typing import Dict, Any, Callable, Awaitable, List

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable[[Any], Awaitable[str]]] = {}
        self._schemas: List[Dict[str, Any]] = []
        self._computation_tools: set = set()

    def register(self, schema: Dict[str, Any], is_computation: bool = False):
        def decorator(func):
            name = schema["name"]
            self._tools[name] = func
            self._schemas.append(schema)
            if is_computation:
                self._computation_tools.add(name)
            return func
        return decorator

    def get_tool(self, name: str) -> Callable:
        return self._tools.get(name)

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        return self._schemas
        
    def is_computation_tool(self, name: str) -> bool:
        return name in self._computation_tools

    def get_registered_names(self) -> List[str]:
        return list(self._tools.keys())

tool_registry = ToolRegistry()
