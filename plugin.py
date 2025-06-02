import os
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QProgressDialog
from qgis.core import QgsProject, QgsMessageLog, Qgis, QgsVectorLayer, QgsTask, QgsApplication
from .ui.dialog import RoadImageLinkerDialog
from .ui.progress_dialog import ProgressDialog
from .core.road_image_linker_core import RoadImageLinker
from .core.excel_to_shapefile import ExcelToShapefileConverter
import tempfile
import shutil

class RoadImageLinkerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.temp_dir = None
        
        # Initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'RoadImageLinker_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&Road Image Linker')
        self.first_start = None
        self.progress_dialog = None

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
            # Initialize progress dialog
            self.progress_dialog = ProgressDialog()
            self.progress_dialog.show()
            QgsApplication.processEvents()
            
            # Get parameters from dialog
            input_type = self.dlg.get_input_type()
            images_folder = self.dlg.get_images_folder()
            output_path = self.dlg.get_output_path()
            max_distance = self.dlg.get_max_distance()
            
            # Update progress
            self.progress_dialog.set_progress(5, "Starting processing...")
            QgsApplication.processEvents()

            # Handle Excel input
            if input_type == 'excel':
                excel_path = self.dlg.get_excel_path()
                if not excel_path:
                    self.show_error("Please select an Excel file")
                    return
                
                # Create temporary shapefile
                self.temp_dir = tempfile.mkdtemp()
                temp_shapefile = os.path.join(self.temp_dir, "temp_roads.shp")
                
                self.progress_dialog.set_progress(10, "Converting Excel to shapefile...")
                QgsApplication.processEvents()
                
                converter = ExcelToShapefileConverter(self.progress_dialog)
                success, msg = converter.process_excel(excel_path, temp_shapefile)
                
                if not success:
                    self.show_error(msg)
                    return
                
                shapefile_path = temp_shapefile
            else:
                # Original shapefile handling
                shapefile_path = self.dlg.get_shapefile_path()
                if not shapefile_path:
                    self.show_error("Please select a shapefile")
                    return
            
            # Proceed with existing logic
            self.progress_dialog.set_progress(30, "Initializing road image linker...")
            QgsApplication.processEvents()
            
            linker = RoadImageLinker(shapefile_path, images_folder)
            linker.progress_signal.connect(self.update_progress)
            
            self.progress_dialog.set_progress(40, "Processing roads and images...")
            QgsApplication.processEvents()
            
            success = linker.run_complete_workflow(output_path, max_distance)
            
            if success:
                self.progress_dialog.set_progress(90, "Loading results...")
                QgsApplication.processEvents()
                
                # Get the layer name from the output path (without extension)
                layer_name = os.path.splitext(os.path.basename(output_path))[0]
                
                # Remove existing layer if it exists
                existing_layers = QgsProject.instance().mapLayersByName(layer_name)
                for layer in existing_layers:
                    QgsProject.instance().removeMapLayer(layer)
                
                # Load the new layer
                layer = QgsVectorLayer(output_path, layer_name, "ogr")
                if layer.isValid():
                    QgsProject.instance().addMapLayer(layer)
                    
                    # Get the HTML template path (in same directory as output)
                    output_dir = os.path.dirname(output_path)
                    html_path = os.path.join(output_dir, "image_tooltip_template.html")
                    
                    # Configure map tips
                    self.setup_map_tips(layer, html_path)
                    
                    self.progress_dialog.set_progress(100, "Processing complete!")
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
        if self.progress_dialog:
            self.progress_dialog.set_progress(value, message)
            QgsApplication.processEvents()

    def show_error(self, message):
        self.iface.messageBar().pushMessage(
            "Error", 
            message,
            level=Qgis.Critical)
        if self.progress_dialog:
            self.progress_dialog.close()

    def setup_map_tips(self, layer, html_path):
        try:
            if not os.path.exists(html_path):
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