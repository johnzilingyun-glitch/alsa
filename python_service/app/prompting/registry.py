import os
from typing import Dict, Optional

class PromptRegistry:
    def __init__(self, templates_dir: str):
        self.templates_dir = templates_dir
        self._cache: Dict[str, str] = {}

    def get_template(self, role: str, language: str = "zh-CN") -> str:
        """
        Retrieve a prompt template for a specific role and language.
        """
        lang_suffix = "zh" if language == "zh-CN" else "en"
        role_key = role.replace(" ", "_").lower()
        filename = f"{role_key}_{lang_suffix}.txt"
        path = os.path.join(self.templates_dir, filename)

        if path in self._cache:
            return self._cache[path]

        if not os.path.exists(path):
            # Fallback to English if ZH not found
            if lang_suffix == "zh":
                return self.get_template(role, language="en")
            raise FileNotFoundError(f"Template not found for role {role} and language {language}")

        with open(path, "r", encoding="utf-8") as f:
            template = f.read()
            self._cache[path] = template
            return template

# Initialize registry
current_dir = os.path.dirname(__file__)
templates_path = os.path.join(current_dir, "templates")
prompt_registry = PromptRegistry(templates_path)
