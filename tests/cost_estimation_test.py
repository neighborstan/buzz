from buzz import cost_estimation as cost


def test_pricing_metadata_has_source_and_checked_date():
    pricing = cost.pricing_for_model("gpt-5.4-mini")

    assert pricing is not None
    assert pricing.source_url == cost.PRICING_SOURCE_URL
    assert pricing.checked_date == cost.PRICING_CHECKED_DATE
    assert pricing.input_per_1m_tokens_usd == 0.75
    assert pricing.cached_input_per_1m_tokens_usd == 0.075
    assert pricing.output_per_1m_tokens_usd == 4.50


def test_pricing_metadata_includes_model_page_prices():
    diarize = cost.pricing_for_model("gpt-4o-transcribe-diarize")
    whisper = cost.pricing_for_model("whisper-1")
    gpt5_mini = cost.pricing_for_model("gpt-5-mini")
    gpt5_nano = cost.pricing_for_model("gpt-5-nano")

    assert diarize is not None
    assert diarize.source_url.endswith("/gpt-4o-transcribe-diarize")
    assert diarize.input_per_1m_tokens_usd == 2.50
    assert diarize.output_per_1m_tokens_usd == 10.00

    assert whisper is not None
    assert whisper.per_minute_usd == 0.006

    assert gpt5_mini is not None
    assert gpt5_mini.input_per_1m_tokens_usd == 0.25
    assert gpt5_mini.cached_input_per_1m_tokens_usd == 0.025
    assert gpt5_mini.output_per_1m_tokens_usd == 2.00

    assert gpt5_nano is not None
    assert gpt5_nano.input_per_1m_tokens_usd == 0.05
    assert gpt5_nano.cached_input_per_1m_tokens_usd == 0.005
    assert gpt5_nano.output_per_1m_tokens_usd == 0.40


def test_unknown_model_has_no_pricing():
    assert cost.pricing_for_model("custom-model") is None


def test_estimates_transcription_cost_from_duration():
    line = cost.estimate_transcription_cost("gpt-4o-transcribe", 600)

    assert line.is_known
    assert line.amount_usd == 0.06
    assert "10.0 min" in line.detail


def test_estimates_whisper_cost_from_duration():
    line = cost.estimate_transcription_cost("whisper-1", 600)

    assert line.is_known
    assert line.amount_usd == 0.06
    assert "10.0 min" in line.detail


def test_token_priced_transcription_model_shows_rate_without_amount():
    line = cost.estimate_transcription_cost("gpt-4o-transcribe-diarize", 600)

    assert line.is_known is False
    assert "Audio token rate" in line.detail
    assert "input $2.50/1M" in line.detail
    assert "output $10.00/1M" in line.detail
    assert cost.RATE_ESTIMATE_UNAVAILABLE in line.detail
    assert line.detail != cost.PRICE_UNKNOWN


def test_unknown_stt_price_returns_unknown_line():
    line = cost.estimate_transcription_cost("custom-stt-model", 600)

    assert line.is_known is False
    assert line.detail == cost.PRICE_UNKNOWN


def test_unknown_duration_returns_unknown_transcription_line():
    line = cost.estimate_transcription_cost("gpt-4o-transcribe", None)

    assert line.is_known is False
    assert line.detail == cost.PRICE_UNKNOWN


def test_estimates_post_processing_cost_from_text():
    line = cost.estimate_post_processing_cost(
        "gpt-5.4-mini",
        transcript_text="abcd" * 100,
        prompt_text="abcd" * 20,
    )

    assert line.is_known
    assert line.amount_usd > 0
    assert "input" in line.detail
    assert "output" in line.detail


def test_estimates_post_processing_cost_from_duration():
    line = cost.estimate_post_processing_cost("gpt-5.4-mini", duration_seconds=120)

    assert line.is_known
    assert "~360 input" in line.detail
    assert "~360 output" in line.detail


def test_unknown_post_processing_model_returns_unknown_line():
    line = cost.estimate_post_processing_cost("custom-model", duration_seconds=120)

    assert line.is_known is False
    assert line.detail == cost.PRICE_UNKNOWN


def test_estimates_gpt5_mini_post_processing_cost():
    line = cost.estimate_post_processing_cost("gpt-5-mini", duration_seconds=120)

    assert line.is_known
    assert line.amount_usd > 0
    assert "~360 input" in line.detail


def test_builds_partial_breakdown_with_unknown_part():
    breakdown = cost.build_cost_breakdown(
        stt_model_id="gpt-4o-transcribe",
        include_transcription=True,
        duration_seconds=60,
        post_processing_model_id="custom-model",
        include_post_processing=True,
    )

    assert breakdown.total_usd is None
    assert breakdown.known_subtotal_usd == 0.006
    assert breakdown.has_unknown is True
    preview = cost.format_cost_preview(breakdown)
    assert "Transcription: ~$0.0060" in preview
    assert "Post-processing: price unknown" in preview
    assert "Known subtotal: ~$0.0060" in preview


def test_warning_state_for_threshold_and_reasoning_effort():
    breakdown = cost.build_cost_breakdown(
        stt_model_id="gpt-4o-transcribe",
        include_transcription=True,
        duration_seconds=60,
        post_processing_model_id="gpt-5.5",
        include_post_processing=True,
        post_processing_prompt="prompt",
        transcript_text="abcd" * 100,
        reasoning_effort="xhigh",
        warning_threshold_usd=0.001,
    )

    assert len(breakdown.warnings) >= 2
    assert any("warning threshold" in warning for warning in breakdown.warnings)
    assert any("High reasoning effort" in warning for warning in breakdown.warnings)


def test_probe_media_duration_seconds_returns_none_on_failure(monkeypatch):
    def fail(_file_path):
        raise RuntimeError("ffprobe failed")

    monkeypatch.setattr(cost, "_probe_video", fail)

    assert cost.probe_media_duration_seconds("missing.wav") is None


def test_probe_media_duration_seconds_reads_duration(monkeypatch):
    monkeypatch.setattr(
        cost,
        "_probe_video",
        lambda _file_path: {"duration_ms": 1234},
    )

    assert cost.probe_media_duration_seconds("audio.wav") == 1.234
