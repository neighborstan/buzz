from dataclasses import dataclass


OPENAI_STT_DEFAULT_MODEL = "gpt-4o-transcribe"
OPENAI_STT_LEGACY_MODEL = "whisper-1"


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
        model_id="gpt-4o-mini-transcribe",
        label="gpt-4o-mini-transcribe",
        tooltip="Faster and lower cost OpenAI transcription model.",
    ),
    OpenAISttModelPreset(
        model_id="gpt-4o-transcribe-diarize",
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
