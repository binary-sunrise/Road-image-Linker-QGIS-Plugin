from qgis.PyQt.QtWidgets import QDialog ,QApplication
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
import os

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'ui_progress.ui'))

class ProgressDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(ProgressDialog, self).__init__(parent)
        self.setupUi(self)
        self.setWindowTitle("Processing Progress")
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
        self.progressBar.setValue(0)
        
    def set_progress(self, value, message=None):
        self.progressBar.setValue(value)
        if message:
            self.statusLabel.setText(message)
        QApplication.processEvents()