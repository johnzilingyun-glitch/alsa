with open("app/services/llm_gateway.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Verify the lines
assert "async def generate_with_native_tools" in lines[599], f"Unexpected line 600: {lines[599]}"
assert "llm_gateway = LLMGateway()" in lines[1280], f"Unexpected line 1281: {lines[1280]}"

# Keep lines 0 to 598 (first 599 lines) and lines 1280 to end (1281th line to end)
new_lines = lines[:599] + lines[1280:]

with open("app/services/llm_gateway.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Successfully refactored app/services/llm_gateway.py")
