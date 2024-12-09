from PyQt6 import QtWidgets


class LoginDialog(QtWidgets.QDialog):
    """
    Dialog to get a username and password. Completer optional for username.
    """

    class LoginForm(QtWidgets.QWidget):
        """
        Login form widget.
        """

        def __init__(self, parent=None, completer=None):
            super().__init__(parent)

            self._username_line_edit = QtWidgets.QLineEdit()
            if completer is not None:
                self._username_line_edit.setCompleter(completer)

            self._password_line_edit = QtWidgets.QLineEdit()
            self._password_line_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

            self._arrange()

        def _arrange(self):
            layout = QtWidgets.QFormLayout()

            layout.addRow("Username:", self._username_line_edit)
            layout.addRow("Password:", self._password_line_edit)

            self.setLayout(layout)

        @property
        def credentials(self):
            return self._username_line_edit.text(), self._password_line_edit.text()

    def __init__(self, parent=None, completer=None):
        super().__init__(parent)

        self.setWindowTitle("Login")

        self._login_form = LoginDialog.LoginForm(self, completer)

        self._dialog_buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self._dialog_buttons.accepted.connect(self.accept)
        self._dialog_buttons.rejected.connect(self.reject)
        self._dialog_buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        ).setText("Login")

        self._arrange()

    def _arrange(self):
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(self._login_form)
        layout.addWidget(self._dialog_buttons)

        self.setLayout(layout)

    @property
    def credentials(self):
        return self._login_form.credentials
