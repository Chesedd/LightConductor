from PyQt6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QHBoxLayout, QVBoxLayout, QPushButton,
    QWidget, QComboBox)

from AssistanceTools.ColorPicker import ColorPicker
from lightconductor.application.pattern_service import PatternService

_pattern_service = PatternService()


class TagGroupPatternDialog(QDialog):
    def __init__(self, led_count, parent=None):
        super().__init__(parent)
        self.led_count = led_count
        self.setWindowTitle("Tag group patterns")
        self.mainLayout = QVBoxLayout(self)
        self.initUI()

    def initUI(self):
        patternRow = QWidget()
        patternLayout = QHBoxLayout(patternRow)
        patternLayout.addWidget(QLabel("Pattern"))
        self.patternBar = QComboBox()
        self.patternBar.addItems([
            "Sequential fill",
            "Floating gradient",
            "Moving window",
        ])
        self.patternBar.currentTextChanged.connect(self.onPatternChanged)
        patternLayout.addWidget(self.patternBar)
        self.mainLayout.addWidget(patternRow)

        timingRow = QWidget()
        timingLayout = QHBoxLayout(timingRow)
        timingLayout.addWidget(QLabel("Start"))
        self.startTimeBar = QLineEdit("0.0")
        self.startTimeBar.setFixedWidth(60)
        timingLayout.addWidget(self.startTimeBar)
        timingLayout.addWidget(QLabel("End"))
        self.endTimeBar = QLineEdit("5.0")
        self.endTimeBar.setFixedWidth(60)
        timingLayout.addWidget(self.endTimeBar)
        timingLayout.addWidget(QLabel("Step"))
        self.stepBar = QLineEdit("0.2")
        self.stepBar.setFixedWidth(60)
        timingLayout.addWidget(self.stepBar)
        self.mainLayout.addWidget(timingRow)

        extraRow = QWidget()
        extraLayout = QHBoxLayout(extraRow)
        extraLayout.addWidget(QLabel("Window LEDs"))
        self.windowSizeBar = QLineEdit("3")
        self.windowSizeBar.setFixedWidth(60)
        extraLayout.addWidget(self.windowSizeBar)
        extraLayout.addWidget(QLabel("Gradient width"))
        self.gradientWidthBar = QLineEdit("4")
        self.gradientWidthBar.setFixedWidth(60)
        extraLayout.addWidget(self.gradientWidthBar)
        self.mainLayout.addWidget(extraRow)

        self.colorPicker = ColorPicker()
        self.mainLayout.addWidget(self.colorPicker)

        buttons = QWidget()
        buttonsLayout = QHBoxLayout(buttons)
        okButton = QPushButton("Create")
        okButton.clicked.connect(self.accept)
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttonsLayout.addWidget(okButton)
        buttonsLayout.addWidget(cancelButton)
        self.mainLayout.addWidget(buttons)
        self.onPatternChanged(self.patternBar.currentText())

    def onPatternChanged(self, pattern_name):
        self.windowSizeBar.setEnabled(pattern_name == "Moving window")
        self.gradientWidthBar.setEnabled(pattern_name == "Floating gradient")

    def _parse_float(self, line_edit, default):
        try:
            return float(line_edit.text())
        except ValueError:
            return default

    def _parse_int(self, line_edit, default):
        try:
            return int(line_edit.text())
        except ValueError:
            return default

    def buildTags(self):
        rgb = [self.colorPicker.rgb[0], self.colorPicker.rgb[1], self.colorPicker.rgb[2]]
        start_time = self._parse_float(self.startTimeBar, 0.0)
        end_time = self._parse_float(self.endTimeBar, start_time)
        step = self._parse_float(self.stepBar, 0.2)
        pattern_name = self.patternBar.currentText()

        if pattern_name == "Sequential fill":
            frames = _pattern_service.sequential_fill(self.led_count, rgb)
        elif pattern_name == "Floating gradient":
            width = self._parse_int(self.gradientWidthBar, 4)
            frames = _pattern_service.floating_gradient(
                self.led_count, rgb, width,
            )
        else:
            window = self._parse_int(self.windowSizeBar, 3)
            frames = _pattern_service.moving_window(
                self.led_count, window, rgb,
            )

        return _pattern_service.build_tags(
            frames=frames,
            start_time=start_time,
            end_time=end_time,
            step=step,
        )
