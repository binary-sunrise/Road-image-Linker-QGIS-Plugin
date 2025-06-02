from qgis.PyQt.QtWidgets import QDialog, QFileDialog
from qgis.PyQt import uic
import os

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'dialog.ui'))

class RoadImageLinkerDialog(QDialog, FORM_CLASS):
    def __init__(self):
        QDialog.__init__(self)
        self.setupUi(self)
        
        # Connect browse buttons
        self.browseShapefileButton.clicked.connect(self.browse_shapefile)
        self.browseImagesButton.clicked.connect(self.browse_images)
        self.browseOutputButton.clicked.connect(self.browse_output)
        self.browseExcelButton.clicked.connect(self.browse_excel)
        
        # Initialize input type toggle
        self.inputTypeComboBox.currentIndexChanged.connect(self.toggle_input_type)
        self.toggle_input_type()  # Set initial state
        
    def toggle_input_type(self):
        """Show/hide appropriate input fields based on selection"""
        is_shapefile = self.inputTypeComboBox.currentIndex() == 0
        self.shapefileLabel.setVisible(is_shapefile)
        self.shapefileLineEdit.setVisible(is_shapefile)
        self.browseShapefileButton.setVisible(is_shapefile)
        
        is_excel = self.inputTypeComboBox.currentIndex() == 1
        self.excelLabel.setVisible(is_excel)
        self.excelLineEdit.setVisible(is_excel)
        self.browseExcelButton.setVisible(is_excel)
    
    def browse_excel(self):
        """Open file dialog for Excel input"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Excel File",
            "",
            "Excel Files (*.xlsx *.xls);;All Files (*)"
        )
        if filename:
            self.excelLineEdit.setText(filename)
    
    def browse_shapefile(self):
        """Open file dialog for shapefile input"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Shapefile",
            "",
            "Shapefiles (*.shp);;All Files (*)"
        )
        if filename:
            self.shapefileLineEdit.setText(filename)
    
    def browse_images(self):
        """Open directory dialog for images folder"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Images Folder"
        )
        if folder:
            self.imagesLineEdit.setText(folder)
    
    def browse_output(self):
        """Open save dialog for output shapefile"""
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Output Shapefile",
            "",
            "Shapefiles (*.shp);;All Files (*)"
        )
        if filename:
            if not filename.lower().endswith('.shp'):
                filename += '.shp'
            self.outputLineEdit.setText(filename)
    
    def get_input_type(self):
        """Returns input type as string"""
        return "shapefile" if self.inputTypeComboBox.currentIndex() == 0 else "excel"
    
    def get_shapefile_path(self):
        return self.shapefileLineEdit.text()
    
    def get_excel_path(self):
        return self.excelLineEdit.text()
    
    def get_images_folder(self):
        return self.imagesLineEdit.text()
    
    def get_output_path(self):
        return self.outputLineEdit.text()
    
    def get_max_distance(self):
        return self.distanceSpinBox.value()