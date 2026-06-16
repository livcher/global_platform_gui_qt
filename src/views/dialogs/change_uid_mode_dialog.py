"""
ChangeUidModeDialog - View/change the NXP UID configuration of an implant.

Reads the five config tags (10A1-10A5: ATQA1/ATQA2/SAK/Cascade SAK/UID) over
a GlobalPlatform secure channel, shows each label, value and its meaning, and
offers one-click buttons to switch between the named UID modes. The mode the
card is already in is disabled. Changes apply immediately and the config is
re-read afterwards to refresh the displayed values.

Card I/O is injected as callbacks so the dialog stays decoupled from the
NFC thread:
    read_config()            -> Optional[Dict[str, int]]
    apply_mode(key, config)  -> bool
"""

from typing import Callable, Dict, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...services import uid_mode
from ...utils.colors import Colors


class ChangeUidModeDialog(QDialog):
    """Dialog to inspect and change the UID mode of an NXP implant."""

    def __init__(
        self,
        read_config: Callable[[], Optional[Dict[str, int]]],
        apply_mode: Callable[[str, Dict[str, int]], bool],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Change UID Mode")
        self.setModal(True)
        self.setMinimumWidth(460)

        self._read_config = read_config
        self._apply_mode = apply_mode
        self._config: Dict[str, int] = {}

        self._value_labels: Dict[str, QLabel] = {}
        self._meaning_labels: Dict[str, QLabel] = {}
        self._mode_buttons: Dict[str, QPushButton] = {}

        self._build_ui()
        self._refresh()

    # -- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "Current chip configuration (tags 10A1-10A5). Pick a mode below "
            "to reconfigure the UID; the current mode is disabled."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {Colors.muted_text()};")
        layout.addWidget(intro)

        # Summary of the matched mode.
        self._summary_label = QLabel()
        self._summary_label.setStyleSheet(
            f"background-color: {Colors.info_bg()};"
            f" color: {Colors.primary_text()};"
            " border-radius: 4px; padding: 6px 8px; font-weight: bold;"
        )
        layout.addWidget(self._summary_label)

        # Config table.
        group = QGroupBox("Tag Configuration")
        grid = QGridLayout(group)
        grid.setColumnStretch(2, 1)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)

        for col, title in enumerate(("Tag", "Value", "Meaning")):
            header = QLabel(title)
            header.setStyleSheet(
                f"color: {Colors.secondary_text()}; font-weight: bold;"
            )
            grid.addWidget(header, 0, col)

        for row, tag in enumerate(uid_mode.TAG_ORDER, start=1):
            name = QLabel(f"{tag} · {uid_mode.TAG_LABELS[tag]}")
            name.setStyleSheet(f"color: {Colors.primary_text()};")

            value = QLabel("—")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value.setStyleSheet(
                f"color: {Colors.primary_text()}; font-family: monospace;"
            )

            meaning = QLabel("")
            meaning.setWordWrap(True)
            meaning.setStyleSheet(f"color: {Colors.muted_text()};")

            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            grid.addWidget(meaning, row, 2)

            self._value_labels[tag] = value
            self._meaning_labels[tag] = meaning

        layout.addWidget(group)

        # Mode buttons.
        modes_label = QLabel("Set mode:")
        modes_label.setStyleSheet(f"color: {Colors.secondary_text()};")
        layout.addWidget(modes_label)

        buttons_row = QHBoxLayout()
        for mode in uid_mode.MODES:
            btn = QPushButton(mode.label)
            btn.clicked.connect(
                lambda _checked, key=mode.key: self._on_mode_clicked(key)
            )
            self._mode_buttons[mode.key] = btn
            buttons_row.addWidget(btn)
        layout.addLayout(buttons_row)

        # Status line.
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Separator + close.
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: {Colors.muted_text()};")
        layout.addWidget(line)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

    # -- Behaviour ----------------------------------------------------------

    def _refresh(self) -> None:
        """Re-read the card config and update the table, summary and buttons."""
        config = self._read_config()

        if not config:
            self._config = {}
            self._summary_label.setText("Could not read chip configuration")
            for tag in uid_mode.TAG_ORDER:
                self._value_labels[tag].setText("—")
                self._meaning_labels[tag].setText("")
            for btn in self._mode_buttons.values():
                btn.setEnabled(False)
            self._set_status(
                "Reading the chip failed. Make sure the implant is still on "
                "the reader, then reopen this dialog.",
                error=True,
            )
            return

        self._config = config
        self._summary_label.setText(
            f"Current mode: {uid_mode.summarize_mode(config)}"
        )

        for tag in uid_mode.TAG_ORDER:
            if tag in config:
                value = config[tag]
                self._value_labels[tag].setText(f"0x{value:02X}")
                self._meaning_labels[tag].setText(
                    uid_mode.describe_value(tag, value)
                )
            else:
                self._value_labels[tag].setText("(unreadable)")
                self._meaning_labels[tag].setText("")

        disabled = uid_mode.disabled_mode_keys(config)
        for key, btn in self._mode_buttons.items():
            btn.setEnabled(key not in disabled)

    def _on_mode_clicked(self, mode_key: str) -> None:
        label = uid_mode.MODES_BY_KEY[mode_key].label
        self._set_status(f"Applying “{label}”…")
        self.setEnabled(False)
        QApplication.processEvents()

        try:
            ok = self._apply_mode(mode_key, dict(self._config))
        finally:
            self.setEnabled(True)

        if ok:
            self._set_status(f"Applied “{label}”. Refreshed below.")
        else:
            self._set_status(
                f"Failed to apply “{label}”. The chip may be locked or use a "
                "different key.",
                error=True,
            )

        # Re-read regardless so the table reflects the true current state.
        self._refresh()

    def _set_status(self, text: str, error: bool = False) -> None:
        color = Colors.warning_text() if error else Colors.muted_text()
        self._status_label.setStyleSheet(f"color: {color};")
        self._status_label.setText(text)
