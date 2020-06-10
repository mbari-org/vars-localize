from fbs_runtime.application_context.PyQt5 import ApplicationContext

import PyQt5.QtCore
import PyQt5.QtWidgets
import PyQt5.QtGui

import sys

import util.utils
from ui.AppWindow import AppWindow


if __name__ == '__main__':
    APP_CONTEXT = ApplicationContext()       # 1. Instantiate ApplicationContext
    util.utils.set_app_context(APP_CONTEXT)
    window = AppWindow(APP_CONTEXT)
    window.show()
    exit_code = APP_CONTEXT.app.exec_()      # 2. Invoke appctxt.app.exec_()
    sys.exit(exit_code)
