"""Configuration module for Road Image Linker plugin."""
from pathlib import Path

# Configuration for the Road Image Linker plugin
# Centralizes all configurable parameters in one place

class Config:
    # File extensions
    SUPPORTED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif'}
    
    # CRS settings
    DEFAULT_CRS = 'EPSG:3857'
    GEOGRAPHIC_CRS = 'EPSG:4326'
    
    # Default values
    DEFAULT_MAX_DISTANCE = 50  # meters
    
    # Required Excel columns with their types
    REQUIRED_EXCEL_COLUMNS = {
        'StartChainage': float,
        'StartingLatitude': float,
        'StartingLongitude': float,
        'EndingLatitude': float,
        'EndingLongitude': float
    }
    
    # Optional Excel columns
    OPTIONAL_EXCEL_COLUMNS = {
        'NHNumber': str,
        'LaneNumber': str
    }
    
    @staticmethod
    def get_locale_path(plugin_dir: str, locale: str) -> Path:
        """Get the path to locale files."""
        return Path(plugin_dir) / 'i18n' / f'RoadImageLinker_{locale}.qm'
    
    @staticmethod
    def get_html_template_path(output_dir: str) -> Path:
        """Get the path to HTML template file."""
        return Path(output_dir) / "image_tooltip_template.html"
