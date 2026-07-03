"""Post-processing model presets and capability helpers."""

DEFAULT_MODEL = "gpt-5.4-mini"

POST_PROCESSING_MODEL_PRESETS = (
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5-mini",
    "gpt-5-nano",
)

REASONING_EFFORT_VALUES = ("none", "low", "medium", "high", "xhigh")
DEFAULT_REASONING_EFFORT = "medium"

_REASONING_EFFORT_MODELS = {
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
}


def normalize_model_id(value: str | None) -> str:
    model = (value or "").strip()
    return model or DEFAULT_MODEL


def is_known_post_processing_model(model: str | None) -> bool:
    return normalize_model_id(model) in POST_PROCESSING_MODEL_PRESETS


def supports_reasoning_effort(model: str | None) -> bool:
    return normalize_model_id(model) in _REASONING_EFFORT_MODELS


def normalize_reasoning_effort(value: str | None) -> str:
    effort = (value or "").strip().lower()
    if effort in REASONING_EFFORT_VALUES:
        return effort
    return DEFAULT_REASONING_EFFORT
