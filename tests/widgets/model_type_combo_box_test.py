import platform

import pytest

from buzz.model_loader import ModelType
from buzz.widgets.model_type_combo_box import ModelTypeComboBox


class TestModelTypeComboBox:
    @pytest.mark.parametrize(
        "model_types",
        [
            pytest.param(
                [
                    "Whisper",
                    "Whisper.cpp",
                    "Hugging Face",
                    "Faster Whisper",
                    "OpenAI API",
                    # Faster Whisper is not available on macOS x86_64
                ] if not (platform.system() == "Darwin" and platform.machine() == "x86_64") else [
                    "Whisper",
                    "Whisper.cpp",
                    "Hugging Face",
                    "OpenAI API",
                ],
            ),
        ],
    )
    def test_should_display_items(self, qtbot, model_types):
        widget = ModelTypeComboBox()
        qtbot.add_widget(widget)

        assert widget.count() == len(model_types)
        for index, model_type in enumerate(model_types):
            assert widget.itemText(index) == model_type

    def test_should_emit_internal_model_type_for_openai_api_label(self, qtbot):
        widget = ModelTypeComboBox(
            model_types=[ModelType.WHISPER, ModelType.OPEN_AI_WHISPER_API]
        )
        qtbot.add_widget(widget)

        with qtbot.wait_signal(widget.changed) as blocker:
            widget.setCurrentText("OpenAI API")

        assert blocker.args == [ModelType.OPEN_AI_WHISPER_API]
        assert widget.currentData() == ModelType.OPEN_AI_WHISPER_API
