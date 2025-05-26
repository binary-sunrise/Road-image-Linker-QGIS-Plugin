from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsProject, QgsMessageLog, Qgis, QgsVectorLayer
import os.path
from .dialog import RoadImageLinkerDialog
from .road_image_linker_core import RoadImageLinker

class RoadImageLinkerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        
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

    def tr(self, message):
        return QCoreApplication.translate('RoadImageLinker', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True,
                   add_to_menu=True, add_to_toolbar=True, status_tip=None,
                   whats_this=None, parent=None):
        
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
            self.iface.addPluginToVectorMenu(self.menu, action)

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

    def run(self):
        if self.first_start == True:
            self.first_start = False
            self.dlg = RoadImageLinkerDialog()

        self.dlg.show()
        result = self.dlg.exec_()
        
        if result:
            self.execute_linking()

    def execute_linking(self):
        try:
            # Get parameters from dialog
            shapefile_path = self.dlg.get_shapefile_path()
            images_folder = self.dlg.get_images_folder()
            output_path = self.dlg.get_output_path()
            max_distance = self.dlg.get_max_distance()
            
            linker = RoadImageLinker(shapefile_path, images_folder)
            success = linker.run_complete_workflow(output_path, max_distance)
            
            if success:
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
                    
                    self.iface.messageBar().pushMessage(
                        "Success", 
                        f"Successfully linked roads to images. Layer '{layer_name}' added to map with map tips configured.",
                        level=Qgis.Success,
                        duration=5
                    )
                    
                    # Zoom to the layer extent
                    self.iface.mapCanvas().setExtent(layer.extent())
                    self.iface.mapCanvas().refresh()
                else:
                    self.iface.messageBar().pushMessage(
                        "Error", 
                        "Failed to load result layer",
                        level=Qgis.Critical
                    )
            else:
                self.iface.messageBar().pushMessage(
                    "Error", 
                    "Failed to link roads to images. Check the log for details.",
                    level=Qgis.Critical
                )
                
        except Exception as e:
            self.iface.messageBar().pushMessage(
                "Error", 
                f"Plugin error: {str(e)}",
                level=Qgis.Critical
            )
            QgsMessageLog.logMessage(f"Road Image Linker Error: {str(e)}", level=Qgis.Critical)

    def setup_map_tips(self, layer, html_path):
        """Configure map tips for the layer"""
        try:
            # Verify HTML template exists
            if not os.path.exists(html_path):
                QgsMessageLog.logMessage(
                    f"HTML template not found: {html_path}", 
                    "Road Image Linker", Qgis.Warning
                )
                return False
                
            # Read HTML template
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Configure map tips
            layer.setMapTipTemplate(html_content)
            
            # Enable map tips in QGIS interface
            if self.iface:
                self.iface.actionShowMapTips().setChecked(True)
            
            QgsMessageLog.logMessage(
                f"Map tips configured for layer: {layer.name()}", 
                "Road Image Linker", Qgis.Info
            )
            return True
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error setting up map tips: {e}", 
                "Road Image Linker", Qgis.Critical
            )
            return False

def classFactory(iface):
    return RoadImageLinkerPlugin(iface)