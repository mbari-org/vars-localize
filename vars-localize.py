import sys

from PyQt5.QtWidgets import QApplication

from ui.AppWindow import AppWindow

if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = AppWindow()
    window.show()

    exit_code = app.exec_()
    sys.exit(exit_code)
