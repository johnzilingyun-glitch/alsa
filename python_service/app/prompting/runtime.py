import os
import logging
import glob
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader
from .version_registry import prompt_version_registry

logger = logging.getLogger(__name__)

class PromptRuntimeService:
    def __init__(self, templates_dir: str):
        self.env = Environment(loader=FileSystemLoader(templates_dir))
        self.templates_dir = templates_dir
        self.registry = prompt_version_registry
        
        # Auto-seed templates to the version registry
        try:
            self._seed_templates_to_registry()
        except Exception as e:
            logger.error(f"Failed to seed templates to prompt version registry: {e}")

    def _seed_templates_to_registry(self):
        pattern = os.path.join(self.templates_dir, "*")
        files = glob.glob(pattern)
        
        # Sort so that .txt is processed before .md, so .md will end up as the active version if both exist
        files.sort(key=lambda x: (1 if x.endswith('.md') else 0))
        
        for file_path in files:
            if not os.path.isfile(file_path):
                continue
            base = os.path.basename(file_path)
            # Remove extension
            name_key, ext = os.path.splitext(base)
            if ext not in ('.md', '.txt', '.jinja2'):
                continue
                
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    template_content = f.read()
                
                # Determine role_scope from name
                role_scope = name_key.replace("_zh", "").replace("_en", "").replace("_", " ").title()
                
                # Register
                version = self.registry.register(
                    name=name_key,
                    role_scope=role_scope,
                    template=template_content
                )
                # Activate it
                self.registry.activate(version.prompt_version_id)
                logger.info(f"Seeded prompt template {base} as version {version.prompt_version_id}")
            except Exception as e:
                logger.error(f"Error seeding template {base}: {e}")

    def assemble_prompt(self, template_name: str, context: Dict[str, Any]) -> str:
        template = self.env.get_template(template_name)
        return template.render(**context)

    def get_prompt(self, name: str, version: str = "v1", language: str = "zh-CN") -> Dict[str, Any]:
        """
        Retrieves a prompt template from the registry (or falls back to filesystem if not found).
        Respects the language parameter: loads _zh for zh-CN, _en for others.
        """
        # Always force 'zh' (Chinese) prompts as requested
        lang_suffix = "zh"
        fallback_suffix = "en"
        
        # 1. Try finding the active template in the registry first
        full_name = f"{name}_{lang_suffix}"
        active_version = self.registry.get_active(full_name)
        if not active_version:
            active_version = self.registry.get_active(name)
            
        if active_version:
            return {
                "name": name,
                "version": active_version.prompt_version_id,
                "template": active_version.template
            }
            
        # 2. Fallback to filesystem loading (and lazy-register)
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
            file_path = os.path.join(self.templates_dir, file_name)
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # Lazy-register in registry
                    name_key, _ = os.path.splitext(file_name)
                    role_scope = name_key.replace("_zh", "").replace("_en", "").replace("_", " ").title()
                    v = self.registry.register(name=name_key, role_scope=role_scope, template=content)
                    self.registry.activate(v.prompt_version_id)
                    
                    return {
                        "name": name,
                        "version": v.prompt_version_id,
                        "template": content
                    }
                except Exception as e:
                    logger.error(f"Failed to lazy-register {file_name}: {e}")
        
        raise FileNotFoundError(f"Prompt template {name} not found in {self.templates_dir}")

    def record_run(self, metrics: Dict[str, Any]):
        """
        Record prompt execution metrics directly to version registry.
        """
        logger.info(f"[PromptRuntime] Metrics recorded: {metrics.get('model')} | Latency: {metrics.get('latency_ms')}ms")
        try:
            self.registry.record_run(
                prompt_version_id=metrics.get("prompt_version_id", ""),
                model=metrics.get("model", ""),
                provider=metrics.get("provider", "unknown"),
                input_tokens=metrics.get("input_tokens", 0),
                output_tokens=metrics.get("output_tokens", 0),
                latency_ms=metrics.get("latency_ms", 0),
                tool_calls=metrics.get("tool_calls", 0),
                schema_validation_passed=metrics.get("schema_validation_passed", True)
            )
        except Exception as e:
            logger.error(f"Failed to record run metrics in registry: {e}")

# Singleton instance
current_dir = os.path.dirname(os.path.abspath(__file__))
templates_path = os.path.join(current_dir, "templates")
prompt_runtime = PromptRuntimeService(templates_path)
