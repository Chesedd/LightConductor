from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout

class TagState(QWidget):
    def __init__(self, tagType):
        super().__init__()
        self.tagType = tagType
        self.mainLayout = QVBoxLayout()
        self.setLayout(self.mainLayout)

        self.initUI()

    def initUI(self):
        self.circleState = QLabel()
        self.circleState.setFixedSize(20, 20)
        self.circleState.setStyleSheet(
            f"background-color: rgb({self.tagType.color});"
            "border-radius: 10px;"
        )
        self.mainLayout.addWidget(self.circleState)

        name = QLabel(self.tagType.name)
        self.mainLayout.addWidget(name)

    def changeState(self, state):
        if state == "On":
            self.circleState.setStyleSheet(
                f"background-color: rgb({self.tagType.color});"
                "border-radius: 10px;"
            )
        else:
            self.circleState.setStyleSheet(
                f"background-color: rgb(0, 0, 0);"
                "border-radius: 10px;"
            )
