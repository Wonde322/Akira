"""Confirmation bridge for the desktop UI.

Desktop Akira runs in autonomous mode. The compatibility service is kept for
older imports, but it never blocks a worker on a modal approval dialog.
"""

from PySide6.QtCore import QObject, Signal


class ConfirmationService(QObject):
    """Compatibility provider for autonomous desktop execution."""

    request_received = Signal(str, str, dict, object)

    def __init__(self, parent=None, timeout=600):
        super().__init__(parent)
        self.timeout = timeout

    def provider(self, tool_name, arguments):
        """Approve ordinary desktop tool execution without opening a modal."""
        return True
