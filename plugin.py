import os
import tempfile
import shutil
from pathlib import Path
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsProject, QgsMessageLog, Qgis, QgsVectorLayer, QgsTask, QgsApplication
from .ui.dialog import RoadImageLinkerDialog
from .ui.progress_dialog import ProgressDialog
from .core.road_image_linker_core import RoadImageLinker
from .core.excel_to_shapefile import ExcelToShapefileConverter
from .utils.progress import ProgressHandler, ProgressStep
from .utils.file_handler import FileHandler

class RoadImageLinkerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.temp_dir = None
        self.file_handler = FileHandler()
        self.progress_handler = None
        self.progress_dialog = None
        
        # Initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = self.file_handler.ensure_path(self.plugin_dir) / 'i18n' / f'RoadImageLinker_{locale}.qm'

        if locale_path.exists():
            self.translator = QTranslator()
            self.translator.load(str(locale_path))
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&Road Image Linker')
        self.first_start = None

    def tr(self, message):
        return QCoreApplication.translate('RoadImageLinker', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToVectorMenu(
                self.menu,
                action)

        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.add_action(
            icon_path,
            text=self.tr(u'Link Road Images'),
            callback=self.run,
            parent=self.iface.mainWindow())

        self.first_start = True

    def unload(self):
        for action in self.actions:
            self.iface.removePluginVectorMenu(
                self.tr(u'&Road Image Linker'),
                action)
            self.iface.removeToolBarIcon(action)
        
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                QgsMessageLog.logMessage(
                    f"Error cleaning temp directory: {str(e)}",
                    "Road Image Linker", Qgis.Warning)

    def run(self):
        if self.first_start:
            self.first_start = False
            self.dlg = RoadImageLinkerDialog()

        self.dlg.show()
        result = self.dlg.exec_()
        
        if result:
            self.execute_linking()

    def execute_linking(self):
        try:
            # Initialize progress dialog and handler
            self.progress_dialog = ProgressDialog()
            self.progress_handler = ProgressHandler(self.progress_dialog)
            self.progress_dialog.show()
            
            workflow_steps = [
                ProgressStep(5, "Starting processing..."),
                ProgressStep(10, "Validating input files..."),
                ProgressStep(30, "Initializing road image linker..."),
                ProgressStep(40, "Processing roads and images..."),
                ProgressStep(90, "Loading results..."),
                ProgressStep(100, "Processing complete!")
            ]
            
            # Get parameters from dialog
            input_type = self.dlg.get_input_type()
            images_folder = self.dlg.get_images_folder()
            output_path = self.dlg.get_output_path()
            max_distance = self.dlg.get_max_distance()
            
            self.progress_handler.update(workflow_steps[0].value, workflow_steps[0].message)

            # Validate images folder
            valid, msg = self.file_handler.validate_file_exists(images_folder)
            if not valid:
                self.show_error(f"Images folder error: {msg}")
                return

            # Handle Excel input
            if input_type == 'excel':
                excel_path = self.dlg.get_excel_path()
                valid, msg = self.file_handler.validate_file_exists(excel_path, '.xlsx')
                if not valid:
                    self.show_error(f"Excel file error: {msg}")
                    return
                
                # Create temporary shapefile
                self.temp_dir = tempfile.mkdtemp()
                temp_shapefile = str(self.file_handler.ensure_path(self.temp_dir) / "temp_roads.shp")
                
                self.progress_handler.update(workflow_steps[1].value, workflow_steps[1].message)
                
                converter = ExcelToShapefileConverter(self.progress_dialog)
                success, msg = converter.process_excel(excel_path, temp_shapefile)
                
                if not success:
                    self.show_error(msg)
                    return
                
                shapefile_path = temp_shapefile
            else:
                shapefile_path = self.dlg.get_shapefile_path()
                valid, msg = self.file_handler.validate_file_exists(shapefile_path, '.shp')
                if not valid:
                    self.show_error(f"Shapefile error: {msg}")
                    return
            
            # Proceed with existing logic
            self.progress_handler.update(workflow_steps[2].value, workflow_steps[2].message)
            
            linker = RoadImageLinker(shapefile_path, images_folder)
            linker.progress_signal.connect(self.update_progress)
            
            self.progress_handler.update(workflow_steps[3].value, workflow_steps[3].message)
            
            success = linker.run_complete_workflow(output_path, max_distance)
            
            if success:
                self.progress_handler.update(workflow_steps[4].value, workflow_steps[4].message)
                
                # Get the layer name from the output path (without extension)
                layer_name = self.file_handler.ensure_path(output_path).stem
                
                # Remove existing layer if it exists
                existing_layers = QgsProject.instance().mapLayersByName(layer_name)
                for layer in existing_layers:
                    QgsProject.instance().removeMapLayer(layer)
                
                # Load the new layer
                layer = QgsVectorLayer(output_path, layer_name, "ogr")
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    
                    # Configure map tips
                    output_dir = self.file_handler.ensure_path(output_path).parent
                    html_path = output_dir / "image_tooltip_template.html"
                    
                    self.setup_map_tips(layer, html_path)
                    
                    self.progress_handler.update(workflow_steps[5].value, workflow_steps[5].message)
                    self.iface.messageBar().pushMessage(
                        "Success", 
                        f"Successfully processed roads. Layer '{layer_name}' added to map.",
                        level=Qgis.Success,
                        duration=5
                    )
                    
                    # Zoom to the layer extent
                    self.iface.mapCanvas().setExtent(layer.extent())
                    self.iface.mapCanvas().refresh()
                else:
                    self.show_error("Failed to load result layer")
            else:
                self.show_error("Processing failed. Check the log for details.")
                
        except Exception as e:
            self.show_error(f"Plugin error: {str(e)}")
            QgsMessageLog.logMessage(
                f"Road Image Linker Error: {str(e)}", 
                level=Qgis.Critical)
        finally:
            if self.progress_dialog:
                self.progress_dialog.close()

    def update_progress(self, value, message):
        if self.progress_handler:
            self.progress_handler.update(value, message)

    def show_error(self, message):
        self.iface.messageBar().pushMessage(
            "Error", 
            message,
            level=Qgis.Critical)
        if self.progress_dialog:
            self.progress_dialog.close()

    def setup_map_tips(self, layer, html_path):
        try:
            if not html_path.exists():
                QgsMessageLog.logMessage(
                    f"HTML template not found: {html_path}", 
                    "Road Image Linker", Qgis.Warning)
                return False
                
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            layer.setMapTipTemplate(html_content)
            
            if self.iface:
                self.iface.actionShowMapTips().setChecked(True)
            
            QgsMessageLog.logMessage(
                f"Map tips configured for layer: {layer.name()}", 
                "Road Image Linker", Qgis.Info)
            return True
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error setting up map tips: {e}", 
                "Road Image Linker", Qgis.Critical)
            return False