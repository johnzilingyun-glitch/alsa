import os
from typing import Dict, Any, Optional
from ..db.models import PromptVersion, PromptRun
from ..db.sqlite import session_factory
from sqlmodel import select, Session

class PromptRuntime:
    # ... (原有代码)

    def record_run(self, run_data: Dict[str, Any]):
        """
        持久化 Prompt 运行指标。
        """
        with session_factory() as session:
            run = PromptRun(**run_data)
            session.add(run)
            session.commit()
            print(f"Prompt run recorded: {run.prompt_run_id}")
    def __init__(self, templates_dir: str):
        self.templates_dir = templates_dir
        self._cache = {}

    def _load_template(self, template_path: str) -> str:
        if template_path not in self._cache:
            with open(os.path.join(self.templates_dir, template_path), 'r', encoding='utf-8') as f:
                self._cache[template_path] = f.read()
        return self._cache[template_path]

    def get_prompt(self, prompt_name: str, version: str) -> Dict[str, Any]:
        with session_factory() as session:
            statement = select(PromptVersion).where(
                PromptVersion.prompt_name == prompt_name,
                PromptVersion.version == version
            )
            pv = session.exec(statement).first()
            if not pv:
                raise ValueError(f"Prompt {prompt_name} v{version} not found")

            return {
                "template": self._load_template(pv.template_path),
                "schema": pv.schema_name,
                "version": pv.version
            }

# Singleton instance
prompt_runtime = PromptRuntime(os.path.join(os.path.dirname(__file__), "templates"))
