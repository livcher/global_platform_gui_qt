"""
Platform-aware color palette for light/dark mode support.

Provides adaptive colors that work across Windows, macOS, and Linux
in both light and dark system themes.
"""

import platform
import subprocess

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette


def is_dark_mode() -> bool:
    """Detect if the system is using dark mode."""
    if platform.system() == "Darwin":
        # macOS: check AppleInterfaceStyle
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return result.stdout.strip().lower() == "dark"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False
    elif platform.system() == "Windows":
        # Windows: check registry for AppsUseLightTheme
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0  # 0 = dark mode, 1 = light mode
        except (ImportError, FileNotFoundError, OSError):
            return False
    else:
        # Linux and others: check Qt palette luminance
        app = QApplication.instance()
        if app:
            palette = app.palette()
            bg = palette.color(QPalette.Window)
            # If background luminance is low, it's dark mode
            return (bg.red() * 0.299 + bg.green() * 0.587 + bg.blue() * 0.114) < 128
    return False


class Colors:
    """Adaptive colors based on system theme."""

    _dark_mode = None

    @classmethod
    def refresh(cls):
        """Refresh dark mode detection (call after app starts)."""
        cls._dark_mode = is_dark_mode()

    @classmethod
    def _is_dark(cls) -> bool:
        if cls._dark_mode is None:
            cls._dark_mode = is_dark_mode()
        return cls._dark_mode

    @classmethod
    def muted_text(cls) -> str:
        """Muted/secondary text color."""
        return "#aaa" if cls._is_dark() else "#666"

    @classmethod
    def secondary_text(cls) -> str:
        """Secondary text color (slightly more visible than muted)."""
        return "#999" if cls._is_dark() else "#888"

    @classmethod
    def primary_text(cls) -> str:
        """Primary text color."""
        return "#ddd" if cls._is_dark() else "#333"

    @classmethod
    def subtle_text(cls) -> str:
        """Subtle text color."""
        return "#bbb" if cls._is_dark() else "#555"

    @classmethod
    def light_bg(cls) -> str:
        """Light background for panels/cards."""
        return "#2d2d2d" if cls._is_dark() else "#f5f5f5"

    @classmethod
    def lighter_bg(cls) -> str:
        """Slightly lighter background."""
        return "#363636" if cls._is_dark() else "#f8f8f8"

    @classmethod
    def input_bg(cls) -> str:
        """Background for disabled/readonly inputs."""
        return "#3d3d3d" if cls._is_dark() else "#f0f0f0"

    @classmethod
    def info_bg(cls) -> str:
        """Info panel background (blue tint)."""
        return "#1a3a4a" if cls._is_dark() else "#e3f2fd"

    @classmethod
    def warning_text(cls) -> str:
        """Warning text color."""
        return "#ffb74d" if cls._is_dark() else "#cc6600"

    @classmethod
    def warning_bg(cls) -> str:
        """Warning background."""
        return "#3d3020" if cls._is_dark() else "#fdf6e3"

    @classmethod
    def warning_border(cls) -> str:
        """Warning text on warning bg."""
        return "#ffb74d" if cls._is_dark() else "#b58900"

    @classmethod
    def card_bg(cls) -> str:
        """Card/panel background (e.g., plugin items)."""
        return "#383838" if cls._is_dark() else "#ffffff"

    @classmethod
    def card_border(cls) -> str:
        """Card/panel border."""
        return "#555" if cls._is_dark() else "#d0d0d0"

    @classmethod
    def card_hover_border(cls) -> str:
        """Card/panel border on hover."""
        return "#888" if cls._is_dark() else "#999"

    @classmethod
    def hover_bg(cls) -> str:
        """Background on hover (buttons, tool buttons)."""
        return "#505050" if cls._is_dark() else "#e0e0e0"

    @classmethod
    def alert_error_text(cls) -> str:
        """Alert box error/danger text."""
        return "#fca5a5" if cls._is_dark() else "#b91c1c"

    @classmethod
    def alert_error_bg(cls) -> str:
        """Alert box error/danger background."""
        return "#451a1a" if cls._is_dark() else "#fef2f2"

    @classmethod
    def alert_error_border(cls) -> str:
        """Alert box error/danger border."""
        return "#7f1d1d" if cls._is_dark() else "#fecaca"

    @classmethod
    def link(cls) -> str:
        """Hyperlink color."""
        return "#6cb4ee" if cls._is_dark() else "#1a73e8"

    @classmethod
    def success(cls) -> str:
        """Success/valid color."""
        return "#81c784" if cls._is_dark() else "#4caf50"

    @classmethod
    def error(cls) -> str:
        """Error/invalid color."""
        return "#e57373" if cls._is_dark() else "#f44336"
