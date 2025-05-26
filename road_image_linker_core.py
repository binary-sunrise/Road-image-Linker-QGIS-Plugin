import os
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsField, QgsFeature,
    QgsPointXY, QgsGeometry, QgsCoordinateTransform,
    QgsCoordinateReferenceSystem, QgsMessageLog, Qgis
)
from qgis.PyQt.QtCore import QVariant
import geopandas as gpd
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import pandas as pd
from shapely.geometry import Point
import numpy as np
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import pathname2url

class RoadImageLinker:
    """
    Links road polyline features to their closest geocoded images.
    Each road feature gets associated with exactly one closest image.
    """
    
    def __init__(self, shapefile_path, images_folder):
        """
        Initialize the Road Image Linker
        
        Args:
            shapefile_path (str): Path to the road polylines shapefile
            images_folder (str): Path to folder containing geocoded images
        """
        self.shapefile_path = Path(shapefile_path)
        self.images_folder = Path(images_folder)
        self.roads_gdf = None
        self.image_points_gdf = None
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.tiff', '.tif'}
        
    def _convert_to_degrees(self, dms_value):
        """
        Convert GPS DMS (Degrees, Minutes, Seconds) to decimal degrees
        
        Args:
            dms_value: Tuple of (degrees, minutes, seconds)
            
        Returns:
            float: Decimal degrees
        """
        degrees, minutes, seconds = dms_value
        return degrees + (minutes / 60.0) + (seconds / 3600.0)
    
    def _path_to_uri(self, file_path):
        """
        Convert file path to URI format
        
        Args:
            file_path (str or Path): File system path
            
        Returns:
            str: URI formatted path (file:///C:/path/to/file.jpg)
        """
        abs_path = Path(file_path).resolve()
        return urljoin('file:', pathname2url(str(abs_path)))
    
    def extract_gps_from_image(self, image_path):
        """
        Extract GPS coordinates from image EXIF data
        
        Args:
            image_path (Path): Path to the image file
            
        Returns:
            tuple: (latitude, longitude) or (None, None) if no GPS data
        """
        try:
            with Image.open(image_path) as image:
                exif_data = image._getexif()
                
                if exif_data is None:
                    return None, None
                    
                # Extract GPS info
                gps_info = {}
                for tag, value in exif_data.items():
                    decoded_tag = TAGS.get(tag, tag)
                    if decoded_tag == "GPSInfo":
                        for gps_tag in value:
                            gps_decoded = GPSTAGS.get(gps_tag, gps_tag)
                            gps_info[gps_decoded] = value[gps_tag]
                
                if not gps_info:
                    return None, None
                
                # Extract and validate coordinates
                lat_ref = gps_info.get('GPSLatitudeRef')
                lat = gps_info.get('GPSLatitude')
                lon_ref = gps_info.get('GPSLongitudeRef')
                lon = gps_info.get('GPSLongitude')
                
                if not all([lat, lon, lat_ref, lon_ref]):
                    return None, None
                
                # Convert to decimal degrees
                lat_decimal = self._convert_to_degrees(lat)
                lon_decimal = self._convert_to_degrees(lon)
                
                # Apply hemisphere corrections
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
        """
        Load the road polylines shapefile
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.shapefile_path.exists():
                raise FileNotFoundError(f"Shapefile not found: {self.shapefile_path}")
                
            self.roads_gdf = gpd.read_file(self.shapefile_path)
            QgsMessageLog.logMessage(
                f"✓ Loaded {len(self.roads_gdf)} road features", 
                "Road Image Linker", Qgis.Info
            )
            QgsMessageLog.logMessage(
                f"  CRS: {self.roads_gdf.crs}", 
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
        """
        Extract GPS coordinates from all images in the folder
        
        Returns:
            bool: True if images with GPS found, False otherwise
        """
        if not self.images_folder.exists():
            QgsMessageLog.logMessage(
                f"✗ Images folder not found: {self.images_folder}", 
                "Road Image Linker", Qgis.Critical
            )
            return False
            
        QgsMessageLog.logMessage(
            f"Scanning for images in: {self.images_folder}", 
            "Road Image Linker", Qgis.Info
        )
        
        image_data = []
        total_images = 0
        
        # Scan all image files
        for image_file in self.images_folder.rglob('*'):
            if image_file.suffix.lower() in self.supported_formats:
                total_images += 1
                lat, lon = self.extract_gps_from_image(image_file)
                
                if lat is not None and lon is not None:
                    # Convert path to URI format
                    uri_path = self._path_to_uri(image_file)
                    
                    image_data.append({
                        'image_path': str(image_file),
                        'image_uri': uri_path,
                        'filename': image_file.name,
                        'latitude': lat,
                        'longitude': lon,
                        'geometry': Point(lon, lat)
                    })
        
        QgsMessageLog.logMessage(
            f"  Found {total_images} image files", 
            "Road Image Linker", Qgis.Info
        )
        QgsMessageLog.logMessage(
            f"  {len(image_data)} images have GPS coordinates", 
            "Road Image Linker", Qgis.Info
        )
        
        if image_data:
            self.image_points_gdf = gpd.GeoDataFrame(image_data, crs='EPSG:4326')
            self._print_coordinate_summary()
            return True
        else:
            QgsMessageLog.logMessage(
                "✗ No images with GPS data found", 
                "Road Image Linker", Qgis.Critical
            )
            return False
    
    def _print_coordinate_summary(self):
        """Print summary of coordinate ranges for debugging"""
        if self.image_points_gdf is not None:
            bounds = self.image_points_gdf.total_bounds
            QgsMessageLog.logMessage(
                f"  Image coordinate bounds: [{bounds[0]:.6f}, {bounds[1]:.6f}] to [{bounds[2]:.6f}, {bounds[3]:.6f}]", 
                "Road Image Linker", Qgis.Info
            )
    
    def reproject_data(self, target_crs='EPSG:3857'):
        """
        Reproject data to a projected CRS for accurate distance calculations
        
        Args:
            target_crs (str): Target coordinate reference system
        """
        QgsMessageLog.logMessage(
            "Reprojecting data for distance calculations...", 
            "Road Image Linker", Qgis.Info
        )
        
        # Reproject roads if geographic
        if self.roads_gdf.crs.is_geographic:
            self.roads_gdf = self.roads_gdf.to_crs(target_crs)
            QgsMessageLog.logMessage(
                f"  Roads reprojected to {target_crs}", 
                "Road Image Linker", Qgis.Info
            )
            
        # Reproject images to match roads
        if self.image_points_gdf.crs != self.roads_gdf.crs:
            self.image_points_gdf = self.image_points_gdf.to_crs(self.roads_gdf.crs)
            QgsMessageLog.logMessage(
                f"  Images reprojected to {self.roads_gdf.crs}", 
                "Road Image Linker", Qgis.Info
            )
    
    def find_closest_images_to_roads(self, max_distance=50):
        """
        Find the closest image for each road feature (one-to-one mapping)
        
        Args:
            max_distance (float): Maximum distance in meters to consider a match
            
        Returns:
            int: Number of successful matches
        """
        QgsMessageLog.logMessage(
            f"Finding closest images to roads (max distance: {max_distance}m)...", 
            "Road Image Linker", Qgis.Info
        )
        
        # Add image columns if they don't exist
        for col in ['Image_Path', 'Image_URI', 'Image_Name', 'Distance_m']:
            if col not in self.roads_gdf.columns:
                self.roads_gdf[col] = ''
        
        matches = []
        
        # For each road, find its closest image
        for road_idx, road_feature in self.roads_gdf.iterrows():
            # Calculate distances from this road to all images
            distances = self.image_points_gdf.geometry.distance(road_feature.geometry)
            
            if len(distances) == 0:
                continue
                
            min_distance = distances.min()
            closest_image_idx = distances.idxmin()
            
            # Only match if within maximum distance
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
        
        # Update roads with their closest images
        matched_roads = 0
        for match in matches:
            road_idx = match['road_idx']
            self.roads_gdf.at[road_idx, 'Image_Path'] = match['image_path']
            self.roads_gdf.at[road_idx, 'Image_URI'] = match['image_uri']
            self.roads_gdf.at[road_idx, 'Image_Name'] = match['image_name']
            self.roads_gdf.at[road_idx, 'Distance_m'] = round(match['distance'], 2)
            matched_roads += 1
        
        QgsMessageLog.logMessage(
            f"✓ Matched {matched_roads} roads to their closest images", 
            "Road Image Linker", Qgis.Info
        )
        
        # Print statistics if matches exist
        if matches:
            distances = [m['distance'] for m in matches]
            QgsMessageLog.logMessage(
                f"  Distance statistics: Min: {min(distances):.1f}m, Max: {max(distances):.1f}m, Mean: {np.mean(distances):.1f}m", 
                "Road Image Linker", Qgis.Info
            )
        
        # Report unmatched roads
        unmatched = len(self.roads_gdf) - matched_roads
        if unmatched > 0:
            QgsMessageLog.logMessage(
                f"  {unmatched} roads had no images within {max_distance}m", 
                "Road Image Linker", Qgis.Warning
            )
        
        return matched_roads
    
    def save_updated_shapefile(self, output_path):
        """
        Save the updated shapefile with image associations
        
        Args:
            output_path (str): Path for output shapefile
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert back to geographic CRS for output
            output_gdf = self.roads_gdf.to_crs('EPSG:4326')
            output_gdf.to_file(output_path)
            
            QgsMessageLog.logMessage(
                f"✓ Saved updated shapefile: {output_path}", 
                "Road Image Linker", Qgis.Info
            )
            
            return True
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"✗ Error saving shapefile: {e}", 
                "Road Image Linker", Qgis.Critical
            )
            return False
    
    def create_qgis_assets(self, output_dir):
        """
        Create QGIS project template and HTML tooltip template
        
        Args:
            output_dir (str): Directory to save QGIS assets
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # HTML Template for Map Tips (using URI format)
        html_template = '''<!DOCTYPE html>
<html>
<head>
    <style>
        body { 
            margin: 5px; 
            font-family: Arial, sans-serif; 
            background: #f9f9f9;
            border-radius: 5px;
            padding: 10px;
            max-width: 350px;
        }
        .header {
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
            border-bottom: 1px solid #ddd;
            padding-bottom: 5px;
        }
        .image-container { 
            text-align: center;
            margin: 10px 0;
        }
        .road-image { 
            max-width: 300px; 
            max-height: 200px; 
            border: 2px solid #007cba;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .image-info {
            font-size: 11px;
            color: #666;
            margin-top: 5px;
            background: white;
            padding: 5px;
            border-radius: 3px;
        }
        .distance {
            font-weight: bold;
            color: #007cba;
        }
        .no-image {
            color: #999;
            font-style: italic;
            text-align: center;
            padding: 20px;
        }
    </style>
</head>
<body>
    [% IF "Image_URI" != '' %]
        <div class="header">Road Crack Image</div>
        <div class="image-container">
            <img src="[% "Image_URI" %]" alt="Road crack image" class="road-image" onerror="this.style.display='none';">
            <div class="image-info">
                <div><strong>File:</strong> [% "Image_Name" %]</div>
                <div><strong>Distance:</strong> <span class="distance">[% "Distance_m" %]m</span></div>
            </div>
        </div>
    [% ELSE %]
        <div class="no-image">No image associated with this road segment</div>
    [% END %]
</body>
</html>'''
        
        html_file = output_dir / "image_tooltip_template.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_template)
        
        QgsMessageLog.logMessage(
            f"✓ Created HTML tooltip template: {html_file}", 
            "Road Image Linker", Qgis.Info
        )
    
    def generate_summary_report(self):
        """Generate a summary report of the linking process"""
        if self.roads_gdf is None:
            return
            
        total_roads = len(self.roads_gdf)
        linked_roads = len(self.roads_gdf[self.roads_gdf['Image_URI'] != ''])
        
        summary = f"""
ROAD-IMAGE LINKING SUMMARY
{'='*50}
Total road features:     {total_roads}
Roads with images:       {linked_roads}
Roads without images:    {total_roads - linked_roads}
Link success rate:       {(linked_roads/total_roads)*100:.1f}%
"""
        
        if linked_roads > 0:
            distances = self.roads_gdf[self.roads_gdf['Distance_m'] != '']['Distance_m'].astype(float)
            summary += f"""
Distance Statistics:
  Average distance:      {distances.mean():.1f}m
  Maximum distance:      {distances.max():.1f}m
  Minimum distance:      {distances.min():.1f}m
"""
        
        QgsMessageLog.logMessage(summary, "Road Image Linker", Qgis.Info)
    
    def run_complete_workflow(self, output_shapefile, max_distance=50):
        """
        Execute the complete road-image linking workflow
        
        Args:
            output_shapefile (str): Path for output shapefile
            max_distance (float): Maximum linking distance in meters
            
        Returns:
            bool: True if successful, False otherwise
        """
        QgsMessageLog.logMessage(
            "🚀 Starting Road-Image Linking Workflow", 
            "Road Image Linker", Qgis.Info
        )
        
        try:
            # Step 1: Load road shapefile
            if not self.load_road_shapefile():
                return False
                
            # Step 2: Extract image locations
            if not self.extract_image_locations():
                return False
                
            # Step 3: Reproject for accurate calculations
            self.reproject_data()
            
            # Step 4: Find closest images
            matches = self.find_closest_images_to_roads(max_distance)
            if matches == 0:
                QgsMessageLog.logMessage(
                    f"✗ No matches found within {max_distance}m. Try increasing max_distance.", 
                    "Road Image Linker", Qgis.Warning
                )
                return False
                
            # Step 5: Save results
            if not self.save_updated_shapefile(output_shapefile):
                return False
                
            # Step 6: Create QGIS assets
            output_dir = Path(output_shapefile).parent
            self.create_qgis_assets(output_dir)
            
            # Step 7: Generate summary
            self.generate_summary_report()
            
            QgsMessageLog.logMessage(
                "✅ Workflow completed successfully!", 
                "Road Image Linker", Qgis.Info
            )

            # Try to automatically setup QGIS map tips
            layer_name = Path(output_shapefile).stem
            html_path = str(Path(output_shapefile).parent / "image_tooltip_template.html")
            
            if setup_qgis_map_tips(layer_name, html_path):
                QgsMessageLog.logMessage(
                    "✓ QGIS map tips automatically configured", 
                    "Road Image Linker", Qgis.Info
                )
            else:
                QgsMessageLog.logMessage(
                    "! Could not configure QGIS map tips automatically", 
                    "Road Image Linker", Qgis.Warning
                )

            return True
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"✗ Workflow failed: {e}", 
                "Road Image Linker", Qgis.Critical
            )
            return False


def setup_qgis_map_tips(layer_name, html_template_path):
    """
    Configure QGIS map tips using PyQGIS
    
    Args:
        layer_name (str): Name of the layer in QGIS
        html_template_path (str): Path to HTML template file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from qgis.utils import iface
        
        # Convert to Path object and resolve absolute path
        html_path = Path(html_template_path).resolve()
        
        # Verify template exists
        if not html_path.exists():
            QgsMessageLog.logMessage(
                f"✗ HTML template not found: {html_path}", 
                "Road Image Linker", Qgis.Critical
            )
            return False
            
        # Get the layer
        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            QgsMessageLog.logMessage(
                f"✗ Layer '{layer_name}' not found in project", 
                "Road Image Linker", Qgis.Warning
            )
            return False
            
        layer = layers[0]
        
        try:
            # Read HTML template with explicit encoding
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        except Exception as e:
            QgsMessageLog.logMessage(
                f"✗ Error reading HTML template: {e}", 
                "Road Image Linker", Qgis.Critical
            )
            return False
        
        # Configure map tips
        layer.setMapTipTemplate(html_content)
        if iface:
            iface.actionShowMapTips().setChecked(True)
        
        QgsMessageLog.logMessage(
            f"✓ Map tips configured for layer: {layer_name}", 
            "Road Image Linker", Qgis.Info
        )
        return True
        
    except Exception as e:
        QgsMessageLog.logMessage(
            f"✗ Error setting up map tips: {e}", 
            "Road Image Linker", Qgis.Critical
        )
        return False


# Example usage when run as standalone script
if __name__ == "__main__":
    # This will only run when the script is executed directly, not when imported as a plugin
    try:
        # Configuration
        shapefile_path = "D:/Freelance Projects/Blue Ocean/Code/shapefile/cracking.shp"
        images_folder = "D:/Freelance Projects/Blue Ocean/Code/pcams"
        output_shapefile = "D:/Freelance Projects/Blue Ocean/Code/output/road_image_linked.shp"
        max_distance = 50  # meters
        
        # Create and run linker
        linker = RoadImageLinker(shapefile_path, images_folder)
        
        success = linker.run_complete_workflow(
            output_shapefile=output_shapefile,
            max_distance=max_distance
        )
        
        if success:
            print(f"\n📋 Next Steps for QGIS:")
            print(f"1. Open QGIS and load: {output_shapefile}")
            print(f"2. Right-click layer → Properties → Display")
            print(f"3. Enable 'HTML Map Tip' and the template will be automatically applied")
            print(f"4. Enable 'Show Map Tips' in View menu")
            print(f"5. Hover over road features to see associated images")
        else:
            print("\n❌ Workflow failed. Check QGIS message log for details.")
            
    except Exception as e:
        print(f"Error running standalone: {e}")
        print("This script is designed to run as a QGIS plugin or in QGIS Python environment.")