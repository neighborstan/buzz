"""
Prepared transcript post-processing plugin for Buzz.

After a transcription completes, sends the full timestamped transcript to an
OpenAI-compatible chat completions API and writes the cleaned result to a
Markdown file. This is intentionally separate from STT model selection and does
not replace the saved transcript segments.
"""

import logging
import os

from buzz.plugins.base import (
    BuzzPlugin,
    ConfigField,
    ConfigFieldType,
    PluginContext,
    PluginMetadata,
    plugin_gettext,
)
from buzz.transcriber.file_transcriber import to_timestamp

logger = logging.getLogger(__name__)

_ = plugin_gettext(__file__)

DEFAULT_MODEL = "gpt-5.4-mini"

DEFAULT_PROMPT = """You are cleaning up a full meeting transcript.

Return only a prepared Markdown transcript.
Do not summarize. Do not shorten the transcript. Keep every utterance and all meaningful content.
Preserve chronological order.
Preserve speaker labels exactly when they are present.
Preserve timestamps when they are present.
Preserve technical terms, acronyms, product names, file names, code terms, numbers and names.
Improve punctuation, paragraphing and readability.
Remove only obvious filler or broken repeated fragments when meaning is unchanged.
Do not invent words, facts, decisions, action items or speaker names.
Mark unclear fragments as unclear instead of guessing.
"""


class TranscriptPostProcessingPlugin(BuzzPlugin):
    metadata = PluginMetadata(
        id="transcript_post_processing",
        name=_("Transcript Post-processing"),
        description=_(
            "Clean up the full transcript via an OpenAI-compatible API and "
            "save a prepared Markdown transcript."
        ),
        version="1.0.0",
        pip_dependencies=[],
        config_fields=[
            ConfigField(
                key="api_url",
                label=_("API base URL"),
                type=ConfigFieldType.TEXT,
                default="https://api.openai.com/v1",
                placeholder="https://api.openai.com/v1",
            ),
            ConfigField(
                key="api_key",
                label=_("API key"),
                type=ConfigFieldType.PASSWORD,
                default="",
                placeholder="sk-...",
            ),
            ConfigField(
                key="model",
                label=_("Post-processing model"),
                type=ConfigFieldType.TEXT,
                default=DEFAULT_MODEL,
            ),
            ConfigField(
                key="prompt",
                label=_("Cleanup prompt"),
                type=ConfigFieldType.TEXTAREA,
                default=DEFAULT_PROMPT,
            ),
            ConfigField(
                key="save_to_file",
                label=_("Save prepared transcript to a file"),
                type=ConfigFieldType.BOOL,
                default=True,
            ),
            ConfigField(
                key="output_folder",
                label=_("Output folder"),
                type=ConfigFieldType.TEXT,
                default="",
                description=_("Leave empty to save next to the source file."),
            ),
        ],
    )

    def on_complete(self, transcription_id, task, segments, context: PluginContext):
        cfg = context.config
        if not _coerce_bool(cfg.get("save_to_file", True)):
            context.log.info("Transcript post-processing skipped: file saving disabled")
            return

        api_key = (cfg.get("api_key") or "").strip()
        if not api_key:
            context.log.warning("Transcript post-processing skipped: no API key configured")
            return

        transcript = self._format_transcript(segments)
        if not transcript:
            context.log.info("Transcript post-processing skipped: empty transcript")
            return

        prepared = self._post_process(cfg, transcript, context)
        if not prepared:
            return

        self._write_file(cfg, task, prepared, context)

    def _format_transcript(self, segments) -> str:
        lines = []
        for segment in segments:
            text = (getattr(segment, "text", "") or "").strip()
            if not text:
                continue
            start = _segment_time(segment, "start", "start_time")
            end = _segment_time(segment, "end", "end_time")
            lines.append(f"- [{to_timestamp(start)} - {to_timestamp(end)}] {text}")
        return "\n".join(lines).strip()

    def _post_process(self, cfg, transcript, context):
        try:
            from openai import OpenAI
        except ImportError:
            context.log.error("openai package not available")
            return None

        base_url = (cfg.get("api_url") or "").strip() or None
        model = (cfg.get("model") or DEFAULT_MODEL).strip()
        prompt = (cfg.get("prompt") or DEFAULT_PROMPT).strip()

        try:
            client = OpenAI(api_key=cfg["api_key"], base_url=base_url, max_retries=0)
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": (
                            "Clean up this full transcript according to the "
                            "system instructions.\n\nTranscript:\n"
                            f"{transcript}"
                        ),
                    },
                ],
                timeout=180.0,
            )
        except Exception as exc:
            context.log.error("Transcript post-processing request failed: %s", exc)
            return None

        if completion and completion.choices and completion.choices[0].message:
            content = completion.choices[0].message.content
            return content.strip() if content else None
        context.log.error("Transcript post-processing: empty response from server")
        return None

    def _write_file(self, cfg, task, prepared_transcript, context):
        try:
            source_path = _source_path(task)
            stem = _source_stem(source_path)
            folder = (cfg.get("output_folder") or "").strip()
            if not folder:
                folder = getattr(task, "output_directory", None)
            if not folder:
                folder = os.path.dirname(source_path) or os.getcwd()

            os.makedirs(folder, exist_ok=True)
            out_path = os.path.join(folder, f"{stem}.prepared.md")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(prepared_transcript)
                if not prepared_transcript.endswith("\n"):
                    f.write("\n")
            context.log.info("Prepared transcript written to %s", out_path)
        except Exception as exc:
            context.log.error("Failed to write prepared transcript file: %s", exc)


def _segment_time(segment, primary_attr, fallback_attr) -> int:
    value = getattr(segment, primary_attr, None)
    if value is None:
        value = getattr(segment, fallback_attr, 0)
    return int(value or 0)


def _source_path(task) -> str:
    return (
        getattr(task, "original_file_path", None)
        or getattr(task, "file_path", None)
        or "transcript"
    )


def _source_stem(source_path: str) -> str:
    stem = os.path.splitext(os.path.basename(source_path))[0] or "transcript"
    if stem.endswith("_speech"):
        stem = stem[:-7]
    return stem or "transcript"


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return value != 0
    return bool(value)
