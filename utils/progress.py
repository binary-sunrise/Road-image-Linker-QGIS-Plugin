"""Progress handling utilities for Road Image Linker plugin."""
from dataclasses import dataclass
from typing import Optional, Callable
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QApplication

@dataclass
class ProgressStep:
    """Represents a step in a progress workflow."""
    value: int
    message: str

class ProgressHandler(QObject):
    """Centralized progress handling for the plugin."""
    progress_signal = pyqtSignal(int, str)
    
    def __init__(self, dialog=None):
        super().__init__()
        self.dialog = dialog
        
    def update(self, value: int, message: str):
        """Update progress with a value and message."""
        if self.dialog:
            self.dialog.set_progress(value, message)
        self.progress_signal.emit(value, message)
        QApplication.processEvents()
    
    def handle_workflow(self, steps: list[ProgressStep], action: Callable):
        """Execute a workflow with progress updates."""
        try:
            for step in steps:
                self.update(step.value, step.message)
                if action:
                    action()
            return True
        except Exception as e:
            self.update(0, f"Error: {str(e)}")
            return False
