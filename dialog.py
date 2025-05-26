import os
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'dialog.ui'))

class RoadImageLinkerDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(RoadImageLinkerDialog, self).__init__(parent)
        self.setupUi(self)
        
        # Connect buttons to methods
        self.btn_browse_shapefile.clicked.connect(self.select_shapefile)
        self.btn_browse_images.clicked.connect(self.select_images_folder)
        self.btn_browse_output.clicked.connect(self.select_output_path)
        
        # Set default values
        self.spin_max_distance.setValue(50)
        
    def select_shapefile(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Road Shapefile", 
            "", 
            "Shapefile (*.shp);;All Files (*)"
        )
        if file_path:
            self.line_shapefile.setText(file_path)
    
    def select_images_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self, 
            "Select Images Folder"
        )
        if folder_path:
            self.line_images_folder.setText(folder_path)
    
    def select_output_path(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Output Shapefile", 
            "", 
            "Shapefile (*.shp);;All Files (*)"
        )
        if file_path:
            self.line_output.setText(file_path)
    
    def get_shapefile_path(self):
        return self.line_shapefile.text()
    
    def get_images_folder(self):
        return self.line_images_folder.text()
    
    def get_output_path(self):
        return self.line_output.text()
    
    def get_max_distance(self):
        return self.spin_max_distance.value()
    
    def accept(self):
        # Validate inputs before accepting
        if not self.get_shapefile_path():
            QMessageBox.warning(self, "Warning", "Please select a shapefile")
            return
        
        if not self.get_images_folder():
            QMessageBox.warning(self, "Warning", "Please select images folder")
            return
            
        if not self.get_output_path():
            QMessageBox.warning(self, "Warning", "Please specify output path")
            return
        
        super().accept()