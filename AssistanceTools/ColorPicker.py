from PyQt6.QtWidgets import *
from PyQt6.QtCore import *

class ColorPicker(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        mainLayout = QVBoxLayout()

        title = QLabel("Color")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mainLayout.addWidget(title)

        self.sliderR, self.labelR = self.createSliderBox("R", 0, 255)
        self.sliderG, self.labelG = self.createSliderBox("G", 0, 255)
        self.sliderB, self.labelB = self.createSliderBox("B", 0, 255)

        slidersLayout = QVBoxLayout()
        slidersLayout.addWidget(self.labelR)
        slidersLayout.addWidget(self.sliderR)
        slidersLayout.addWidget(self.labelG)
        slidersLayout.addWidget(self.sliderG)
        slidersLayout.addWidget(self.labelB)
        slidersLayout.addWidget(self.sliderB)
        mainLayout.addLayout(slidersLayout)

        self.colorSquare = QLabel()
        self.colorSquare.setFixedSize(200, 20)
        self.colorSquare.setStyleSheet("background-color: rgb(0, 0, 0); border: 2px solid black;")
        mainLayout.addWidget(self.colorSquare, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(mainLayout)
        self.updateColor()

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
        self.r = self.sliderR.value()
        self.g = self.sliderG.value()
        self.b = self.sliderB.value()

        self.colorSquare.setStyleSheet(
            f"background-color: rgb({self.r}, {self.g}, {self.b}); "
            f"border: 2px solid black;"
        )

        for slider, labelWidget in [
            (self.sliderR, self.labelR),
            (self.sliderG, self.labelG),
            (self.sliderB, self.labelB)
        ]:
            valueEdit = labelWidget.layout().itemAt(1).widget()
            valueEdit.setText(str(slider.value()))