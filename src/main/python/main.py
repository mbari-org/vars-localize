from fbs_runtime.application_context.PyQt5 import ApplicationContext

import PyQt5.QtCore
import PyQt5.QtWidgets
import PyQt5.QtGui

import sys
from ui.AppWindow import AppWindow


def create_window() -> AppWindow:
    window = AppWindow()
    icon = PyQt5.QtGui.QIcon('logo.png')
    window.setWindowIcon(icon)
    return window


if __name__ == '__main__':
    appctxt = ApplicationContext()       # 1. Instantiate ApplicationContext
    window = create_window()
    window.show()
    exit_code = appctxt.app.exec_()      # 2. Invoke appctxt.app.exec_()
    sys.exit(exit_code)
