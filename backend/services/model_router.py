"""Cost-aware model routing — the orchestrator that picks a model per workload.

Every LLM call site tags itself with a ``task`` (services/llm.py threads it
through ``complete``/``complete_json``). The router maps the task to a TIER
and, when the resolved provider has a lighter model configured for that tier,
swaps the model in the effective config. The provider itself never changes
here — WHO processes the content is a privacy decision (resolve_config,
fail-closed); this module only decides HOW MUCH model that provider spends.

Rules:
- ``generate``/``refine`` (long legal drafts) always stay on the HEAVY tier.
- High-volume, short workloads (critic review, evaluator gate, lessons
  extraction, tabular cells, intake parse) run on the LIGHT tier.
- A gestora that PINS an explicit ``llm_model`` in its model-config override
  is never re-routed (resolve_config marks the config as pinned).
- An empty light-model setting makes routing a NO-OP for that provider, so
  the zero-config local setup behaves exactly as before.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from config import get_settings

logger = logging.getLogger("lolailo.model_router")

HEAVY = "heavy"
LIGHT = "light"

# Task -> tier. Unknown/None tasks default to HEAVY (never degrade quality of
# an untagged call by accident).
TASK_TIERS: dict[str, str] = {
    "generate": HEAVY,
    "refine": HEAVY,
    "parse": LIGHT,
    "parse_escalated": HEAVY,
    "critic": LIGHT,
    "critic_gate": LIGHT,
    "lessons": LIGHT,
    "tabular": LIGHT,
}


def tier_for(task: Optional[str]) -> str:
    """The routing tier for a task tag (HEAVY when unknown or untagged)."""
    if not task:
        return HEAVY
    return TASK_TIERS.get(task, HEAVY)


def light_model_for(provider: str) -> str:
    """The configured light-tier model for ``provider`` ("" = no routing)."""
    settings = get_settings()
    return {
        "ollama": settings.ollama_light_model,
        "anthropic": settings.anthropic_light_model,
        "mistral": settings.mistral_light_model,
    }.get(provider, "")


def apply(config: Any, task: Optional[str]) -> Any:
    """Mutate ``config`` (an EffectiveLLMConfig) for the task's tier.

    No-op when routing is disabled, the task is heavy-tier, the gestora pinned
    an explicit model, or the provider has no light model configured.
    """
    settings = get_settings()
    if not settings.model_routing_enabled or tier_for(task) != LIGHT:
        return config
    if getattr(config, "model_pinned", False):
        return config
    light = light_model_for(config.llm_provider)
    if not light:
        return config
    if config.llm_provider == "ollama":
        config.ollama_llm_model = light
    elif config.llm_provider == "anthropic":
        config.claude_model = light
    elif config.llm_provider == "mistral":
        config.mistral_model = light
    logger.debug("Routed task %s to %s:%s (light tier)", task, config.llm_provider, light)
    return config


def model_of(config: Any) -> str:
    """The model name the config would use with its current provider."""
    return {
        "ollama": config.ollama_llm_model,
        "anthropic": config.claude_model,
        "mistral": config.mistral_model,
    }.get(config.llm_provider, "?")
