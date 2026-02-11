"""
Parameters Encoding Page

Wizard page for configuring how form field values are encoded into
installation parameters (the --params hex string for gp --install).

Supports three encoding modes:
- Template: String substitution with {field_id} variables
- TLV: Tag-Length-Value structure building
- Custom: Python builder script
"""

import copy
import re
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QCheckBox,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
    QMenu,
    QWidget,
    QSplitter,
)

from ....utils.colors import Colors


# ============================================================================
# TLV Entry Dialog
# ============================================================================

class TLVEntryDialog(QDialog):
    """Dialog for adding/editing a single TLV entry."""

    def __init__(self, entry_data: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TLV Entry")
        self.setMinimumWidth(400)

        self._entry_data = entry_data or {}
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QFormLayout(self)

        # Tag
        self._tag_edit = QLineEdit()
        self._tag_edit.setPlaceholderText("e.g. 80, 9F33")
        self._tag_edit.setMaxLength(8)
        layout.addRow("Tag (hex):", self._tag_edit)

        # Value template
        self._value_edit = QLineEdit()
        self._value_edit.setPlaceholderText("e.g. {read_perm}{write_perm}")
        layout.addRow("Value template:", self._value_edit)

        # Length bytes
        self._length_combo = QComboBox()
        self._length_combo.addItem("1 byte", 1)
        self._length_combo.addItem("2 bytes", 2)
        layout.addRow("Length field size:", self._length_combo)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _load_data(self):
        if self._entry_data:
            self._tag_edit.setText(self._entry_data.get("tag", ""))
            self._value_edit.setText(self._entry_data.get("value", ""))
            length_bytes = self._entry_data.get("length_bytes", 1)
            idx = self._length_combo.findData(length_bytes)
            if idx >= 0:
                self._length_combo.setCurrentIndex(idx)

    def _validate_and_accept(self):
        tag = self._tag_edit.text().strip().upper()
        if not tag or not re.match(r'^[0-9A-F]+$', tag):
            self._tag_edit.setFocus()
            return
        if len(tag) % 2 != 0:
            self._tag_edit.setFocus()
            return
        if not self._value_edit.text().strip():
            self._value_edit.setFocus()
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "tag": self._tag_edit.text().strip().upper(),
            "value": self._value_edit.text().strip(),
            "length_bytes": self._length_combo.currentData(),
        }


# ============================================================================
# Available Fields Helper Widget
# ============================================================================

class FieldsAssistWidget(QWidget):
    """
    Shows available field IDs from the UI Builder page and lets users
    insert template variable references at the cursor.
    """

    # Suffix options for the insert menu
    SUFFIXES = [
        ("", "Raw value", "{{{id}}}"),
        ("_hex", "Hex-encode text", "{{{id}_hex}}"),
        ("_ascii_hex", "ASCII to hex", "{{{id}_ascii_hex}}"),
        ("_length:02X", "Byte length (hex)", "{{{id}_length:02X}}"),
        ("_ascii_length:02X", "Char length (hex)", "{{{id}_ascii_length:02X}}"),
    ]

    def __init__(self, insert_callback, parent=None):
        """
        Args:
            insert_callback: Called with the text to insert, e.g. "{pin_hex}"
        """
        super().__init__(parent)
        self._insert_callback = insert_callback
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Fields table
        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Field", "Type", ""])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.verticalHeader().hide()
        self._table.setSelectionMode(QTableWidget.NoSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setMaximumHeight(150)
        layout.addWidget(self._table)

        # Quick reference
        ref_text = (
            "<b>Quick Reference:</b> "
            "<code>{a+b_length:02X}</code> = combined byte length | "
            "<code>{?field}...{/field}</code> = conditional section"
        )
        ref_label = QLabel(ref_text)
        ref_label.setWordWrap(True)
        ref_label.setStyleSheet(f"color: {Colors.muted_text()}; font-size: 11px; padding: 4px;")
        layout.addWidget(ref_label)

    def update_fields(self, fields: list[dict]):
        """Update the table with field definitions from the UI Builder page."""
        self._table.setRowCount(len(fields))
        for row, field_def in enumerate(fields):
            field_id = field_def.get("id", "")
            field_type = field_def.get("type", "text")

            id_item = QTableWidgetItem(field_id)
            self._table.setItem(row, 0, id_item)

            type_item = QTableWidgetItem(field_type)
            self._table.setItem(row, 1, type_item)

            insert_btn = QPushButton("Insert...")
            insert_btn.setMaximumWidth(80)
            insert_btn.clicked.connect(
                lambda checked, fid=field_id: self._show_insert_menu(fid)
            )
            self._table.setCellWidget(row, 2, insert_btn)

    def _show_insert_menu(self, field_id: str):
        """Show a dropdown menu with suffix options for the given field."""
        menu = QMenu(self)
        for suffix, description, template in self.SUFFIXES:
            text = template.format(id=field_id)
            action = menu.addAction(f"{text}  ({description})")
            action.triggered.connect(
                lambda checked, t=text: self._insert_callback(t)
            )
        # Position near the button
        btn = self.sender()
        if btn:
            menu.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))
        else:
            menu.exec_()


# ============================================================================
# Parameters Page
# ============================================================================

class ParametersPage(QWizardPage):
    """
    Wizard page for configuring installation parameter encoding.

    Placed after the UI Builder page, this page defines how form field
    values are transformed into the hex --params string for gp --install.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Installation Parameters")
        self.setSubTitle(
            "Define how form field values are encoded into "
            "installation parameters for the applet."
        )

        self._tlv_entries: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Skip checkbox
        self._skip_cb = QCheckBox("Skip (no installation parameters needed)")
        self._skip_cb.setChecked(True)
        self._skip_cb.toggled.connect(self._on_skip_toggled)
        layout.addWidget(self._skip_cb)

        # Main content area (disabled when skip is checked)
        self._content_widget = QWidget()
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(0, 8, 0, 0)

        # Encoding type selector
        type_group = QGroupBox("Encoding Type")
        type_layout = QHBoxLayout(type_group)

        self._encoding_group = QButtonGroup(self)
        self._template_radio = QRadioButton("Template")
        self._tlv_radio = QRadioButton("TLV Structure")
        self._custom_radio = QRadioButton("Custom Script")

        self._template_radio.setChecked(True)

        self._encoding_group.addButton(self._template_radio, 0)
        self._encoding_group.addButton(self._tlv_radio, 1)
        self._encoding_group.addButton(self._custom_radio, 2)

        type_layout.addWidget(self._template_radio)
        type_layout.addWidget(self._tlv_radio)
        type_layout.addWidget(self._custom_radio)
        type_layout.addStretch()

        content_layout.addWidget(type_group)

        # Create AID
        aid_layout = QHBoxLayout()
        aid_layout.addWidget(QLabel("Create AID (optional):"))
        self._create_aid_edit = QLineEdit()
        self._create_aid_edit.setPlaceholderText("e.g. D2760000850101")
        self._create_aid_edit.setMaximumWidth(300)
        aid_layout.addWidget(self._create_aid_edit)
        aid_hint = QLabel("AID for --create flag")
        aid_hint.setStyleSheet(f"color: {Colors.muted_text()};")
        aid_layout.addWidget(aid_hint)
        aid_layout.addStretch()
        content_layout.addLayout(aid_layout)

        # Stacked widget for encoding-specific content
        self._content_stack = QStackedWidget()

        # -- Template page (index 0) --
        self._content_stack.addWidget(self._build_template_page())

        # -- TLV page (index 1) --
        self._content_stack.addWidget(self._build_tlv_page())

        # -- Custom page (index 2) --
        self._content_stack.addWidget(self._build_custom_page())

        content_layout.addWidget(self._content_stack, 1)

        layout.addWidget(self._content_widget)

        # Connect encoding type change
        self._encoding_group.buttonClicked.connect(self._on_encoding_changed)

        # Initial state: skip checked → content hidden
        self._content_widget.setVisible(False)

    # ---- Template page ----

    def _build_template_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 0)

        # Header with visual assist toggle
        header = QHBoxLayout()
        header.addWidget(QLabel("Template String:"))
        header.addStretch()
        self._visual_assist_cb = QCheckBox("Visual Assist")
        self._visual_assist_cb.setChecked(True)
        self._visual_assist_cb.toggled.connect(self._on_visual_assist_toggled)
        header.addWidget(self._visual_assist_cb)
        layout.addLayout(header)

        # Template editor
        self._template_edit = QTextEdit()
        self._template_edit.setFont(QFont("Consolas, Monaco, monospace", 10))
        self._template_edit.setPlaceholderText(
            "Enter template with {field_id} placeholders.\n\n"
            "Example:\n"
            "  {container_size} 8102 {read_perm}{write_perm}\n\n"
            "Use suffixes for encoding:\n"
            "  {pin_hex}           - hex-encode text\n"
            "  {pin_ascii_hex}     - ASCII to hex\n"
            "  {data_length:02X}   - byte length as hex"
        )
        self._template_edit.setMaximumHeight(120)
        layout.addWidget(self._template_edit)

        # Visual assist area (fields table + reference)
        self._template_assist = FieldsAssistWidget(
            insert_callback=self._insert_template_text
        )
        layout.addWidget(self._template_assist)

        layout.addStretch()
        return widget

    def _insert_template_text(self, text: str):
        """Insert text at cursor in template editor."""
        cursor = self._template_edit.textCursor()
        cursor.insertText(text)
        self._template_edit.setFocus()

    # ---- TLV page ----

    def _build_tlv_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 0)

        layout.addWidget(QLabel("TLV Entries:"))

        # Splitter: list on top, fields assist below
        splitter = QSplitter(Qt.Vertical)

        # TLV list
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)

        self._tlv_list = QListWidget()
        list_layout.addWidget(self._tlv_list)

        # Buttons
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._tlv_add)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._tlv_edit)
        btn_layout.addWidget(edit_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._tlv_remove)
        btn_layout.addWidget(remove_btn)

        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._tlv_move_up)
        btn_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._tlv_move_down)
        btn_layout.addWidget(move_down_btn)

        btn_layout.addStretch()
        list_layout.addLayout(btn_layout)

        splitter.addWidget(list_widget)

        # Fields assist for TLV value templates
        self._tlv_assist = FieldsAssistWidget(
            insert_callback=self._insert_tlv_reference
        )
        splitter.addWidget(self._tlv_assist)

        layout.addWidget(splitter, 1)
        return widget

    def _insert_tlv_reference(self, text: str):
        """Copy reference text to clipboard for pasting into TLV value field."""
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        # Show tooltip near the fields table
        from PyQt5.QtWidgets import QToolTip
        from PyQt5.QtGui import QCursor
        QToolTip.showText(QCursor.pos(), f"Copied: {text}")

    def _tlv_add(self):
        dlg = TLVEntryDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            entry = dlg.get_data()
            self._tlv_entries.append(entry)
            self._refresh_tlv_list()

    def _tlv_edit(self):
        row = self._tlv_list.currentRow()
        if row < 0 or row >= len(self._tlv_entries):
            return
        dlg = TLVEntryDialog(entry_data=self._tlv_entries[row], parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._tlv_entries[row] = dlg.get_data()
            self._refresh_tlv_list()

    def _tlv_remove(self):
        row = self._tlv_list.currentRow()
        if row < 0 or row >= len(self._tlv_entries):
            return
        self._tlv_entries.pop(row)
        self._refresh_tlv_list()

    def _tlv_move_up(self):
        row = self._tlv_list.currentRow()
        if row <= 0 or row >= len(self._tlv_entries):
            return
        self._tlv_entries[row], self._tlv_entries[row - 1] = (
            self._tlv_entries[row - 1], self._tlv_entries[row]
        )
        self._refresh_tlv_list()
        self._tlv_list.setCurrentRow(row - 1)

    def _tlv_move_down(self):
        row = self._tlv_list.currentRow()
        if row < 0 or row >= len(self._tlv_entries) - 1:
            return
        self._tlv_entries[row], self._tlv_entries[row + 1] = (
            self._tlv_entries[row + 1], self._tlv_entries[row]
        )
        self._refresh_tlv_list()
        self._tlv_list.setCurrentRow(row + 1)

    def _refresh_tlv_list(self):
        self._tlv_list.clear()
        for entry in self._tlv_entries:
            tag = entry.get("tag", "??")
            value = entry.get("value", "")
            length = entry.get("length_bytes", 1)
            label = f"Tag {tag}: {value}"
            if length == 2:
                label += "  (2-byte length)"
            self._tlv_list.addItem(label)

    # ---- Custom page ----

    def _build_custom_page(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 0)

        # Python script editor (reuse existing widget)
        from .python_editor import PythonScriptEditor
        self._script_editor = PythonScriptEditor()
        # Override placeholder for parameter builder context
        editor_widget = self._script_editor.findChild(QTextEdit)
        if editor_widget:
            editor_widget.setPlaceholderText(
                "# Access field values:\n"
                "#   value = field_values.get('field_id', '')\n"
                "#   value = field_values['field_id']\n"
                "#\n"
                "# Set the result to the final hex param string:\n"
                "#   result = '8102' + read_perm + write_perm\n"
                "#\n"
                "# Example:\n"
                "container = field_values.get('container_size', '1000')\n"
                "read_perm = field_values.get('read_perm', '00')\n"
                "write_perm = field_values.get('write_perm', '00')\n"
                "result = f'8102{read_perm}{write_perm}8202{container}'"
            )
        layout.addWidget(self._script_editor, 1)

        # API reference
        api_ref = QLabel(
            "<b>API Reference:</b><br>"
            "<code>field_values</code> — dict of field_id to user input value<br>"
            "<code>result</code> — set this to the final hex parameter string<br>"
            "<b>Available:</b> len, str, int, hex, bytes, bytearray, "
            "range, enumerate, format, list, dict<br>"
            "<b>Restricted:</b> No imports, no file I/O, no network (sandboxed)"
        )
        api_ref.setWordWrap(True)
        api_ref.setStyleSheet(
            f"background-color: {Colors.light_bg()}; "
            f"padding: 8px; border-radius: 4px; font-size: 11px;"
        )
        layout.addWidget(api_ref)

        return widget

    # ---- Event handlers ----

    def _on_skip_toggled(self, checked: bool):
        self._content_widget.setVisible(not checked)

    def _on_encoding_changed(self, button):
        idx = self._encoding_group.id(button)
        self._content_stack.setCurrentIndex(idx)

    def _on_visual_assist_toggled(self, checked: bool):
        self._template_assist.setVisible(checked)

    # ---- Data flow ----

    def _get_install_fields(self) -> list[dict]:
        """Get field definitions from the UI Builder page data."""
        wizard = self.wizard()
        if not wizard:
            return []
        fields = []
        # Check form fields (flat form)
        form_fields = wizard.get_plugin_value("install_ui.form.fields", [])
        if form_fields:
            fields.extend(form_fields)
        # Check tabbed dialog fields
        tabs = wizard.get_plugin_value("install_ui.dialog.tabs", [])
        if tabs:
            for tab in tabs:
                if isinstance(tab, dict):
                    fields.extend(tab.get("fields", []))
        return fields

    def initializePage(self):
        """Load existing parameter data and populate fields."""
        wizard = self.wizard()
        if not wizard:
            return

        # Populate field assist tables
        install_fields = self._get_install_fields()
        self._template_assist.update_fields(install_fields)
        self._tlv_assist.update_fields(install_fields)

        # Load existing parameters data
        params = wizard.get_plugin_value("parameters")
        if not params or not isinstance(params, dict):
            self._skip_cb.setChecked(True)
            return

        encoding = params.get("encoding", "none")
        if encoding == "none" or not encoding:
            self._skip_cb.setChecked(True)
            return

        # Has parameters — uncheck skip
        self._skip_cb.setChecked(False)

        # Set create AID
        create_aid = params.get("create_aid", "")
        self._create_aid_edit.setText(create_aid or "")

        # Set encoding type and populate
        if encoding == "template":
            self._template_radio.setChecked(True)
            self._content_stack.setCurrentIndex(0)
            template_str = params.get("template", "")
            self._template_edit.setPlainText(template_str or "")

        elif encoding == "tlv":
            self._tlv_radio.setChecked(True)
            self._content_stack.setCurrentIndex(1)
            self._tlv_entries = copy.deepcopy(params.get("tlv_structure", []))
            self._refresh_tlv_list()

        elif encoding == "custom":
            self._custom_radio.setChecked(True)
            self._content_stack.setCurrentIndex(2)
            builder = params.get("builder", "")
            self._script_editor.set_text(builder or "")

    def validatePage(self) -> bool:
        """Save parameter configuration to wizard data."""
        wizard = self.wizard()
        if not wizard:
            return True

        if self._skip_cb.isChecked():
            wizard.set_plugin_data("parameters", None)
            return True

        # Get create AID (strip whitespace, validate if provided)
        create_aid = self._create_aid_edit.text().strip().upper().replace(" ", "")
        if create_aid and not re.match(r'^[0-9A-F]+$', create_aid):
            self._create_aid_edit.setFocus()
            return False
        create_aid_val = create_aid if create_aid else None

        # Build parameters dict based on encoding type
        if self._template_radio.isChecked():
            template_text = self._template_edit.toPlainText().strip()
            params = {
                "encoding": "template",
                "template": template_text,
            }
            if create_aid_val:
                params["create_aid"] = create_aid_val

        elif self._tlv_radio.isChecked():
            params = {
                "encoding": "tlv",
                "tlv_structure": copy.deepcopy(self._tlv_entries),
            }
            if create_aid_val:
                params["create_aid"] = create_aid_val

        elif self._custom_radio.isChecked():
            script_text = self._script_editor.get_text().strip()
            params = {
                "encoding": "custom",
                "builder": script_text,
            }
            if create_aid_val:
                params["create_aid"] = create_aid_val

        else:
            params = None

        wizard.set_plugin_data("parameters", params)
        return True
