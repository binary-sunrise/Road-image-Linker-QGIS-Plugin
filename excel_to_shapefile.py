import os
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
from qgis.core import QgsMessageLog, Qgis
from pathlib import Path

class ExcelToShapefileConverter:
    """
    Converts Excel road data to a shapefile with line geometries
    """
    
    def __init__(self):
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
        """
        Validate the Excel file structure and content
        
        Args:
            excel_path (str): Path to Excel file
            
        Returns:
            tuple: (bool success, str message, DataFrame data)
        """
        try:
            if not Path(excel_path).exists():
                return False, f"Excel file not found: {excel_path}", None
                
            # Read Excel file
            df = pd.read_excel(excel_path)
            
            # Check required columns
            missing_cols = [col for col in self.required_columns if col not in df.columns]
            if missing_cols:
                return False, f"Missing required columns: {', '.join(missing_cols)}", None
                
            # Check data types
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
        """
        Convert validated DataFrame to shapefile
        
        Args:
            df (DataFrame): Validated road data
            output_path (str): Output shapefile path
            
        Returns:
            tuple: (bool success, str message)
        """
        try:
            # Create line geometries
            geometries = []
            for _, row in df.iterrows():
                start_point = (row['StartingLongitude'], row['StartingLatitude'])
                end_point = (row['EndingLongitude'], row['EndingLatitude'])
                geometries.append(LineString([start_point, end_point]))
            
            # Create GeoDataFrame
            gdf = gpd.GeoDataFrame(
                df,
                geometry=geometries,
                crs='EPSG:4326'  # WGS84
            )
            
            # Ensure output directory exists
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save shapefile
            gdf.to_file(output_path)
            
            QgsMessageLog.logMessage(
                f"Successfully created shapefile: {output_path}",
                "Excel Converter", Qgis.Info
            )
            
            return True, f"Shapefile created: {output_path}"
            
        except Exception as e:
            error_msg = f"Error creating shapefile: {str(e)}"
            QgsMessageLog.logMessage(
                error_msg,
                "Excel Converter", Qgis.Critical
            )
            return False, error_msg

    def process_excel(self, excel_path, output_shapefile):
        """
        Complete workflow from Excel to shapefile
        
        Args:
            excel_path (str): Input Excel file path
            output_shapefile (str): Output shapefile path
            
        Returns:
            tuple: (bool success, str message)
        """
        # Validate Excel
        valid, msg, df = self.validate_excel(excel_path)
        if not valid:
            return False, msg
            
        # Convert to shapefile
        return self.convert_to_shapefile(df, output_shapefile)