import logging

from buzz.plugins.base import PluginContext
from buzz.plugins.loader import load_plugin_from_dir
from buzz.plugins.transcript_post_processing import plugin as tpp
from buzz.transcriber.transcriber import Segment


class _Task:
    def __init__(self, file_path, original_file_path=None, output_directory=None):
        self.file_path = str(file_path)
        self.original_file_path = (
            str(original_file_path) if original_file_path is not None else None
        )
        self.output_directory = str(output_directory) if output_directory else None


class _Service:
    pass


def _context(config):
    return PluginContext(
        config=config,
        transcription_service=_Service(),
        settings=None,
        logger=logging.getLogger("test"),
    )


def _config(tmp_path, **overrides):
    config = {
        "api_key": "key",
        "api_url": "https://example.com/v1",
        "model": "gpt-5.4-mini",
        "prompt": tpp.DEFAULT_PROMPT,
        "save_to_file": True,
        "output_folder": str(tmp_path),
    }
    config.update(overrides)
    return config


def test_transcript_post_processing_plugin_loads():
    loaded = load_plugin_from_dir("buzz/plugins/transcript_post_processing")

    assert loaded.metadata.id == "transcript_post_processing"
    keys = [field.key for field in loaded.metadata.config_fields]
    assert keys == [
        "api_url",
        "api_key",
        "model",
        "prompt",
        "save_to_file",
        "output_folder",
    ]
    assert "Do not summarize" in tpp.DEFAULT_PROMPT
    assert "Preserve speaker labels" in tpp.DEFAULT_PROMPT
    assert "Preserve chronological order" in tpp.DEFAULT_PROMPT
    assert "Preserve technical terms" in tpp.DEFAULT_PROMPT
    assert "Do not invent" in tpp.DEFAULT_PROMPT


def test_format_transcript_includes_timestamps_and_speaker_labels():
    transcript = tpp.TranscriptPostProcessingPlugin()._format_transcript(
        [
            Segment(0, 1500, "speaker_0: Hello."),
            Segment(2000, 3500, "speaker_1: Hi."),
            Segment(4000, 5000, " "),
        ]
    )

    assert transcript == (
        "- [00:00:00.000 - 00:00:01.500] speaker_0: Hello.\n"
        "- [00:00:02.000 - 00:00:03.500] speaker_1: Hi."
    )


def test_on_complete_writes_prepared_markdown(tmp_path, monkeypatch):
    captured = {}

    class _Message:
        content = "# Prepared\n\nspeaker_0: Hello."

    class _Choice:
        message = _Message()

    class _Completion:
        choices = [_Choice()]

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            captured["client"] = kwargs
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, *args, **kwargs):
            captured["request"] = kwargs
            return _Completion()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeClient)

    source = tmp_path / "meeting.wav"
    source.write_bytes(b"")
    output_folder = tmp_path / "out"
    segments = [Segment(0, 1000, "speaker_0: hello")]

    tpp.TranscriptPostProcessingPlugin().on_complete(
        "tid",
        _Task(file_path=source, original_file_path=source),
        segments,
        _context(_config(output_folder)),
    )

    out_file = output_folder / "meeting.prepared.md"
    assert out_file.read_text(encoding="utf-8") == "# Prepared\n\nspeaker_0: Hello.\n"
    assert captured["client"]["api_key"] == "key"
    assert captured["client"]["base_url"] == "https://example.com/v1"
    assert captured["request"]["model"] == "gpt-5.4-mini"
    assert captured["request"]["messages"][0]["content"] == tpp.DEFAULT_PROMPT.strip()
    user_message = captured["request"]["messages"][1]["content"]
    assert "Transcript:" in user_message
    assert "speaker_0: hello" in user_message
    assert "00:00:00.000" in user_message


def test_on_complete_uses_task_output_directory_when_config_folder_empty(
    tmp_path, monkeypatch
):
    class _Message:
        content = "prepared"

    class _Choice:
        message = _Message()

    class _Completion:
        choices = [_Choice()]

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, *args, **kwargs):
            return _Completion()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeClient)

    source = tmp_path / "meeting_speech.wav"
    source.write_bytes(b"")
    output_folder = tmp_path / "task-output"
    task = _Task(
        file_path=source,
        original_file_path=None,
        output_directory=output_folder,
    )

    tpp.TranscriptPostProcessingPlugin().on_complete(
        "tid",
        task,
        [Segment(0, 1000, "hello")],
        _context(_config(tmp_path, output_folder="")),
    )

    assert (output_folder / "meeting.prepared.md").read_text(
        encoding="utf-8"
    ) == "prepared\n"


def test_on_complete_skips_without_api_key(tmp_path, monkeypatch):
    def fail_client(*args, **kwargs):
        raise AssertionError("OpenAI client should not be created")

    import openai

    monkeypatch.setattr(openai, "OpenAI", fail_client)

    tpp.TranscriptPostProcessingPlugin().on_complete(
        "tid",
        _Task(file_path=tmp_path / "meeting.wav"),
        [Segment(0, 1000, "hello")],
        _context(_config(tmp_path, api_key="")),
    )

    assert not list(tmp_path.glob("*.prepared.md"))


def test_on_complete_skips_empty_transcript(tmp_path, monkeypatch):
    def fail_client(*args, **kwargs):
        raise AssertionError("OpenAI client should not be created")

    import openai

    monkeypatch.setattr(openai, "OpenAI", fail_client)

    tpp.TranscriptPostProcessingPlugin().on_complete(
        "tid",
        _Task(file_path=tmp_path / "meeting.wav"),
        [Segment(0, 1000, " ")],
        _context(_config(tmp_path)),
    )

    assert not list(tmp_path.glob("*.prepared.md"))


def test_on_complete_keeps_segments_when_api_fails(tmp_path, monkeypatch):
    class _FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = self

        @property
        def completions(self):
            return self

        def create(self, *args, **kwargs):
            raise RuntimeError("network failed")

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeClient)

    segments = [Segment(0, 1000, "speaker_0: hello")]
    tpp.TranscriptPostProcessingPlugin().on_complete(
        "tid",
        _Task(file_path=tmp_path / "meeting.wav"),
        segments,
        _context(_config(tmp_path)),
    )

    assert segments == [Segment(0, 1000, "speaker_0: hello")]
    assert not list(tmp_path.glob("*.prepared.md"))
