from buzz.plugins.transcript_post_processing import models
from buzz.transcriber.openai_stt_models import OPENAI_STT_MODEL_PRESETS


def test_post_processing_model_presets_are_separate_from_stt_presets():
    assert models.DEFAULT_MODEL == "gpt-5.4-mini"
    assert models.POST_PROCESSING_MODEL_PRESETS == (
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        "gpt-5-mini",
        "gpt-5-nano",
    )

    assert not set(models.POST_PROCESSING_MODEL_PRESETS).intersection(
        OPENAI_STT_MODEL_PRESETS
    )


def test_normalize_model_id_preserves_custom_value():
    assert models.normalize_model_id("") == models.DEFAULT_MODEL
    assert models.normalize_model_id(" custom-model ") == "custom-model"


def test_known_post_processing_model_detection():
    assert models.is_known_post_processing_model("gpt-5.5") is True
    assert models.is_known_post_processing_model("custom-model") is False


def test_reasoning_effort_capabilities():
    assert models.supports_reasoning_effort("gpt-5.5") is True
    assert models.supports_reasoning_effort("gpt-5.4-mini") is True
    assert models.supports_reasoning_effort("gpt-5-mini") is False
    assert models.supports_reasoning_effort("custom-model") is False


def test_normalize_reasoning_effort():
    assert models.normalize_reasoning_effort("xhigh") == "xhigh"
    assert models.normalize_reasoning_effort(" HIGH ") == "high"
    assert models.normalize_reasoning_effort("unsupported") == "medium"
