import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication


SRC_PATH = Path(__file__).resolve().parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from MainScreen.MainScreen import MainWindow


def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    sys.exit(main())
