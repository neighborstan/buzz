from typing import Optional, List

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QWidget

from buzz.model_loader import ModelType


MODEL_TYPE_DISPLAY_LABELS = {
    ModelType.OPEN_AI_WHISPER_API: "OpenAI API",
}


def model_type_display_text(model_type: ModelType) -> str:
    return MODEL_TYPE_DISPLAY_LABELS.get(model_type, model_type.value)


class ModelTypeComboBox(QComboBox):
    changed = pyqtSignal(ModelType)

    def __init__(
        self,
        model_types: Optional[List[ModelType]] = None,
        default_model: Optional[ModelType] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        if model_types is None:
            model_types = [
                model_type for model_type in ModelType if model_type.is_available()
            ]

        for model_type in model_types:
            self.addItem(model_type_display_text(model_type), model_type)

        self.currentIndexChanged.connect(self.on_index_changed)
        if default_model is not None:
            index = self.findData(default_model)
            if index != -1:
                self.setCurrentIndex(index)

    def on_index_changed(self, index: int):
        model_type = self.itemData(index)
        if model_type is not None:
            self.changed.emit(model_type)
