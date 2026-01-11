import sys
from PyQt6.QtWidgets import QApplication
from MainScreen.MainScreen import MainWindow

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    sys.exit(main())