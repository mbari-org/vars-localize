from fbs_runtime.application_context.PyQt5 import ApplicationContext

import PyQt5.QtCore
import PyQt5.QtWidgets
import PyQt5.QtGui

import sys

import util.utils
from ui.AppWindow import AppWindow


if __name__ == '__main__':
    appctxt = ApplicationContext()       # 1. Instantiate ApplicationContext
    util.utils.set_appctxt(appctxt)
    window = AppWindow(appctxt)
    window.show()
    exit_code = appctxt.app.exec_()      # 2. Invoke appctxt.app.exec_()
    sys.exit(exit_code)
