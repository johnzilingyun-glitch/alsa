from jinja2 import Template

with open("app/prompting/templates/chief_strategist_zh.txt", "r") as f:
    text = f.read()

try:
    t = Template(text)
    print("Jinja2 Parsed Successfully")
except Exception as e:
    print(f"Jinja2 Error: {e}")
