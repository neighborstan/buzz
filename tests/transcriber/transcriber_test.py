import pathlib

import pytest

from buzz.transcriber.file_transcriber import FileTranscriber, write_output, to_timestamp
from buzz.transcriber.transcriber import (
    FileTranscriptionOptions,
    FileTranscriptionTask,
    OutputFormat,
    Segment,
    TranscriptionOptions,
)


class TestToTimestamp:
    def test_to_timestamp(self):
        assert to_timestamp(0) == "00:00:00.000"
        assert to_timestamp(123456789) == "34:17:36.789"


@pytest.mark.parametrize(
    "output_format,output_text",
    [
        (OutputFormat.TXT, "Bien venue dans "),
        (
            OutputFormat.SRT,
            "1\n00:00:00,040 --> 00:00:00,299\nBien\n\n2\n00:00:00,299 --> 00:00:00,329\nvenue dans\n\n",
        ),
        (
            OutputFormat.VTT,
            "WEBVTT\n\n00:00:00.040 --> 00:00:00.299\nBien\n\n00:00:00.299 --> 00:00:00.329\nvenue dans\n\n",
        ),
        (
            OutputFormat.MD,
            "- [00:00:00.040 - 00:00:00.299] Bien\n"
            "- [00:00:00.299 - 00:00:00.329] venue dans\n",
        ),
    ],
)
def test_write_output(
    tmp_path: pathlib.Path, output_format: OutputFormat, output_text: str
):
    output_file_path = tmp_path / "whisper.txt"
    segments = [Segment(40, 299, "Bien"), Segment(299, 329, "venue dans")]

    write_output(
        path=str(output_file_path), segments=segments, output_format=output_format
    )

    with open(output_file_path, encoding="utf-8") as output_file:
        assert output_text == output_file.read()


def test_write_markdown_output_preserves_speaker_labels(tmp_path: pathlib.Path):
    output_file_path = tmp_path / "meeting.md"
    segments = [
        Segment(0, 1500, "speaker_0: Start the meeting"),
        Segment(1500, 3200, "speaker_1: Ready"),
    ]

    write_output(
        path=str(output_file_path), segments=segments, output_format=OutputFormat.MD
    )

    with open(output_file_path, encoding="utf-8") as output_file:
        assert output_file.read() == (
            "- [00:00:00.000 - 00:00:01.500] speaker_0: Start the meeting\n"
            "- [00:00:01.500 - 00:00:03.200] speaker_1: Ready\n"
        )


class DummyFileTranscriber(FileTranscriber):
    def transcribe(self):
        return [Segment(0, 1000, "speaker_0: Hello")]

    def stop(self):
        pass


def test_file_transcriber_writes_markdown_output(tmp_path: pathlib.Path, qtbot):
    task = FileTranscriptionTask(
        transcription_options=TranscriptionOptions(),
        file_transcription_options=FileTranscriptionOptions(
            output_formats={OutputFormat.MD}
        ),
        model_path="",
        file_path=str(tmp_path / "meeting.mkv"),
        output_directory=str(tmp_path),
    )
    transcriber = DummyFileTranscriber(task=task)

    transcriber.run()

    output_files = list(tmp_path.glob("*.md"))
    assert len(output_files) == 1
    with open(output_files[0], encoding="utf-8") as output_file:
        assert output_file.read() == (
            "- [00:00:00.000 - 00:00:01.000] speaker_0: Hello\n"
        )
