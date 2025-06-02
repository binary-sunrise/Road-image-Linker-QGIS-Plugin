"""File handling utilities for Road Image Linker plugin."""
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import pathname2url
from typing import Union, Optional

class FileHandler:
    """Centralized file handling for the plugin."""
    
    @staticmethod
    def ensure_path(path: Union[str, Path]) -> Path:
        """Convert string path to Path object."""
        return Path(path) if isinstance(path, str) else path
    
    @staticmethod
    def create_directory(path: Union[str, Path]) -> Path:
        """Create directory if it doesn't exist."""
        path = FileHandler.ensure_path(path)
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @staticmethod
    def path_to_uri(file_path: Union[str, Path]) -> str:
        """Convert file path to URI."""
        abs_path = FileHandler.ensure_path(file_path).resolve()
        return urljoin('file:', pathname2url(str(abs_path)))
    
    @staticmethod
    def validate_file_exists(file_path: Union[str, Path], extension: Optional[str] = None) -> tuple[bool, str]:
        """Validate that file exists and has correct extension."""
        path = FileHandler.ensure_path(file_path)
        
        if not path.exists():
            return False, f"File not found: {path}"
            
        if extension and path.suffix.lower() != extension.lower():
            return False, f"File must have {extension} extension"
            
        return True, "File validation successful"
    
    @staticmethod
    def get_output_shapefile_path(path: Union[str, Path]) -> Path:
        """Ensure shapefile path has .shp extension."""
        path = FileHandler.ensure_path(path)
        if not path.suffix.lower() == '.shp':
            path = path.with_suffix('.shp')
        return path
