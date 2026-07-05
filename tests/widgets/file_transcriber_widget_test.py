from unittest.mock import Mock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox
from pytestqt.qtbot import QtBot

from buzz.model_loader import ModelType, TranscriptionModel
from buzz.settings.settings import Settings
from buzz.transcriber.transcriber import (
    FileTranscriptionOptions,
    OutputFormat,
    Task,
    TranscriptionOptions,
)
from buzz.widgets.preferences_dialog.models.file_transcription_preferences import (
    FileTranscriptionPreferences,
)
from buzz.widgets.transcriber.file_transcription_form_widget import (
    FileTranscriptionFormWidget,
)
from buzz.widgets.transcriber.file_transcriber_widget import FileTranscriberWidget
from buzz.widgets.transcriber.transcription_options_group_box import (
    TranscriptionOptionsGroupBox,
)
from tests.audio import test_audio_path


class FakePluginManager:
    def __init__(self, enabled=False, config=None):
        self.enabled = enabled
        self.config = config or {}

    def is_enabled(self, plugin_id: str) -> bool:
        return plugin_id == "transcript_post_processing" and self.enabled

    def get_config(self, plugin_id: str) -> dict:
        if plugin_id != "transcript_post_processing":
            return {}
        return self.config


def openai_preferences():
    return FileTranscriptionPreferences(
        language=None,
        task=Task.TRANSCRIBE,
        model=TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API),
        word_level_timings=False,
        extract_speech=False,
        initial_prompt="",
        enable_llm_translation=False,
        llm_prompt="",
        llm_model="",
        output_formats={OutputFormat.TXT},
    )


def local_preferences():
    return FileTranscriptionPreferences(
        language=None,
        task=Task.TRANSCRIBE,
        model=TranscriptionModel(model_type=ModelType.WHISPER),
        word_level_timings=False,
        extract_speech=False,
        initial_prompt="",
        enable_llm_translation=False,
        llm_prompt="",
        llm_model="",
        output_formats={OutputFormat.TXT},
    )


def preview_text(widget: FileTranscriberWidget) -> str:
    return widget.cost_preview_label.text()


class TestFileTranscriberWidget:
    def test_should_set_window_title(self, qtbot: QtBot):
        widget = FileTranscriberWidget(
            file_paths=[test_audio_path],
        )
        qtbot.add_widget(widget)
        assert widget.windowTitle() == "whisper-french.mp3"

    def test_should_emit_triggered_event(self, qtbot: QtBot):
        with patch.object(
            FileTranscriberWidget, "load_preferences", return_value=local_preferences()
        ), patch.object(
            TranscriptionModel, "get_local_model_path", return_value="model-path"
        ):
            widget = FileTranscriberWidget(
                file_paths=[test_audio_path],
            )
        qtbot.add_widget(widget)

        mock_triggered = Mock()
        widget.triggered.connect(mock_triggered)

        with qtbot.wait_signal(widget.triggered, timeout=30 * 1000):
            qtbot.mouseClick(widget.run_button, Qt.MouseButton.LeftButton)

        (
            transcription_options,
            file_transcription_options,
            model_path,
        ) = mock_triggered.call_args[0][0]
        assert transcription_options.language is None
        assert file_transcription_options.file_paths == [test_audio_path]
        assert len(model_path) > 0

    def test_on_model_loaded_empty_path_shows_error_for_local_model(self, qtbot: QtBot):
        widget = FileTranscriberWidget(file_paths=[test_audio_path])
        qtbot.add_widget(widget)
        widget.transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.FASTER_WHISPER)
        )

        mock_triggered = Mock()
        widget.triggered.connect(mock_triggered)

        with patch("buzz.widgets.transcriber.file_transcriber_widget.show_model_download_error_dialog") as mock_err, \
             patch.object(widget, "save_preferences"):
            widget.on_model_loaded("")
            mock_err.assert_called_once()
            mock_triggered.assert_not_called()

    def test_on_model_loaded_empty_path_allowed_for_openai_api(self, qtbot: QtBot):
        widget = FileTranscriberWidget(file_paths=[test_audio_path])
        qtbot.add_widget(widget)
        widget.transcription_options = TranscriptionOptions(
            model=TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API)
        )

        mock_triggered = Mock()
        widget.triggered.connect(mock_triggered)

        with patch("buzz.widgets.transcriber.file_transcriber_widget.show_model_download_error_dialog") as mock_err, \
             patch.object(widget, "save_preferences"):
            widget.on_model_loaded("")
            mock_err.assert_not_called()
            mock_triggered.assert_called_once()

    def test_should_show_openai_transcription_cost_preview(self, qtbot: QtBot):
        Settings().set_value(Settings.Key.OPENAI_API_MODEL, "gpt-4o-transcribe")

        with patch.object(
            FileTranscriberWidget, "load_preferences", return_value=openai_preferences()
        ), patch(
            "buzz.widgets.transcriber.file_transcriber_widget.probe_media_duration_seconds",
            return_value=600,
        ):
            widget = FileTranscriberWidget(file_paths=[test_audio_path])
        qtbot.add_widget(widget)

        text = preview_text(widget)
        assert "Transcription: ~$0.06" in text
        assert "Total: ~$0.06" in text

    def test_should_show_token_rate_for_token_priced_stt_model(self, qtbot: QtBot):
        Settings().set_value(
            Settings.Key.OPENAI_API_MODEL, "gpt-4o-transcribe-diarize"
        )

        with patch.object(
            FileTranscriberWidget, "load_preferences", return_value=openai_preferences()
        ), patch(
            "buzz.widgets.transcriber.file_transcriber_widget.probe_media_duration_seconds",
            return_value=600,
        ):
            widget = FileTranscriberWidget(file_paths=[test_audio_path])
        qtbot.add_widget(widget)

        text = preview_text(widget)
        assert "Transcription: Audio token rate" in text
        assert "input $2.50/1M" in text
        assert "output $10.00/1M" in text
        assert "exact estimate unavailable" in text
        assert "Transcription: price unknown" not in text

    def test_should_include_post_processing_cost_preview(self, qtbot: QtBot):
        plugin_manager = FakePluginManager(
            enabled=True,
            config={
                "api_key": "sk-test",
                "model": "gpt-5.4-mini",
                "reasoning_effort": "medium",
                "save_to_file": True,
            },
        )

        with patch.object(
            FileTranscriberWidget, "load_preferences", return_value=local_preferences()
        ), patch(
            "buzz.widgets.transcriber.file_transcriber_widget.probe_media_duration_seconds",
            return_value=120,
        ):
            widget = FileTranscriberWidget(
                file_paths=[test_audio_path],
                plugin_manager=plugin_manager,
            )
        qtbot.add_widget(widget)

        text = preview_text(widget)
        assert "Post-processing:" in text
        assert "Total:" in text
        assert "Transcription:" not in text

    def test_should_mark_unknown_post_processing_price(self, qtbot: QtBot):
        plugin_manager = FakePluginManager(
            enabled=True,
            config={
                "api_key": "sk-test",
                "model": "custom-model",
                "reasoning_effort": "medium",
                "save_to_file": True,
            },
        )

        with patch.object(
            FileTranscriberWidget, "load_preferences", return_value=local_preferences()
        ), patch(
            "buzz.widgets.transcriber.file_transcriber_widget.probe_media_duration_seconds",
            return_value=120,
        ):
            widget = FileTranscriberWidget(
                file_paths=[test_audio_path],
                plugin_manager=plugin_manager,
            )
        qtbot.add_widget(widget)

        assert "Post-processing: price unknown" in preview_text(widget)

    def test_should_estimate_gpt5_mini_post_processing_price(self, qtbot: QtBot):
        plugin_manager = FakePluginManager(
            enabled=True,
            config={
                "api_key": "sk-test",
                "model": "gpt-5-mini",
                "reasoning_effort": "medium",
                "save_to_file": True,
            },
        )

        with patch.object(
            FileTranscriberWidget, "load_preferences", return_value=local_preferences()
        ), patch(
            "buzz.widgets.transcriber.file_transcriber_widget.probe_media_duration_seconds",
            return_value=120,
        ):
            widget = FileTranscriberWidget(
                file_paths=[test_audio_path],
                plugin_manager=plugin_manager,
            )
        qtbot.add_widget(widget)

        text = preview_text(widget)
        assert "Post-processing:" in text
        assert "price unknown" not in text
        assert "Total:" in text

    def test_should_warn_for_advanced_post_processing_reasoning(self, qtbot: QtBot):
        plugin_manager = FakePluginManager(
            enabled=True,
            config={
                "api_key": "sk-test",
                "model": "gpt-5.5",
                "reasoning_effort": "xhigh",
                "save_to_file": True,
            },
        )

        with patch.object(
            FileTranscriberWidget, "load_preferences", return_value=local_preferences()
        ), patch(
            "buzz.widgets.transcriber.file_transcriber_widget.probe_media_duration_seconds",
            return_value=120,
        ):
            widget = FileTranscriberWidget(
                file_paths=[test_audio_path],
                plugin_manager=plugin_manager,
            )
        qtbot.add_widget(widget)

        assert "High reasoning effort" in preview_text(widget)


class TestFileTranscriptionFormWidget:
    def test_should_show_markdown_export_format(self, qtbot: QtBot):
        widget = FileTranscriptionFormWidget(
            transcription_options=TranscriptionOptions(),
            file_transcription_options=FileTranscriptionOptions(),
        )
        qtbot.add_widget(widget)

        checkbox_texts = {
            checkbox.text() for checkbox in widget.findChildren(QCheckBox)
        }

        assert OutputFormat.MD.value.upper() in checkbox_texts


class TestTranscriptionOptionsGroupBox:
    def test_should_show_openai_model_field_for_openai_backend(self, qtbot: QtBot):
        Settings().set_value(
            Settings.Key.OPENAI_API_MODEL, "gpt-4o-transcribe-diarize"
        )
        widget = TranscriptionOptionsGroupBox(
            default_transcription_options=TranscriptionOptions(
                model=TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API)
            )
        )
        qtbot.add_widget(widget)

        label = widget.form_layout.labelForField(widget.openai_model_line_edit)

        assert label.text() == "Модель OpenAI:"
        assert widget.openai_model_line_edit.isReadOnly()
        assert widget.openai_model_line_edit.text() == "gpt-4o-transcribe-diarize"
        assert not widget.openai_model_line_edit.isHidden()
        assert widget.openai_model_hint_label.text() == (
            "Изменить модель: Справка -> Настройки -> Общие"
        )
        assert not widget.openai_model_hint_label.isHidden()
        assert not widget.openai_access_token_edit.isHidden()

    def test_should_hide_openai_model_field_for_local_backend(self, qtbot: QtBot):
        widget = TranscriptionOptionsGroupBox(
            default_transcription_options=TranscriptionOptions(
                model=TranscriptionModel(model_type=ModelType.WHISPER)
            )
        )
        qtbot.add_widget(widget)

        assert widget.openai_model_line_edit.isHidden()
        assert widget.openai_model_hint_label.isHidden()
        assert widget.openai_access_token_edit.isHidden()

    def test_should_show_custom_openai_model_id(self, qtbot: QtBot):
        Settings().set_value(Settings.Key.OPENAI_API_MODEL, "custom-transcribe-model")
        widget = TranscriptionOptionsGroupBox(
            default_transcription_options=TranscriptionOptions(
                model=TranscriptionModel(model_type=ModelType.OPEN_AI_WHISPER_API)
            )
        )
        qtbot.add_widget(widget)

        assert widget.openai_model_line_edit.text() == "custom-transcribe-model"

    def test_should_refresh_openai_model_display_when_backend_changes(
        self, qtbot: QtBot
    ):
        Settings().set_value(
            Settings.Key.OPENAI_API_MODEL, "gpt-4o-mini-transcribe"
        )
        widget = TranscriptionOptionsGroupBox(
            default_transcription_options=TranscriptionOptions(
                model=TranscriptionModel(model_type=ModelType.WHISPER)
            )
        )
        qtbot.add_widget(widget)

        widget.model_type_combo_box.setCurrentText("OpenAI API")

        assert widget.transcription_options.model.model_type == (
            ModelType.OPEN_AI_WHISPER_API
        )
        assert widget.openai_model_line_edit.text() == "gpt-4o-mini-transcribe"
        assert not widget.openai_model_line_edit.isHidden()
        assert not widget.openai_model_hint_label.isHidden()
