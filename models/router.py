"""LiteLLM 模型路由层

任务 → 模型映射:
  identify_source     → deepseek-chat (便宜, 中文好)
  playbook_fallback   → deepseek-chat
  doc_agent           → deepseek-chat
  field_agent         → deepseek-chat (× N threads)
  fuse_simple         → deepseek-chat
  arbitrate           → claude-sonnet-4 (强推理)
  format_draft        → deepseek-chat
"""

import os
from litellm import completion
from litellm.exceptions import APIError, RateLimitError, Timeout

# ────────────────────────────────────────────────────────────
# 模型配置
# ────────────────────────────────────────────────────────────

MODEL_CONFIG = {
    "identify_source": {
        "model": os.getenv("DEFAULT_MODEL", "openai/deepseek-v4-flash"),
        "fallbacks": ["openai/glm-4"],
        "max_tokens": 100,
        "temperature": 0.1,
    },
    "playbook_fallback": {
        "model": os.getenv("DEFAULT_MODEL", "openai/deepseek-v4-flash"),
        "fallbacks": ["openai/glm-4"],
        "max_tokens": 200,
        "temperature": 0.1,
    },
    "doc_agent": {
        "model": os.getenv("DEFAULT_MODEL", "openai/deepseek-v4-flash"),
        "fallbacks": ["openai/glm-4"],
        "max_tokens": 300,
        "temperature": 0.2,
    },
    "field_agent": {
        "model": os.getenv("DEFAULT_MODEL", "openai/deepseek-v4-flash"),
        "fallbacks": ["openai/glm-4"],
        "max_tokens": 200,
        "temperature": 0.2,
    },
    "fuse_simple": {
        "model": os.getenv("DEFAULT_MODEL", "openai/deepseek-v4-flash"),
        "fallbacks": ["openai/glm-4"],
        "max_tokens": 300,
        "temperature": 0.2,
    },
    "arbitrate": {
        "model": os.getenv("STRONG_MODEL", "openai/claude-sonnet-4-20250514"),
        "fallbacks": ["openai/glm-4-plus"],
        "max_tokens": 500,
        "temperature": 0.3,
    },
    "format_draft": {
        "model": os.getenv("DEFAULT_MODEL", "openai/deepseek-v4-flash"),
        "fallbacks": ["openai/glm-4"],
        "max_tokens": 300,
        "temperature": 0.3,
    },
}

# 纯确定性兜底（所有模型不可用时）
RULE_BASED_FALLBACK = "rule_based"


# ────────────────────────────────────────────────────────────
# 路由函数
# ────────────────────────────────────────────────────────────

async def route(task: str, messages: list[dict], **kwargs) -> dict:
    """按任务类型选择模型并调用。

    Args:
        task: 任务类型 (identify_source / playbook_fallback / ...)
        messages: LLM 消息列表
        **kwargs: 覆盖配置参数

    Returns:
        {"content": str, "model": str, "tokens": int, "cost": float}

    Raises:
        AllModelsExhausted: 所有模型（含 fallback）都不可用
    """
    config = MODEL_CONFIG.get(task, MODEL_CONFIG["identify_source"])
    model = kwargs.get("model", config["model"])
    fallbacks = kwargs.get("fallbacks", config.get("fallbacks", []))
    max_tokens = kwargs.get("max_tokens", config["max_tokens"])
    temperature = kwargs.get("temperature", config["temperature"])

    last_error = None

    # 尝试主力模型
    try:
        response = await _call(model, messages, max_tokens, temperature)
        return response
    except (APIError, RateLimitError, Timeout) as e:
        last_error = e

    # 尝试 fallback 模型
    for fb_model in fallbacks:
        try:
            response = await _call(fb_model, messages, max_tokens, temperature)
            return response
        except (APIError, RateLimitError, Timeout) as e:
            last_error = e

    # 全部不可用
    raise AllModelsExhausted(f"All models failed for task '{task}': {last_error}")


async def _call(model: str, messages: list[dict], max_tokens: int, temperature: float) -> dict:
    """调用 LiteLLM，返回结构化结果"""
    kwargs = {}
    if _one_api:
        kwargs["api_key"] = _one_api.get("api_key")
        kwargs["api_base"] = _one_api.get("base_url") + "/v1"

    response = completion(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        **kwargs,
    )
    return {
        "content": response.choices[0].message.content,
        "model": model,
        "tokens": response.usage.total_tokens if response.usage else 0,
        "cost": _estimate_cost(model, response.usage),
    }


def _estimate_cost(model: str, usage) -> float:
    """估算成本（近似值）"""
    if not usage:
        return 0.0
    prices = {
        "deepseek": (0.14, 0.28),      # input/output per 1M tokens, USD
        "claude": (3.0, 15.0),
        "glm-4": (1.0, 1.0),
    }
    for prefix, (in_price, out_price) in prices.items():
        if prefix in model:
            return (usage.prompt_tokens * in_price + usage.completion_tokens * out_price) / 1_000_000
    return 0.0


class AllModelsExhausted(Exception):
    """所有模型（含 fallback）都不可用"""
    pass


# ────────────────────────────────────────────────────────────
# One-API 代理配置（从 ai/config.json 读取）
# ────────────────────────────────────────────────────────────

import json
from pathlib import Path

def _load_one_api_config() -> dict | None:
    config_path = Path(__file__).resolve().parent.parent / "ai" / "config.json"
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return None

_one_api = _load_one_api_config()
if _one_api:
    import os
    os.environ.setdefault("OPENAI_API_KEY", _one_api.get("api_key", ""))
    os.environ.setdefault("OPENAI_API_BASE", _one_api.get("base_url", "") + "/v1")
