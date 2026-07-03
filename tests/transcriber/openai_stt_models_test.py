import pytest

from buzz.transcriber.openai_stt_models import (
    OPENAI_STT_DEFAULT_MODEL,
    OPENAI_STT_DIARIZATION_MODEL,
    OPENAI_STT_LEGACY_MODEL,
    OPENAI_STT_MINI_MODEL,
    OPENAI_STT_MINI_SNAPSHOT_MODEL,
    is_known_openai_gpt_stt_model,
    is_openai_stt_diarization_model,
    openai_stt_supports_prompt,
    openai_stt_supports_timestamp_granularities,
    openai_stt_transcription_response_format,
    openai_stt_translation_model,
    openai_stt_uses_chunking_strategy,
)


@pytest.mark.parametrize(
    "model_id",
    [
        OPENAI_STT_DEFAULT_MODEL,
        OPENAI_STT_MINI_MODEL,
        OPENAI_STT_MINI_SNAPSHOT_MODEL,
        OPENAI_STT_DIARIZATION_MODEL,
    ],
)
def test_known_openai_gpt_stt_models_use_json_without_timestamps(model_id):
    assert is_known_openai_gpt_stt_model(model_id) is True
    assert openai_stt_transcription_response_format(model_id) == "json"
    assert openai_stt_supports_timestamp_granularities(model_id) is False


def test_diarization_model_does_not_support_prompt_and_uses_chunking():
    assert is_openai_stt_diarization_model(OPENAI_STT_DIARIZATION_MODEL) is True
    assert openai_stt_supports_prompt(OPENAI_STT_DIARIZATION_MODEL) is False
    assert openai_stt_uses_chunking_strategy(OPENAI_STT_DIARIZATION_MODEL) is True


def test_non_diarization_models_support_prompt():
    assert openai_stt_supports_prompt(OPENAI_STT_DEFAULT_MODEL) is True
    assert openai_stt_supports_prompt(OPENAI_STT_LEGACY_MODEL) is True
    assert openai_stt_supports_prompt("custom-transcribe") is True


def test_legacy_and_custom_models_preserve_structured_response_behavior():
    assert openai_stt_transcription_response_format(OPENAI_STT_LEGACY_MODEL) == "verbose_json"
    assert openai_stt_supports_timestamp_granularities(OPENAI_STT_LEGACY_MODEL) is True

    assert openai_stt_transcription_response_format("custom-transcribe") == "verbose_json"
    assert openai_stt_supports_timestamp_granularities("custom-transcribe") is True


def test_translation_model_falls_back_only_for_known_gpt_models():
    assert openai_stt_translation_model(OPENAI_STT_DEFAULT_MODEL) == OPENAI_STT_LEGACY_MODEL
    assert openai_stt_translation_model(OPENAI_STT_DIARIZATION_MODEL) == OPENAI_STT_LEGACY_MODEL
    assert openai_stt_translation_model(OPENAI_STT_LEGACY_MODEL) == OPENAI_STT_LEGACY_MODEL
    assert openai_stt_translation_model("custom-transcribe") == "custom-transcribe"
