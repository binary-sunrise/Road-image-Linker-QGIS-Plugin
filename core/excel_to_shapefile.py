import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
from qgis.core import QgsMessageLog, Qgis
from pathlib import Path
from qgis.PyQt.QtCore import pyqtSignal, QObject

class ExcelToShapefileConverter(QObject):
    progress_signal = pyqtSignal(int, str)
    
    def __init__(self, progress_dialog=None):
        super().__init__()
        self.progress_dialog = progress_dialog
        self.required_columns = {
            'StartChainage': float,
            'StartingLatitude': float,
            'StartingLongitude': float,
            'EndingLatitude': float,
            'EndingLongitude': float
        }
        self.optional_columns = {
            'NHNumber': str,
            'LaneNumber': str
        }
    
    def update_progress(self, value, message):
        if self.progress_dialog:
            self.progress_dialog.set_progress(value, message)
        self.progress_signal.emit(value, message)
    
    def validate_excel(self, excel_path):
        try:
            self.update_progress(15, "Validating Excel file...")
            
            if not Path(excel_path).exists():
                return False, f"Excel file not found: {excel_path}", None
                
            self.update_progress(20, "Reading Excel data...")
            df = pd.read_excel(excel_path)
            
            self.update_progress(25, "Checking columns...")
            missing_cols = [col for col in self.required_columns if col not in df.columns]
            if missing_cols:
                return False, f"Missing required columns: {', '.join(missing_cols)}", None
                
            self.update_progress(30, "Validating data types...")
            type_errors = []
            for col, expected_type in self.required_columns.items():
                if not pd.api.types.is_numeric_dtype(df[col]) and expected_type == float:
                    type_errors.append(f"{col} should be numeric")
            
            if type_errors:
                return False, f"Data type issues: {', '.join(type_errors)}", None
                
            self.update_progress(40, "Excel validation complete")
            return True, "Excel file validated successfully", df
            
        except Exception as e:
            return False, f"Error reading Excel file: {str(e)}", None
    
    def convert_to_shapefile(self, df, output_path):
        try:
            self.update_progress(45, "Creating geometries...")
            geometries = []
            total_rows = len(df)
            
            for i, (_, row) in enumerate(df.iterrows()):
                start_point = (row['StartingLongitude'], row['StartingLatitude'])
                end_point = (row['EndingLongitude'], row['EndingLatitude'])
                geometries.append(LineString([start_point, end_point]))
                
                # Update progress every 10 rows
                if i % 10 == 0:
                    progress = 45 + int((i / total_rows) * 45)
                    self.update_progress(progress, f"Processing row {i+1} of {total_rows}...")
            
            self.update_progress(70, "Creating GeoDataFrame...")
            gdf = gpd.GeoDataFrame(
                df,
                geometry=geometries,
                crs='EPSG:4326'
            )
            
            self.update_progress(80, "Saving shapefile...")
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            gdf.to_file(output_path)
            
            self.update_progress(90, "Shapefile created successfully")
            return True, f"Shapefile created: {output_path}"
            
        except Exception as e:
            error_msg = f"Error creating shapefile: {str(e)}"
            self.update_progress(0, error_msg)
            return False, error_msg

    def process_excel(self, excel_path, output_shapefile):
        valid, msg, df = self.validate_excel(excel_path)
        if not valid:
            return False, msg
            
        return self.convert_to_shapefile(df, output_shapefile)