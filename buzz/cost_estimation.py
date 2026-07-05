"""OpenAI API cost estimation helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

PRICING_SOURCE_URL = "https://developers.openai.com/api/docs/pricing"
PRICING_CHECKED_DATE = "2026-07-04"
PRICE_UNKNOWN = "price unknown"
RATE_ESTIMATE_UNAVAILABLE = "rate known; exact estimate unavailable before API usage"

DEFAULT_WARNING_THRESHOLD_USD = 1.0
DEFAULT_TRANSCRIPT_TOKENS_PER_MINUTE = 180
DEFAULT_OUTPUT_TOKEN_MULTIPLIER = 1.0
CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class ModelPricing:
    model_id: str
    source_url: str = PRICING_SOURCE_URL
    checked_date: str = PRICING_CHECKED_DATE
    per_minute_usd: Optional[float] = None
    input_per_1m_tokens_usd: Optional[float] = None
    cached_input_per_1m_tokens_usd: Optional[float] = None
    output_per_1m_tokens_usd: Optional[float] = None
    token_pricing_label: str = "Text token rate"

    @property
    def has_minute_pricing(self) -> bool:
        return self.per_minute_usd is not None

    @property
    def has_token_pricing(self) -> bool:
        return (
            self.input_per_1m_tokens_usd is not None
            and self.output_per_1m_tokens_usd is not None
        )


@dataclass(frozen=True)
class CostLine:
    label: str
    amount_usd: Optional[float]
    detail: str = ""
    warning: bool = False

    @property
    def is_known(self) -> bool:
        return self.amount_usd is not None


@dataclass(frozen=True)
class CostBreakdown:
    transcription: Optional[CostLine] = None
    post_processing: Optional[CostLine] = None
    total_usd: Optional[float] = None
    known_subtotal_usd: float = 0.0
    warnings: tuple[str, ...] = ()

    @property
    def has_unknown(self) -> bool:
        return any(
            line is not None and not line.is_known
            for line in (self.transcription, self.post_processing)
        )

    @property
    def is_empty(self) -> bool:
        return self.transcription is None and self.post_processing is None


OPENAI_MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-4o-transcribe": ModelPricing(
        model_id="gpt-4o-transcribe",
        per_minute_usd=0.006,
        input_per_1m_tokens_usd=2.50,
        output_per_1m_tokens_usd=10.00,
        token_pricing_label="Audio token rate",
    ),
    "gpt-4o-mini-transcribe": ModelPricing(
        model_id="gpt-4o-mini-transcribe",
        per_minute_usd=0.003,
        input_per_1m_tokens_usd=1.25,
        output_per_1m_tokens_usd=5.00,
        token_pricing_label="Audio token rate",
    ),
    "gpt-4o-transcribe-diarize": ModelPricing(
        model_id="gpt-4o-transcribe-diarize",
        source_url="https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize",
        input_per_1m_tokens_usd=2.50,
        output_per_1m_tokens_usd=10.00,
        token_pricing_label="Audio token rate",
    ),
    "whisper-1": ModelPricing(
        model_id="whisper-1",
        source_url="https://developers.openai.com/api/docs/models/whisper-1",
        per_minute_usd=0.006,
    ),
    "gpt-5.5": ModelPricing(
        model_id="gpt-5.5",
        input_per_1m_tokens_usd=5.00,
        cached_input_per_1m_tokens_usd=0.50,
        output_per_1m_tokens_usd=30.00,
    ),
    "gpt-5.4": ModelPricing(
        model_id="gpt-5.4",
        input_per_1m_tokens_usd=2.50,
        cached_input_per_1m_tokens_usd=0.25,
        output_per_1m_tokens_usd=15.00,
    ),
    "gpt-5.4-mini": ModelPricing(
        model_id="gpt-5.4-mini",
        input_per_1m_tokens_usd=0.75,
        cached_input_per_1m_tokens_usd=0.075,
        output_per_1m_tokens_usd=4.50,
    ),
    "gpt-5.4-nano": ModelPricing(
        model_id="gpt-5.4-nano",
        input_per_1m_tokens_usd=0.20,
        cached_input_per_1m_tokens_usd=0.02,
        output_per_1m_tokens_usd=1.25,
    ),
    "gpt-5-mini": ModelPricing(
        model_id="gpt-5-mini",
        source_url="https://developers.openai.com/api/docs/models/gpt-5-mini",
        input_per_1m_tokens_usd=0.25,
        cached_input_per_1m_tokens_usd=0.025,
        output_per_1m_tokens_usd=2.00,
    ),
    "gpt-5-nano": ModelPricing(
        model_id="gpt-5-nano",
        source_url="https://developers.openai.com/api/docs/models/gpt-5-nano",
        input_per_1m_tokens_usd=0.05,
        cached_input_per_1m_tokens_usd=0.005,
        output_per_1m_tokens_usd=0.40,
    ),
}

REASONING_WARNING_MODELS = frozenset(
    {"gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"}
)
ADVANCED_REASONING_EFFORTS = frozenset({"high", "xhigh"})


def pricing_for_model(model_id: str | None) -> Optional[ModelPricing]:
    normalized = (model_id or "").strip()
    if not normalized:
        return None
    return OPENAI_MODEL_PRICING.get(normalized)


def estimate_transcription_cost(
    model_id: str | None,
    duration_seconds: float | None,
    warning_threshold_usd: float = DEFAULT_WARNING_THRESHOLD_USD,
) -> CostLine:
    pricing = pricing_for_model(model_id)
    if pricing is None:
        return CostLine(label="Transcription", amount_usd=None, detail=PRICE_UNKNOWN)
    if not pricing.has_minute_pricing:
        if pricing.has_token_pricing:
            return CostLine(
                label="Transcription",
                amount_usd=None,
                detail=f"{format_token_rate(pricing)}; {RATE_ESTIMATE_UNAVAILABLE}",
            )
        return CostLine(label="Transcription", amount_usd=None, detail=PRICE_UNKNOWN)
    if duration_seconds is None or duration_seconds <= 0:
        return CostLine(label="Transcription", amount_usd=None, detail=PRICE_UNKNOWN)

    duration_minutes = duration_seconds / 60.0
    amount = duration_minutes * float(pricing.per_minute_usd)
    return CostLine(
        label="Transcription",
        amount_usd=amount,
        detail=f"{duration_minutes:.1f} min at {format_usd(pricing.per_minute_usd)}/min",
        warning=amount >= warning_threshold_usd,
    )


def estimate_text_tokens(text: str | None) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    return max(1, math.ceil(len(normalized) / CHARS_PER_TOKEN))


def estimate_transcript_tokens_from_duration(
    duration_seconds: float | None,
    tokens_per_minute: int = DEFAULT_TRANSCRIPT_TOKENS_PER_MINUTE,
) -> Optional[int]:
    if duration_seconds is None or duration_seconds <= 0:
        return None
    return max(1, math.ceil((duration_seconds / 60.0) * tokens_per_minute))


def estimate_post_processing_cost(
    model_id: str | None,
    transcript_text: str | None = None,
    prompt_text: str | None = None,
    duration_seconds: float | None = None,
    warning_threshold_usd: float = DEFAULT_WARNING_THRESHOLD_USD,
) -> CostLine:
    pricing = pricing_for_model(model_id)
    if pricing is None or not pricing.has_token_pricing:
        return CostLine(label="Post-processing", amount_usd=None, detail=PRICE_UNKNOWN)

    prompt_tokens = estimate_text_tokens(prompt_text)
    transcript_tokens = estimate_text_tokens(transcript_text)
    if transcript_tokens == 0:
        duration_tokens = estimate_transcript_tokens_from_duration(duration_seconds)
        if duration_tokens is None:
            return CostLine(
                label="Post-processing",
                amount_usd=None,
                detail=PRICE_UNKNOWN,
            )
        transcript_tokens = duration_tokens

    input_tokens = prompt_tokens + transcript_tokens
    output_tokens = max(1, math.ceil(transcript_tokens * DEFAULT_OUTPUT_TOKEN_MULTIPLIER))
    amount = (
        input_tokens * float(pricing.input_per_1m_tokens_usd)
        + output_tokens * float(pricing.output_per_1m_tokens_usd)
    ) / 1_000_000.0
    return CostLine(
        label="Post-processing",
        amount_usd=amount,
        detail=f"~{input_tokens} input / ~{output_tokens} output tokens",
        warning=amount >= warning_threshold_usd,
    )


def build_cost_breakdown(
    stt_model_id: str | None = None,
    include_transcription: bool = False,
    duration_seconds: float | None = None,
    post_processing_model_id: str | None = None,
    include_post_processing: bool = False,
    post_processing_prompt: str | None = None,
    transcript_text: str | None = None,
    reasoning_effort: str | None = None,
    warning_threshold_usd: float = DEFAULT_WARNING_THRESHOLD_USD,
) -> CostBreakdown:
    transcription = None
    post_processing = None
    warnings: list[str] = []

    if include_transcription:
        transcription = estimate_transcription_cost(
            stt_model_id,
            duration_seconds,
            warning_threshold_usd=warning_threshold_usd,
        )
        if transcription.warning:
            warnings.append("Transcription estimate crosses the warning threshold.")

    if include_post_processing:
        post_processing = estimate_post_processing_cost(
            post_processing_model_id,
            transcript_text=transcript_text,
            prompt_text=post_processing_prompt,
            duration_seconds=duration_seconds,
            warning_threshold_usd=warning_threshold_usd,
        )
        if post_processing.warning:
            warnings.append("Post-processing estimate crosses the warning threshold.")
        if has_advanced_reasoning_warning(post_processing_model_id, reasoning_effort):
            warnings.append("High reasoning effort can be slower or more expensive.")

    known_lines = [
        line
        for line in (transcription, post_processing)
        if line is not None and line.is_known
    ]
    known_subtotal = sum(float(line.amount_usd or 0.0) for line in known_lines)
    has_unknown = any(
        line is not None and not line.is_known
        for line in (transcription, post_processing)
    )
    total = known_subtotal if known_lines and not has_unknown else None

    return CostBreakdown(
        transcription=transcription,
        post_processing=post_processing,
        total_usd=total,
        known_subtotal_usd=known_subtotal,
        warnings=tuple(warnings),
    )


def has_advanced_reasoning_warning(
    model_id: str | None,
    reasoning_effort: str | None,
) -> bool:
    model = (model_id or "").strip()
    effort = (reasoning_effort or "").strip().lower()
    return model in REASONING_WARNING_MODELS and effort in ADVANCED_REASONING_EFFORTS


def format_cost_preview(breakdown: CostBreakdown) -> str:
    if breakdown.is_empty:
        return "OpenAI API estimate: no OpenAI API cost for selected workflow."

    lines = ["OpenAI API estimate:"]
    for line in (breakdown.transcription, breakdown.post_processing):
        if line is None:
            continue
        if line.is_known:
            detail = f" ({line.detail})" if line.detail else ""
            lines.append(f"{line.label}: ~{format_usd(line.amount_usd)}{detail}")
        else:
            lines.append(f"{line.label}: {line.detail or PRICE_UNKNOWN}")

    if breakdown.total_usd is not None:
        lines.append(f"Total: ~{format_usd(breakdown.total_usd)}")
    elif breakdown.known_subtotal_usd > 0:
        lines.append(f"Known subtotal: ~{format_usd(breakdown.known_subtotal_usd)}")

    for warning in breakdown.warnings:
        lines.append(f"Warning: {warning}")

    return "\n".join(lines)


def format_token_rate(pricing: ModelPricing) -> str:
    if not pricing.has_token_pricing:
        return PRICE_UNKNOWN

    parts = [
        f"{pricing.token_pricing_label}: "
        f"input {format_usd(pricing.input_per_1m_tokens_usd)}/1M"
    ]
    if pricing.cached_input_per_1m_tokens_usd is not None:
        parts.append(
            f"cached input {format_usd(pricing.cached_input_per_1m_tokens_usd)}/1M"
        )
    parts.append(f"output {format_usd(pricing.output_per_1m_tokens_usd)}/1M")
    return ", ".join(parts)


def format_usd(amount: float | None) -> str:
    if amount is None:
        return PRICE_UNKNOWN
    if amount == 0:
        return "$0.00"
    if amount < 0.01:
        return f"${amount:.4f}"
    return f"${amount:.2f}"


def probe_media_duration_seconds(file_path: str) -> Optional[float]:
    try:
        info = _probe_video(file_path)
        duration_ms = int(info.get("duration_ms", 0) or 0)
    except Exception:
        return None
    if duration_ms <= 0:
        return None
    return duration_ms / 1000.0


def _probe_video(file_path: str) -> dict:
    from buzz.ffmpeg_video_player import probe_video

    return probe_video(file_path)
