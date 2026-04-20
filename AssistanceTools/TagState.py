from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


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
            f"background-color: rgb({self.tagType.color});border-radius: 10px;"
        )
        self.mainLayout.addWidget(self.circleState)

        name = QLabel(self.tagType.name)
        self.mainLayout.addWidget(name)

    def changeState(self, state):
        # state: bool — True → show tag-type color; False → black.
        if state:
            self.circleState.setStyleSheet(
                f"background-color: rgb({self.tagType.color});border-radius: 10px;"
            )
        else:
            self.circleState.setStyleSheet(
                "background-color: rgb(0, 0, 0);border-radius: 10px;"
            )
