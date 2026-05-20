"""
Tools & Skills Configuration Loader.

Reads tools_config.yaml and provides functions to check
whether a tool or skill is enabled at runtime.
Supports hot-reload: re-reads the file on each check so changes
take effect without restarting the service.
"""

import os
import yaml
from typing import Dict, Any, List

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "tools_config.yaml")
_cached_config: Dict[str, Any] = {}
_cached_mtime: float = 0.0


def _load_config() -> Dict[str, Any]:
    """Load config with file-modification-time caching for hot-reload."""
    global _cached_config, _cached_mtime
    try:
        mtime = os.path.getmtime(_CONFIG_PATH)
        if mtime != _cached_mtime:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                _cached_config = yaml.safe_load(f) or {}
            _cached_mtime = mtime
    except FileNotFoundError:
        _cached_config = {}
    return _cached_config


def is_tool_enabled(tool_name: str) -> bool:
    """Check if a tool is enabled in the config. Defaults to True if not found."""
    config = _load_config()
    tools = config.get("tools", {})
    tool_entry = tools.get(tool_name, {})
    if isinstance(tool_entry, dict):
        return tool_entry.get("enabled", True)
    return True


def is_skill_enabled(skill_name: str) -> bool:
    """Check if a skill is enabled in the config. Defaults to True if not found."""
    config = _load_config()
    skills = config.get("skills", {})
    skill_entry = skills.get(skill_name, {})
    if isinstance(skill_entry, dict):
        return skill_entry.get("enabled", True)
    return True


def get_enabled_tools() -> List[str]:
    """Return list of enabled tool names."""
    config = _load_config()
    tools = config.get("tools", {})
    return [name for name, entry in tools.items()
            if isinstance(entry, dict) and entry.get("enabled", True)]


def get_disabled_tools() -> List[str]:
    """Return list of disabled tool names."""
    config = _load_config()
    tools = config.get("tools", {})
    return [name for name, entry in tools.items()
            if isinstance(entry, dict) and not entry.get("enabled", True)]
