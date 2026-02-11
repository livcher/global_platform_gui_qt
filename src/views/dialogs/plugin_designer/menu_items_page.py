"""
Menu Items Page

Allows creating plugin menu bar items through a visual interface.
Menu items appear in the Plugins menu and can trigger workflows, APDUs, commands, or scripts.
"""

import re
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QComboBox,
    QCheckBox,
    QStackedWidget,
    QWidget,
    QMessageBox,
)


class MenuItemDefinitionDialog(QDialog):
    """Dialog for defining a single menu item."""

    ACTION_TYPES = [
        ("Workflow", "workflow"),
        ("APDU Sequence", "apdu_sequence"),
        ("Command", "command"),
        ("Script", "script"),
    ]

    def __init__(
        self,
        item_data: Optional[dict] = None,
        available_workflows: Optional[list[str]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Menu Item Definition")
        self.setMinimumSize(500, 450)

        self._item_data = item_data or {}
        self._available_workflows = available_workflows or []
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Basic info
        form = QFormLayout()

        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("e.g., reset_pin")
        form.addRow("ID:", self._id_edit)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("e.g., Reset PIN")
        self._label_edit.textChanged.connect(self._auto_generate_id)
        form.addRow("Label:", self._label_edit)

        layout.addLayout(form)

        # Card requirements
        self._requires_card_cb = QCheckBox("Requires card connection")
        self._requires_card_cb.setChecked(True)
        self._requires_card_cb.stateChanged.connect(self._on_requires_card_changed)
        layout.addWidget(self._requires_card_cb)

        self._requires_applet_cb = QCheckBox("Requires applet on card")
        self._requires_applet_cb.setChecked(True)
        layout.addWidget(self._requires_applet_cb)

        # Action type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Action Type:"))
        self._type_combo = QComboBox()
        for display, _ in self.ACTION_TYPES:
            self._type_combo.addItem(display)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self._type_combo)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # Stacked widget for type-specific config
        self._config_stack = QStackedWidget()

        # Workflow config (index 0)
        workflow_widget = QWidget()
        wf_layout = QVBoxLayout(workflow_widget)
        wf_form = QFormLayout()
        self._workflow_combo = QComboBox()
        self._workflow_combo.setEditable(True)
        self._workflow_combo.setPlaceholderText("Enter or select workflow name")
        wf_form.addRow("Workflow:", self._workflow_combo)
        wf_layout.addLayout(wf_form)
        wf_layout.addStretch()
        self._config_stack.addWidget(workflow_widget)

        # APDU Sequence config (index 1)
        apdu_widget = QWidget()
        apdu_layout = QVBoxLayout(apdu_widget)
        apdu_layout.addWidget(QLabel("APDU Commands:"))
        self._apdu_list = QListWidget()
        apdu_layout.addWidget(self._apdu_list)
        apdu_btn_layout = QHBoxLayout()
        apdu_add_btn = QPushButton("Add APDU")
        apdu_add_btn.clicked.connect(self._add_apdu)
        apdu_btn_layout.addWidget(apdu_add_btn)
        apdu_remove_btn = QPushButton("Remove")
        apdu_remove_btn.clicked.connect(self._remove_apdu)
        apdu_btn_layout.addWidget(apdu_remove_btn)
        apdu_btn_layout.addStretch()
        apdu_layout.addLayout(apdu_btn_layout)
        self._config_stack.addWidget(apdu_widget)

        # Command config (index 2)
        cmd_widget = QWidget()
        cmd_layout = QVBoxLayout(cmd_widget)
        cmd_form = QFormLayout()
        self._command_edit = QLineEdit()
        self._command_edit.setPlaceholderText("e.g., gpg --export --armor")
        cmd_form.addRow("Command:", self._command_edit)
        cmd_layout.addLayout(cmd_form)
        cmd_layout.addWidget(QLabel(
            "Command will be split on spaces. "
            "User will be asked for consent before execution."
        ))
        cmd_layout.addStretch()
        self._config_stack.addWidget(cmd_widget)

        # Script config (index 3)
        script_widget = QWidget()
        script_layout = QVBoxLayout(script_widget)
        script_layout.addWidget(QLabel("Python Script:"))
        self._script_edit = QPlainTextEdit()
        self._script_edit.setPlaceholderText(
            "# Python snippet\n"
            "# Available: parameters dict\n"
            "# Set result = value to display output"
        )
        script_layout.addWidget(self._script_edit)
        self._config_stack.addWidget(script_widget)

        layout.addWidget(self._config_stack)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_data(self):
        """Load existing data into the form."""
        if not self._item_data:
            return

        self._id_edit.setText(self._item_data.get("id", ""))
        self._label_edit.setText(self._item_data.get("label", ""))
        self._requires_card_cb.setChecked(self._item_data.get("requires_card", True))
        self._requires_applet_cb.setChecked(self._item_data.get("requires_applet", True))

        # Load available workflows into combo
        for wf_name in self._available_workflows:
            self._workflow_combo.addItem(wf_name)

        # Load action
        action = self._item_data.get("action", {})
        if action:
            action_type = action.get("type", "workflow")
            # Find index
            for i, (_, value) in enumerate(self.ACTION_TYPES):
                if value == action_type:
                    self._type_combo.setCurrentIndex(i)
                    break

            if action_type == "workflow":
                wf = action.get("workflow", "")
                idx = self._workflow_combo.findText(wf)
                if idx >= 0:
                    self._workflow_combo.setCurrentIndex(idx)
                else:
                    self._workflow_combo.setEditText(wf)

            elif action_type == "apdu_sequence":
                for apdu in action.get("apdu_sequence", []):
                    if isinstance(apdu, str):
                        self._apdu_list.addItem(apdu)
                    elif isinstance(apdu, dict):
                        apdu_str = apdu.get("apdu", "")
                        desc = apdu.get("description", "")
                        display = f"{apdu_str}" + (f" ({desc})" if desc else "")
                        item = QListWidgetItem(display)
                        item.setData(Qt.UserRole, apdu)
                        self._apdu_list.addItem(item)

            elif action_type == "command":
                cmd = action.get("command", [])
                if isinstance(cmd, list):
                    self._command_edit.setText(" ".join(cmd))
                else:
                    self._command_edit.setText(str(cmd))

            elif action_type == "script":
                self._script_edit.setPlainText(action.get("script", ""))
        else:
            # Load available workflows even for new items
            for wf_name in self._available_workflows:
                if self._workflow_combo.findText(wf_name) < 0:
                    self._workflow_combo.addItem(wf_name)

    def _auto_generate_id(self, text: str):
        """Auto-generate ID from label if ID is empty or was auto-generated."""
        current_id = self._id_edit.text()
        # Only auto-generate if field is empty or looks auto-generated
        if not current_id or re.match(r'^[a-z_]+$', current_id):
            generated = re.sub(r'[^a-zA-Z0-9]+', '_', text).strip('_').lower()
            self._id_edit.setText(generated)

    def _on_requires_card_changed(self, state):
        """Disable requires_applet when requires_card is unchecked."""
        if state != Qt.Checked:
            self._requires_applet_cb.setChecked(False)
            self._requires_applet_cb.setEnabled(False)
        else:
            self._requires_applet_cb.setEnabled(True)

    def _on_type_changed(self, index):
        """Switch the config panel."""
        self._config_stack.setCurrentIndex(index)

    def _add_apdu(self):
        """Add an APDU entry."""
        apdu_str, ok = _get_apdu_input(self)
        if ok and apdu_str:
            self._apdu_list.addItem(apdu_str)

    def _remove_apdu(self):
        """Remove selected APDU."""
        current = self._apdu_list.currentRow()
        if current >= 0:
            self._apdu_list.takeItem(current)

    def _validate_and_accept(self):
        """Validate before accepting."""
        item_id = self._id_edit.text().strip()
        label = self._label_edit.text().strip()

        if not item_id:
            QMessageBox.warning(self, "Validation Error", "ID is required.")
            return
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', item_id):
            QMessageBox.warning(
                self, "Validation Error",
                "ID must start with a letter/underscore and contain only letters, numbers, underscores."
            )
            return
        if not label:
            QMessageBox.warning(self, "Validation Error", "Label is required.")
            return

        self.accept()

    def get_item_data(self) -> dict:
        """Get the menu item data as a dict."""
        _, action_type_value = self.ACTION_TYPES[self._type_combo.currentIndex()]

        action = {"type": action_type_value}

        if action_type_value == "workflow":
            wf = self._workflow_combo.currentText().strip()
            if wf:
                action["workflow"] = wf

        elif action_type_value == "apdu_sequence":
            apdus = []
            for i in range(self._apdu_list.count()):
                item = self._apdu_list.item(i)
                stored = item.data(Qt.UserRole)
                if stored and isinstance(stored, dict):
                    apdus.append(stored)
                else:
                    apdus.append({"apdu": item.text()})
            if apdus:
                action["apdu_sequence"] = apdus

        elif action_type_value == "command":
            cmd_text = self._command_edit.text().strip()
            if cmd_text:
                action["command"] = cmd_text.split()

        elif action_type_value == "script":
            script = self._script_edit.toPlainText().strip()
            if script:
                action["script"] = script

        return {
            "id": self._id_edit.text().strip(),
            "label": self._label_edit.text().strip(),
            "requires_card": self._requires_card_cb.isChecked(),
            "requires_applet": self._requires_applet_cb.isChecked(),
            "action": action,
        }


def _get_apdu_input(parent) -> tuple:
    """Simple input dialog for APDU hex string."""
    from PyQt5.QtWidgets import QInputDialog
    text, ok = QInputDialog.getText(
        parent, "Add APDU",
        "APDU hex string (use {field_id} for template variables):"
    )
    return text.strip(), ok


class MenuItemsPage(QWizardPage):
    """Wizard page for defining plugin menu bar items."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Menu Items")
        self.setSubTitle(
            "Define actions that appear in the Plugins menu bar. "
            "These provide quick access to plugin functionality."
        )

        self._menu_items: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Items list
        layout.addWidget(QLabel("Menu Items:"))

        self._items_list = QListWidget()
        self._items_list.itemDoubleClicked.connect(self._edit_item)
        layout.addWidget(self._items_list)

        # Buttons
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("Add Item")
        add_btn.clicked.connect(self._add_item)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_selected_item)
        btn_layout.addWidget(edit_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_item)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._move_item_up)
        btn_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._move_item_down)
        btn_layout.addWidget(move_down_btn)

        layout.addLayout(btn_layout)

        # Skip checkbox
        self._skip_check = QCheckBox("Skip menu items (no menu bar integration)")
        self._skip_check.stateChanged.connect(self._on_skip_changed)
        layout.addWidget(self._skip_check)

    def initializePage(self):
        """Load existing menu items when editing."""
        wizard = self.wizard()
        if not wizard:
            return

        items = wizard.get_plugin_value("menu_items", [])
        if items and not self._menu_items:
            import copy
            self._menu_items = copy.deepcopy(items)

        if self._menu_items:
            self._update_list()

    def _on_skip_changed(self, state):
        """Handle skip checkbox change."""
        self._items_list.setEnabled(state != Qt.Checked)

    def _get_available_workflows(self) -> list[str]:
        """Get workflow names from the wizard."""
        wizard = self.wizard()
        if not wizard:
            return []
        workflows = wizard.get_plugin_value("workflows", {})
        if workflows and isinstance(workflows, dict):
            return list(workflows.keys())
        return []

    def _get_existing_ids(self, exclude_index: int = -1) -> set:
        """Get set of existing item IDs."""
        ids = set()
        for i, item in enumerate(self._menu_items):
            if i != exclude_index:
                ids.add(item.get("id", ""))
        return ids

    def _add_item(self):
        """Add a new menu item."""
        dialog = MenuItemDefinitionDialog(
            available_workflows=self._get_available_workflows(),
            parent=self,
        )
        if dialog.exec_() == QDialog.Accepted:
            item_data = dialog.get_item_data()
            item_id = item_data.get("id")
            if item_id:
                if item_id in self._get_existing_ids():
                    QMessageBox.warning(
                        self, "Duplicate ID",
                        f"A menu item with ID '{item_id}' already exists."
                    )
                    return
                self._menu_items.append(item_data)
                self._update_list()

    def _edit_item(self, item: QListWidgetItem):
        """Edit a menu item by double-clicking."""
        index = self._items_list.row(item)
        if 0 <= index < len(self._menu_items):
            self._edit_item_at(index)

    def _edit_selected_item(self):
        """Edit the selected menu item."""
        current = self._items_list.currentRow()
        if current >= 0:
            self._edit_item_at(current)

    def _edit_item_at(self, index: int):
        """Edit menu item at index."""
        if 0 <= index < len(self._menu_items):
            dialog = MenuItemDefinitionDialog(
                item_data=self._menu_items[index],
                available_workflows=self._get_available_workflows(),
                parent=self,
            )
            if dialog.exec_() == QDialog.Accepted:
                item_data = dialog.get_item_data()
                item_id = item_data.get("id")
                if item_id and item_id in self._get_existing_ids(exclude_index=index):
                    QMessageBox.warning(
                        self, "Duplicate ID",
                        f"A menu item with ID '{item_id}' already exists."
                    )
                    return
                self._menu_items[index] = item_data
                self._update_list()

    def _remove_item(self):
        """Remove selected menu item."""
        current = self._items_list.currentRow()
        if 0 <= current < len(self._menu_items):
            self._menu_items.pop(current)
            self._update_list()

    def _move_item_up(self):
        """Move selected item up."""
        current = self._items_list.currentRow()
        if current > 0:
            self._menu_items[current], self._menu_items[current - 1] = \
                self._menu_items[current - 1], self._menu_items[current]
            self._update_list()
            self._items_list.setCurrentRow(current - 1)

    def _move_item_down(self):
        """Move selected item down."""
        current = self._items_list.currentRow()
        if 0 <= current < len(self._menu_items) - 1:
            self._menu_items[current], self._menu_items[current + 1] = \
                self._menu_items[current + 1], self._menu_items[current]
            self._update_list()
            self._items_list.setCurrentRow(current + 1)

    def _update_list(self):
        """Update the items list display."""
        self._items_list.clear()

        for item_data in self._menu_items:
            item_id = item_data.get("id", "?")
            label = item_data.get("label", item_id)
            action = item_data.get("action", {})
            action_type = action.get("type", "?")

            suffix = ""
            if action_type == "workflow" and action.get("workflow"):
                suffix = f" -> {action['workflow']}"
            elif action_type == "apdu_sequence":
                count = len(action.get("apdu_sequence", []))
                suffix = f" ({count} APDUs)"
            elif action_type == "command" and action.get("command"):
                cmd = action["command"]
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                suffix = f" $ {cmd_str}"
            elif action_type == "script":
                suffix = " (script)"

            # Card requirement indicator
            req = ""
            if not item_data.get("requires_card", True):
                req = " [always]"
            elif not item_data.get("requires_applet", True):
                req = " [card]"

            item_text = f"{label}{suffix}{req}"
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.UserRole, item_data)
            self._items_list.addItem(list_item)

    def validatePage(self) -> bool:
        """Validate and save data."""
        wizard = self.wizard()
        if not wizard:
            return True

        if self._skip_check.isChecked() or not self._menu_items:
            wizard.set_plugin_data("menu_items", None)
        else:
            wizard.set_plugin_data("menu_items", self._menu_items)

        return True
