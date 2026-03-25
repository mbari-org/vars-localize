from PyQt6 import QtWidgets

from vars_localize.services.M3Service import DEFAULT_M3_URL


class LoginDialog(QtWidgets.QDialog):
    """
    Dialog to get a username and password. Completer optional for username.
    """

    class LoginForm(QtWidgets.QWidget):
        """
        Login form widget.
        """

        def __init__(self, parent=None, completer=None, default_m3_url: str = ""):
            super().__init__(parent)

            self._m3_url_line_edit = QtWidgets.QLineEdit()
            self._m3_url_line_edit.setPlaceholderText(DEFAULT_M3_URL)
            self._m3_url_line_edit.setText(
                (default_m3_url or "").strip() or DEFAULT_M3_URL
            )

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
            layout.addRow("Config server:", self._m3_url_line_edit)

            self.setLayout(layout)

        @property
        def credentials(self):
            return (
                self._m3_url_line_edit.text().strip(),
                self._username_line_edit.text(),
                self._password_line_edit.text(),
            )

    def __init__(self, parent=None, completer=None, default_m3_url: str = ""):
        super().__init__(parent)

        self.setWindowTitle("Login")

        self._login_form = LoginDialog.LoginForm(
            self,
            completer,
            default_m3_url=default_m3_url,
        )

        self._error_label = QtWidgets.QLabel("")
        self._error_label.setObjectName("loginErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.hide()

        self._dialog_buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self._dialog_buttons.accepted.connect(self.accept)
        self._dialog_buttons.rejected.connect(self.reject)
        ok_button = self._dialog_buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
        )
        if ok_button is not None:
            ok_button.setText("Login")

        self._arrange()

        self.setMinimumWidth(400)

    def _arrange(self):
        layout = QtWidgets.QVBoxLayout()

        layout.addWidget(self._login_form)
        layout.addWidget(self._error_label)
        layout.addWidget(self._dialog_buttons)

        self.setLayout(layout)

    @property
    def credentials(self):
        return self._login_form.credentials

    def focus_username(self) -> None:
        self._login_form._username_line_edit.setFocus()

    def set_error(self, message: str) -> None:
        """Show an inline login error message in the dialog."""
        self._error_label.setText(message)
        self._error_label.show()

    def clear_error(self) -> None:
        """Hide any inline login error message."""
        self._error_label.clear()
        self._error_label.hide()
