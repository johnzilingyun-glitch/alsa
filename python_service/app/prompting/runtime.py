import os
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader

class PromptRuntimeService:
    def __init__(self, templates_dir: str):
        self.env = Environment(loader=FileSystemLoader(templates_dir))

    def assemble_prompt(self, template_name: str, context: Dict[str, Any]) -> str:
        template = self.env.get_template(template_name)
        return template.render(**context)

    def get_prompt(self, name: str, version: str = "v1", language: str = "zh-CN") -> Dict[str, Any]:
        """
        Retrieves a prompt template from the filesystem.
        Respects the language parameter: loads _zh for zh-CN, _en for others.
        """
        # Always force 'zh' (Chinese) prompts as requested
        lang_suffix = "zh"
        fallback_suffix = "en"
        
        # Try preferred language first, then fallback
        # .md files have priority over .txt (new structured format)
        possible_files = [
            f"{name}_{lang_suffix}.md",
            f"{name}_{lang_suffix}.txt",
            f"{name}_{fallback_suffix}.md",
            f"{name}_{fallback_suffix}.txt",
            f"{name}.md",
            f"{name}.txt",
            f"{name}.jinja2"
        ]
        
        for file_name in possible_files:
            file_path = os.path.join(self.env.loader.searchpath[0], file_name)
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    return {
                        "name": name,
                        "version": version,
                        "template": f.read()
                    }
        
        raise FileNotFoundError(f"Prompt template {name} not found in {self.env.loader.searchpath[0]}")

    def record_run(self, metrics: Dict[str, Any]):
        """
        Placeholder for recording prompt execution metrics.
        """
        # In a real system, this would write to a DB or telemetry service
        print(f"[PromptRuntime] Metrics recorded: {metrics.get('model')} | Latency: {metrics.get('latency_ms')}ms")

# Singleton instance
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_path = os.path.join(current_dir, "templates")
prompt_runtime = PromptRuntimeService(templates_path)
