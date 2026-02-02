from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSlider, QHBoxLayout,
    QLineEdit
)
from PyQt6.QtCore import Qt

class ColorPicker(QWidget):
    def __init__(self):
        super().__init__()
        self.slidersLabels = []
        self.rgb = [0, 0, 0]
        self.initUI()

    def initUI(self):
        mainLayout = QVBoxLayout(self)

        title = QLabel("Color")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mainLayout.addWidget(title)

        slidersLayout = QVBoxLayout()
        for color in "RGB":
            slider, label = self.createSliderBox(color, 0, 255)
            slidersLayout.addWidget(label)
            slidersLayout.addWidget(slider)
            self.slidersLabels.append([slider, label])

        mainLayout.addLayout(slidersLayout)

        self.colorSquare = QLabel()
        self.colorSquare.setFixedSize(200, 20)
        self.colorSquare.setStyleSheet("background-color: rgb(0, 0, 0); border: 2px solid black;")
        mainLayout.addWidget(self.colorSquare, alignment=Qt.AlignmentFlag.AlignCenter)

        self.updateColor()

    #создание слайдера и лайна под цвет
    def createSliderBox(self, labelText, minVal, maxVal):
        container = QWidget()
        layout = QHBoxLayout(container)

        label = QLabel(f"{labelText}")
        label.setFixedWidth(20)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minVal, maxVal)
        slider.valueChanged.connect(self.updateColor)

        valueLabel = QLineEdit("0")
        valueLabel.setFixedWidth(50)
        valueLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        valueLabel.textChanged.connect(
            lambda text, s=slider: self.textChanged(text, s)
        )

        layout.addWidget(label)
        layout.addWidget(slider)
        layout.addWidget(valueLabel)
        layout.setContentsMargins(0, 0, 0, 0)

        return slider, container

    def textChanged(self, text, slider):
        try:
            value = int(text)
            if 0 <= value <= 255:
                slider.setValue(value)
        except ValueError:
            pass

    def updateColor(self):
        for i in range(3):
            self.rgb[i] = self.slidersLabels[i][0].value()

        self.colorSquare.setStyleSheet(
            f"background-color: rgb({self.rgb[0]}, {self.rgb[1]}, {self.rgb[2]}); "
            f"border: 2px solid black;"
        )

        for slider, labelWidget in self.slidersLabels:
            valueEdit = labelWidget.layout().itemAt(1).widget()
            valueEdit.setText(str(slider.value()))