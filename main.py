import logging
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

SRC_PATH = Path(__file__).resolve().parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from lightconductor.infrastructure.logging_setup import configure_logging
from MainScreen.MainScreen import MainWindow

APP_STYLESHEET = """
QWidget {
    background-color: #121417;
    color: #e6e6e6;
    font-size: 13px;
}
QMainWindow {
    background-color: #121417;
}
QPushButton {
    background-color: #1e2329;
    border: 1px solid #2e353d;
    border-radius: 8px;
    padding: 8px 12px;
}
QPushButton:hover {
    background-color: #252c34;
    border: 1px solid #3a444f;
}
QPushButton:pressed {
    background-color: #2f3944;
}
QPushButton:disabled {
    color: #7a8189;
    background-color: #171b20;
    border: 1px solid #242b33;
}
QLineEdit, QComboBox, QSpinBox {
    background-color: #1a1f25;
    border: 1px solid #2e353d;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #3b82f6;
}
QScrollArea {
    border: none;
}
QGroupBox {
    border: 1px solid #2e353d;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QMenu {
    background-color: #1a1f25;
    border: 1px solid #2e353d;
}
QMenu::item:selected {
    background-color: #2a323b;
}
"""


def main():
    configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("LightConductor starting")
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    sys.exit(main())
