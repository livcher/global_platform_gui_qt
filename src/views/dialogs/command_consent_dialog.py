"""
Command Consent Dialog

Shown when a plugin attempts to execute external commands for the first time.
"""

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPlainTextEdit,
    QCheckBox,
    QDialogButtonBox,
    QWidget,
)
from PyQt5.QtCore import Qt

from src.utils.colors import Colors


class CommandConsentDialog(QDialog):
    """
    Consent dialog for plugin external command execution.

    Displays what command will run and asks the user for permission.
    Optionally remembers the choice for future executions.
    """

    def __init__(
        self,
        plugin_name: str,
        command_preview: str,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("External Command Execution")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        # Title
        title = QLabel(
            f"Plugin <b>{plugin_name}</b> wants to execute an external command"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        # Command preview
        cmd_label = QLabel("Command:")
        layout.addWidget(cmd_label)

        cmd_display = QPlainTextEdit()
        cmd_display.setPlainText(command_preview)
        cmd_display.setReadOnly(True)
        cmd_display.setMaximumHeight(80)
        layout.addWidget(cmd_display)

        # Warning
        warning = QLabel(
            "External commands have full access to your system. "
            "Only allow commands from plugins you trust."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            f"color: {Colors.alert_error_text()}; padding: 8px; "
            f"background: {Colors.alert_error_bg()}; border: 1px solid {Colors.alert_error_border()}; "
            f"border-radius: 4px;"
        )
        layout.addWidget(warning)

        # Remember checkbox
        self._remember_cb = QCheckBox("Remember my choice for this plugin")
        self._remember_cb.setChecked(True)
        layout.addWidget(self._remember_cb)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText("Allow")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def remember(self) -> bool:
        """Whether the user wants to remember this choice."""
        return self._remember_cb.isChecked()
