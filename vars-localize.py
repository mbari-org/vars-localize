import sys

from PyQt5.QtWidgets import QApplication
import qdarkstyle

from ui.AppWindow import AppWindow

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())

    window = AppWindow()
    window.show()

    exit_code = app.exec_()
    sys.exit(exit_code)
