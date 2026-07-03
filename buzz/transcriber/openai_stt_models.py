from dataclasses import dataclass


OPENAI_STT_DEFAULT_MODEL = "gpt-4o-transcribe"
OPENAI_STT_MINI_MODEL = "gpt-4o-mini-transcribe"
OPENAI_STT_MINI_SNAPSHOT_MODEL = "gpt-4o-mini-transcribe-2025-12-15"
OPENAI_STT_DIARIZATION_MODEL = "gpt-4o-transcribe-diarize"
OPENAI_STT_LEGACY_MODEL = "whisper-1"

OPENAI_STT_KNOWN_GPT_MODELS = (
    OPENAI_STT_DEFAULT_MODEL,
    OPENAI_STT_MINI_MODEL,
    OPENAI_STT_MINI_SNAPSHOT_MODEL,
    OPENAI_STT_DIARIZATION_MODEL,
)


@dataclass(frozen=True)
class OpenAISttModelPreset:
    model_id: str
    label: str
    tooltip: str = ""


OPENAI_STT_MODEL_PRESETS = (
    OpenAISttModelPreset(
        model_id=OPENAI_STT_DEFAULT_MODEL,
        label="gpt-4o-transcribe",
        tooltip="Default high quality OpenAI transcription model.",
    ),
    OpenAISttModelPreset(
        model_id=OPENAI_STT_MINI_MODEL,
        label="gpt-4o-mini-transcribe",
        tooltip="Faster and lower cost OpenAI transcription model.",
    ),
    OpenAISttModelPreset(
        model_id=OPENAI_STT_DIARIZATION_MODEL,
        label="gpt-4o-transcribe-diarize",
        tooltip="OpenAI transcription model with diarization response.",
    ),
    OpenAISttModelPreset(
        model_id=OPENAI_STT_LEGACY_MODEL,
        label="whisper-1 (legacy/fallback)",
        tooltip="Legacy OpenAI Whisper API fallback.",
    ),
)


def openai_stt_model_id_from_display_text(value: object) -> str:
    if value is None:
        return OPENAI_STT_DEFAULT_MODEL

    text = str(value).strip()
    if not text:
        return OPENAI_STT_DEFAULT_MODEL

    for preset in OPENAI_STT_MODEL_PRESETS:
        if text in (preset.model_id, preset.label):
            return preset.model_id

    return text


def openai_stt_model_display_text(model_id: str) -> str:
    normalized_model_id = openai_stt_model_id_from_display_text(model_id)
    for preset in OPENAI_STT_MODEL_PRESETS:
        if preset.model_id == normalized_model_id:
            return preset.label

    return normalized_model_id


def is_known_openai_gpt_stt_model(model_id: str) -> bool:
    return openai_stt_model_id_from_display_text(model_id) in OPENAI_STT_KNOWN_GPT_MODELS


def is_openai_stt_diarization_model(model_id: str) -> bool:
    return openai_stt_model_id_from_display_text(model_id) == OPENAI_STT_DIARIZATION_MODEL


def openai_stt_transcription_response_format(model_id: str) -> str:
    if is_known_openai_gpt_stt_model(model_id):
        return "json"

    return "verbose_json"


def openai_stt_supports_prompt(model_id: str) -> bool:
    return not is_openai_stt_diarization_model(model_id)


def openai_stt_supports_timestamp_granularities(model_id: str) -> bool:
    return not is_known_openai_gpt_stt_model(model_id)


def openai_stt_uses_chunking_strategy(model_id: str) -> bool:
    return is_openai_stt_diarization_model(model_id)


def openai_stt_translation_model(model_id: str) -> str:
    normalized_model_id = openai_stt_model_id_from_display_text(model_id)
    if is_known_openai_gpt_stt_model(normalized_model_id):
        return OPENAI_STT_LEGACY_MODEL

    return normalized_model_id
