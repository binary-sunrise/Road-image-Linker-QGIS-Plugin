import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
from qgis.core import QgsMessageLog, Qgis
from pathlib import Path
from qgis.PyQt.QtCore import pyqtSignal, QObject
from ..utils.file_handler import FileHandler
from ..utils.progress import ProgressHandler, ProgressStep

class ExcelToShapefileConverter(QObject):
    progress_signal = pyqtSignal(int, str)
    
    def __init__(self, progress_dialog=None):
        super().__init__()
        self.file_handler = FileHandler()
        self.progress_handler = ProgressHandler(progress_dialog)
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
    
    def validate_excel(self, excel_path):
        """Validate Excel file contents"""
        try:
            # Use FileHandler to validate file
            valid, msg = self.file_handler.validate_file_exists(excel_path, '.xlsx')
            if not valid:
                return False, msg, None
                
            df = pd.read_excel(excel_path)
            
            # Check required columns
            missing_cols = [col for col in self.required_columns if col not in df.columns]
            if missing_cols:
                return False, f"Missing required columns: {', '.join(missing_cols)}", None
                
            # Validate data types
            type_errors = []
            for col, expected_type in self.required_columns.items():
                if not pd.api.types.is_numeric_dtype(df[col]) and expected_type == float:
                    type_errors.append(f"{col} should be numeric")
            
            if type_errors:
                return False, f"Data type issues: {', '.join(type_errors)}", None
            
            return True, "Excel file validated successfully", df
            
        except Exception as e:
            return False, f"Error reading Excel file: {str(e)}", None
    
    def convert_to_shapefile(self, df, output_path):
        """Convert Excel data to shapefile"""
        try:
            # Define workflow steps
            steps = [
                ProgressStep(45, "Creating geometries..."),
                ProgressStep(70, "Creating GeoDataFrame..."),
                ProgressStep(80, "Saving shapefile..."),
                ProgressStep(90, "Shapefile created successfully")
            ]

            # Create geometries
            geometries = []
            total_rows = len(df)
            
            for i, (_, row) in enumerate(df.iterrows()):
                start_point = (row['StartingLongitude'], row['StartingLatitude'])
                end_point = (row['EndingLongitude'], row['EndingLatitude'])
                geometries.append(LineString([start_point, end_point]))
                
                # Update progress every 10 rows
                if i % 10 == 0:
                    progress = 45 + int((i / total_rows) * 25)
                    self.progress_handler.update(progress, f"Processing row {i+1} of {total_rows}...")
            
            # Create GeoDataFrame
            gdf = gpd.GeoDataFrame(df, geometry=geometries, crs='EPSG:4326')
            
            # Ensure output directory exists
            self.file_handler.create_directory(Path(output_path).parent)
            
            # Convert output path
            output_path = self.file_handler.get_output_shapefile_path(output_path)
            
            # Save the file
            gdf.to_file(output_path)
            
            return True, f"Shapefile created: {output_path}"
            
        except Exception as e:
            error_msg = f"Error creating shapefile: {str(e)}"
            self.progress_handler.update(0, error_msg)
            return False, error_msg

    def process_excel(self, excel_path, output_shapefile):
        """Process Excel file and convert to shapefile"""
        workflow_steps = [
            ProgressStep(0, "Starting Excel conversion..."),
            ProgressStep(15, "Validating Excel file..."),
            ProgressStep(30, "Reading Excel data..."),
            ProgressStep(45, "Creating geometries..."),
            ProgressStep(70, "Building shapefile..."),
            ProgressStep(90, "Saving shapefile..."),
            ProgressStep(100, "Conversion complete!")
        ]
        
        try:
            self.progress_handler.update(workflow_steps[0].value, workflow_steps[0].message)
            
            # Validate Excel file
            self.progress_handler.update(workflow_steps[1].value, workflow_steps[1].message)
            valid, msg, df = self.validate_excel(excel_path)
            if not valid:
                return False, msg
            
            # Read Excel data
            self.progress_handler.update(workflow_steps[2].value, workflow_steps[2].message)
            
            # Create geometries
            self.progress_handler.update(workflow_steps[3].value, workflow_steps[3].message)
            geometries = []
            total_rows = len(df)
            
            for i, (_, row) in enumerate(df.iterrows()):
                start_point = (row['StartingLongitude'], row['StartingLatitude'])
                end_point = (row['EndingLongitude'], row['EndingLatitude'])
                geometries.append(LineString([start_point, end_point]))
                
                # Update progress every 10 rows
                if i % 10 == 0:
                    progress = workflow_steps[3].value + int((i / total_rows) * 25)
                    self.progress_handler.update(progress, f"Processing row {i+1} of {total_rows}...")
            
            # Create GeoDataFrame
            self.progress_handler.update(workflow_steps[4].value, workflow_steps[4].message)
            gdf = gpd.GeoDataFrame(df, geometry=geometries, crs='EPSG:4326')
            
            # Ensure output directory exists
            output_path = self.file_handler.get_output_shapefile_path(output_shapefile)
            self.file_handler.create_directory(Path(output_path).parent)
            
            # Save the file
            self.progress_handler.update(workflow_steps[5].value, workflow_steps[5].message)
            gdf.to_file(output_path)
            
            # Complete
            self.progress_handler.update(workflow_steps[6].value, workflow_steps[6].message)
            return True, f"Shapefile created successfully: {output_path}"
            
        except Exception as e:
            error_msg = f"Error processing Excel file: {str(e)}"
            self.progress_handler.update(0, error_msg)
            return False, error_msg