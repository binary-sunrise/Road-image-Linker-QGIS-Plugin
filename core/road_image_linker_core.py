import os
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsFeature,
    QgsPointXY, QgsGeometry, QgsCoordinateTransform,
    QgsCoordinateReferenceSystem, QgsMessageLog, Qgis
)
from qgis.PyQt.QtCore import QVariant, pyqtSignal, QObject, Qt
from qgis.PyQt.QtWidgets import QApplication
import geopandas as gpd
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import pandas as pd
from shapely.geometry import Point
import numpy as np
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import pathname2url

class RoadImageLinker(QObject):
    progress_signal = pyqtSignal(int, str)
    
    def __init__(self, shapefile_path, images_folder):
        super().__init__()
        self.shapefile_path = Path(shapefile_path)
        self.images_folder = Path(images_folder)
        self.roads_gdf = None
        self.image_points_gdf = None
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.tiff', '.tif'}
        
    def _convert_to_degrees(self, dms_value):
        degrees, minutes, seconds = dms_value
        return degrees + (minutes / 60.0) + (seconds / 3600.0)
    
    def _path_to_uri(self, file_path):
        abs_path = Path(file_path).resolve()
        return urljoin('file:', pathname2url(str(abs_path)))
    
    def extract_gps_from_image(self, image_path):
        try:
            with Image.open(image_path) as image:
                exif_data = image._getexif()
                
                if exif_data is None:
                    return None, None
                    
                gps_info = {}
                for tag, value in exif_data.items():
                    decoded_tag = TAGS.get(tag, tag)
                    if decoded_tag == "GPSInfo":
                        for gps_tag in value:
                            gps_decoded = GPSTAGS.get(gps_tag, gps_tag)
                            gps_info[gps_decoded] = value[gps_tag]
                
                if not gps_info:
                    return None, None
                
                lat_ref = gps_info.get('GPSLatitudeRef')
                lat = gps_info.get('GPSLatitude')
                lon_ref = gps_info.get('GPSLongitudeRef')
                lon = gps_info.get('GPSLongitude')
                
                if not all([lat, lon, lat_ref, lon_ref]):
                    return None, None
                
                lat_decimal = self._convert_to_degrees(lat)
                lon_decimal = self._convert_to_degrees(lon)
                
                if lat_ref == 'S':
                    lat_decimal = -lat_decimal
                if lon_ref == 'W':
                    lon_decimal = -lon_decimal
                    
                return lat_decimal, lon_decimal
                
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Warning: Could not extract GPS from {image_path.name}: {e}",
                "Road Image Linker", Qgis.Warning
            )
            return None, None
    
    def load_road_shapefile(self):
        try:
            if not self.shapefile_path.exists():
                raise FileNotFoundError(f"Shapefile not found: {self.shapefile_path}")
                
            self.roads_gdf = gpd.read_file(self.shapefile_path)
            QgsMessageLog.logMessage(
                f"✓ Loaded {len(self.roads_gdf)} road features", 
                "Road Image Linker", Qgis.Info
            )
            return True
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"✗ Error loading shapefile: {e}", 
                "Road Image Linker", Qgis.Critical
            )
            return False
    
    def extract_image_locations(self):
        if not self.images_folder.exists():
            QgsMessageLog.logMessage(
                f"✗ Images folder not found: {self.images_folder}", 
                "Road Image Linker", Qgis.Critical
            )
            return False
            
        image_data = []
        total_images = 0
        
        for image_file in self.images_folder.rglob('*'):
            if image_file.suffix.lower() in self.supported_formats:
                total_images += 1
                lat, lon = self.extract_gps_from_image(image_file)
                
                if lat is not None and lon is not None:
                    uri_path = self._path_to_uri(image_file)
                    image_data.append({
                        'image_path': str(image_file),
                        'image_uri': uri_path,
                        'filename': image_file.name,
                        'latitude': lat,
                        'longitude': lon,
                        'geometry': Point(lon, lat)
                    })
        
        if image_data:
            self.image_points_gdf = gpd.GeoDataFrame(image_data, crs='EPSG:4326')
            return True
        else:
            QgsMessageLog.logMessage(
                "✗ No images with GPS data found", 
                "Road Image Linker", Qgis.Critical
            )
            return False
    
    def reproject_data(self, target_crs='EPSG:3857'):
        if self.roads_gdf.crs.is_geographic:
            self.roads_gdf = self.roads_gdf.to_crs(target_crs)
            
        if self.image_points_gdf.crs != self.roads_gdf.crs:
            self.image_points_gdf = self.image_points_gdf.to_crs(self.roads_gdf.crs)
    
    def find_closest_images_to_roads(self, max_distance=50):
        for col in ['Image_Path', 'Image_URI', 'Image_Name', 'Distance_m']:
            if col not in self.roads_gdf.columns:
                self.roads_gdf[col] = ''
        
        matches = []
        
        for road_idx, road_feature in self.roads_gdf.iterrows():
            distances = self.image_points_gdf.geometry.distance(road_feature.geometry)
            
            if len(distances) == 0:
                continue
                
            min_distance = distances.min()
            closest_image_idx = distances.idxmin()
            
            if min_distance <= max_distance:
                closest_image = self.image_points_gdf.iloc[closest_image_idx]
                matches.append({
                    'road_idx': road_idx,
                    'image_idx': closest_image_idx,
                    'distance': min_distance,
                    'image_path': closest_image['image_path'],
                    'image_uri': closest_image['image_uri'],
                    'image_name': closest_image['filename']
                })
        
        matched_roads = 0
        for match in matches:
            road_idx = match['road_idx']
            self.roads_gdf.at[road_idx, 'Image_Path'] = match['image_path']
            self.roads_gdf.at[road_idx, 'Image_URI'] = match['image_uri']
            self.roads_gdf.at[road_idx, 'Image_Name'] = match['image_name']
            self.roads_gdf.at[road_idx, 'Distance_m'] = round(match['distance'], 2)
            matched_roads += 1
        
        return matched_roads
    
    def save_updated_shapefile(self, output_path):
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_gdf = self.roads_gdf.to_crs('EPSG:4326')
            output_gdf.to_file(output_path)
            return True
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"✗ Error saving shapefile: {e}", 
                "Road Image Linker", Qgis.Critical
            )
            return False
    
    def create_qgis_assets(self, output_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        html_template = '''<!DOCTYPE html>
<html>
<head>
    <style>
        body { margin: 0; font-family: Arial; background: #f9f9f9; padding: 10px; max-width: 350px; }
        .header { font-weight: bold; color: #333; margin-bottom: 8px; border-bottom: 1px solid #eee; }
        .image-container { text-align: center; margin: 8px 0; padding: 5px; }
        .road-image { max-width: 100%; height: auto; max-height: 180px; border: 1px solid #ddd; }
        .image-info { font-size: 0.85em; color: #555; margin-top: 8px; padding: 5px; }
    </style>
</head>
<body>
    <div class="header">Road Crack Information</div>
    <div class="image-container">
        <img src="[% "Image_URI" %]" class="road-image" onerror="this.style.display='none'">
    </div>
    <div class="image-info">
        <div><strong>File:</strong> [% "Image_Name" %]</div>
        <div><strong>Distance:</strong> [% "Distance_m" %]m</div>
    </div>
</body>
</html>'''
        
        with open(output_dir / "image_tooltip_template.html", 'w', encoding='utf-8') as f:
            f.write(html_template)
    
    def setup_qgis_map_tips(self, layer_name, html_path):
        try:
            html_path = Path(html_path).resolve()
            if not html_path.exists():
                return False
                
            layers = QgsProject.instance().mapLayersByName(layer_name)
            if not layers:
                return False
                
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            layers[0].setMapTipTemplate(html_content)
            return True
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"✗ Error setting up map tips: {e}", 
                "Road Image Linker", Qgis.Critical
            )
            return False
    
    def run_complete_workflow(self, output_shapefile, max_distance=50):
        try:
            self.progress_signal.emit(5, "Starting workflow...")
            QApplication.processEvents()
            
            if not self.load_road_shapefile():
                return False
                
            self.progress_signal.emit(20, "Processing images...")
            QApplication.processEvents()
            if not self.extract_image_locations():
                return False
                
            self.progress_signal.emit(40, "Reprojecting data...")
            QApplication.processEvents()
            self.reproject_data()
            
            self.progress_signal.emit(60, "Matching images...")
            QApplication.processEvents()
            if self.find_closest_images_to_roads(max_distance) == 0:
                return False
                
            self.progress_signal.emit(80, "Saving results...")
            QApplication.processEvents()
            if not self.save_updated_shapefile(output_shapefile):
                return False
                
            self.progress_signal.emit(90, "Creating assets...")
            QApplication.processEvents()
            output_dir = Path(output_shapefile).parent
            self.create_qgis_assets(output_dir)
            
            layer_name = Path(output_shapefile).stem
            html_path = str(output_dir / "image_tooltip_template.html")
            self.setup_qgis_map_tips(layer_name, html_path)
            
            self.progress_signal.emit(100, "Completed successfully!")
            return True
            
        except Exception as e:
            self.progress_signal.emit(0, f"Error: {str(e)}")
            QgsMessageLog.logMessage(
                f"✗ Workflow failed: {e}", 
                "Road Image Linker", Qgis.Critical
            )
            return False


if __name__ == "__main__":
    try:
        shapefile_path = "path/to/roads.shp"
        images_folder = "path/to/images"
        output_shapefile = "path/to/output.shp"
        
        linker = RoadImageLinker(shapefile_path, images_folder)
        success = linker.run_complete_workflow(output_shapefile)
        
        if success:
            print("Processing completed successfully!")
        else:
            print("Processing failed")
            
    except Exception as e:
        print(f"Error: {e}")