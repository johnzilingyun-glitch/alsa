"""Tools package — 工具注册表 + 各工具模块自动注册.

Phase 1 健壮性改进 (§4.6 Tool 治理):
  原生数据源 SDK (如 thsdk) 缺失时, 不应导致整个工具包不可用.
  改为容错导入: 每个工具子模块独立 try/except, 缺失依赖只跳过该组工具注册,
  其余工具 (web_search / iwencai 等) 仍可用. 生产环境依赖齐全时行为不变.
"""
import logging

from .registry import tool_registry

logger = logging.getLogger(__name__)

# 自动注册各工具模块. 容错: 单个模块因原生依赖缺失而导入失败时,
# 只跳过该模块的工具注册, 不影响其它工具与 tool_registry 本身.
_TOOL_MODULES = ["search", "iwencai", "ths_tools"]

for _mod in _TOOL_MODULES:
    try:
        __import__(f"{__name__}.{_mod}", fromlist=[_mod])
    except Exception as _e:  # noqa: BLE001
        logger.warning("[tools] 跳过工具模块 %s (依赖缺失或加载失败): %s", _mod, _e)
