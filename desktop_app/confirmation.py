"""Desktop execution policy.

The desktop assistant is autonomous: this module never creates or waits for a
modal approval dialog. The signal remains only so old UI code can import the
same class safely.
"""
from PySide6.QtCore import QObject, Signal

class ConfirmationService(QObject):
    request_received=Signal(str,str,dict,object)
    def __init__(self,parent=None,timeout=0):
        super().__init__(parent); self.timeout=timeout
    def provider(self,tool_name,arguments):
        return True
