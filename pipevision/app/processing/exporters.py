"""
PipeVision Export Module
Converts processed DWG data to AR/GIS-ready formats

Supported formats:
- GeoJSON: Standard for web mapping and AR platforms
- glTF/GLB: 3D model format for AR viewers
- CSV: Simple lat/lon/depth for spreadsheet users
- KML: Google Earth compatibility
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
import math

from pyproj import Transformer, CRS

from app.models.models import Asset, AssetType, ASSET_TYPE_COLORS


logger = logging.getLogger(__name__)


@dataclass
class ExportOptions:
    """Options for export generation."""
    source_crs: str = "EPSG:4326"  # Input coordinate system
    target_crs: str = "EPSG:4326"  # Output coordinate system (WGS84 for AR)
    include_properties: bool = True
    include_depth: bool = True
    default_depth: float = 1.5  # Default depth in meters if not specified
    default_diameter: float = 0.15  # Default pipe diameter in meters
    precision: int = 8  # Coordinate decimal places


class GeoJSONExporter:
    """
    Export assets to GeoJSON format.
    
    GeoJSON is the standard format for:
    - VirtualGIS Pro Vision AR
    - Mapbox
    - Leaflet
    - Most web mapping libraries
    """
    
    def __init__(self, options: Optional[ExportOptions] = None):
        self.options = options or ExportOptions()
        self._init_transformer()
    
    def _init_transformer(self):
        """Initialize coordinate transformer if CRS conversion needed."""
        if self.options.source_crs != self.options.target_crs:
            self.transformer = Transformer.from_crs(
                CRS.from_string(self.options.source_crs),
                CRS.from_string(self.options.target_crs),
                always_xy=True
            )
        else:
            self.transformer = None
    
    def export(self, assets: List[Asset], output_path: str) -> bool:
        """
        Export assets to GeoJSON file.
        
        Args:
            assets: List of Asset objects to export
            output_path: Path for the output file
            
        Returns:
            True if successful
        """
        try:
            features = []
            
            for asset in assets:
                feature = self._asset_to_feature(asset)
                if feature:
                    features.append(feature)
            
            geojson = {
                "type": "FeatureCollection",
                "features": features,
                "metadata": {
                    "generator": "PipeVision",
                    "version": "0.1.0",
                    "crs": self.options.target_crs,
                    "asset_count": len(features),
                }
            }
            
            # Write to file
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(geojson, f, indent=2)
            
            logger.info(f"Exported {len(features)} assets to {output_path}")
            return True
            
        except Exception as e:
            logger.exception(f"GeoJSON export failed: {e}")
            return False
    
    def _asset_to_feature(self, asset: Asset) -> Optional[Dict[str, Any]]:
        """Convert a single asset to a GeoJSON feature."""
        try:
            # Get coordinates from geometry
            # This would normally extract from PostGIS geometry
            # For now, we'll assume coordinates are stored in a JSON field
            coords = self._extract_coordinates(asset)
            if not coords:
                return None
            
            # Transform coordinates if needed
            if self.transformer:
                coords = [
                    self._transform_coord(c) for c in coords
                ]
            
            # Round coordinates
            coords = [
                [round(c[0], self.options.precision), 
                 round(c[1], self.options.precision),
                 round(c[2], self.options.precision) if len(c) > 2 else 0]
                for c in coords
            ]
            
            # Build geometry
            if len(coords) == 1:
                geometry = {
                    "type": "Point",
                    "coordinates": coords[0]
                }
            else:
                geometry = {
                    "type": "LineString",
                    "coordinates": coords
                }
            
            # Build properties
            properties = {
                "id": str(asset.id),
                "type": asset.asset_type.value if asset.asset_type else "unknown",
                "label": asset.label or "",
                "layer": asset.layer_name or "",
                "color": asset.color or ASSET_TYPE_COLORS.get(asset.asset_type, "#808080"),
            }
            
            if self.options.include_depth:
                properties["depth_start"] = asset.depth_start or self.options.default_depth
                properties["depth_end"] = asset.depth_end or self.options.default_depth
                properties["depth_unit"] = asset.depth_unit or "meters"
            
            if self.options.include_properties:
                properties["diameter"] = asset.diameter or self.options.default_diameter
                properties["diameter_unit"] = asset.diameter_unit or "meters"
                properties["material"] = asset.material or ""
            
            return {
                "type": "Feature",
                "geometry": geometry,
                "properties": properties,
            }
            
        except Exception as e:
            logger.warning(f"Failed to convert asset {asset.id}: {e}")
            return None
    
    def _extract_coordinates(self, asset: Asset) -> List[List[float]]:
        """Extract coordinates from asset geometry."""
        # In a real implementation, this would use PostGIS functions
        # For now, we'll check if there's a stored coordinate list
        if hasattr(asset, 'coordinates') and asset.coordinates:
            return asset.coordinates
        
        # Try to extract from original_properties
        if asset.original_properties and 'points' in asset.original_properties:
            return asset.original_properties['points']
        
        return []
    
    def _transform_coord(self, coord: List[float]) -> List[float]:
        """Transform a single coordinate."""
        if self.transformer and len(coord) >= 2:
            x, y = self.transformer.transform(coord[0], coord[1])
            z = coord[2] if len(coord) > 2 else 0
            return [x, y, z]
        return coord


class CSVExporter:
    """
    Export assets to CSV format.
    
    Simple format for users who need to work with spreadsheets
    or import into legacy systems.
    """
    
    def __init__(self, options: Optional[ExportOptions] = None):
        self.options = options or ExportOptions()
    
    def export(self, assets: List[Asset], output_path: str) -> bool:
        """Export assets to CSV file."""
        try:
            import csv
            
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "w", newline="") as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow([
                    "id", "type", "label", "layer",
                    "start_lat", "start_lon", "start_depth",
                    "end_lat", "end_lon", "end_depth",
                    "diameter", "material", "color"
                ])
                
                # Data rows
                for asset in assets:
                    coords = self._extract_coordinates(asset)
                    if not coords:
                        continue
                    
                    start = coords[0] if coords else [0, 0, 0]
                    end = coords[-1] if len(coords) > 1 else start
                    
                    writer.writerow([
                        str(asset.id),
                        asset.asset_type.value if asset.asset_type else "unknown",
                        asset.label or "",
                        asset.layer_name or "",
                        start[1] if len(start) > 1 else 0,  # lat
                        start[0] if len(start) > 0 else 0,  # lon
                        start[2] if len(start) > 2 else asset.depth_start or 0,
                        end[1] if len(end) > 1 else 0,
                        end[0] if len(end) > 0 else 0,
                        end[2] if len(end) > 2 else asset.depth_end or 0,
                        asset.diameter or "",
                        asset.material or "",
                        asset.color or "",
                    ])
            
            logger.info(f"Exported {len(assets)} assets to CSV: {output_path}")
            return True
            
        except Exception as e:
            logger.exception(f"CSV export failed: {e}")
            return False
    
    def _extract_coordinates(self, asset: Asset) -> List[List[float]]:
        """Extract coordinates from asset."""
        if hasattr(asset, 'coordinates') and asset.coordinates:
            return asset.coordinates
        if asset.original_properties and 'points' in asset.original_properties:
            return asset.original_properties['points']
        return []


class GLTFExporter:
    """
    Export assets to glTF/GLB format for 3D visualization.
    
    glTF is the standard for:
    - AR viewers (ARKit, ARCore)
    - 3D web viewers (Three.js)
    - Game engines
    """
    
    def __init__(self, options: Optional[ExportOptions] = None):
        self.options = options or ExportOptions()
    
    def export(self, assets: List[Asset], output_path: str) -> bool:
        """
        Export assets to glTF format.
        
        Creates 3D pipe geometry from 2D lines with depth information.
        """
        try:
            import trimesh
            import numpy as np
            
            meshes = []
            
            for asset in assets:
                mesh = self._asset_to_mesh(asset)
                if mesh:
                    meshes.append(mesh)
            
            if not meshes:
                logger.warning("No meshes generated for glTF export")
                return False
            
            # Combine all meshes
            combined = trimesh.util.concatenate(meshes)
            
            # Export
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            combined.export(output_path)
            
            logger.info(f"Exported {len(meshes)} assets to glTF: {output_path}")
            return True
            
        except ImportError:
            logger.error("trimesh not installed - cannot export glTF")
            return False
        except Exception as e:
            logger.exception(f"glTF export failed: {e}")
            return False
    
    def _asset_to_mesh(self, asset: Asset):
        """Convert an asset to a 3D mesh (pipe/cylinder)."""
        try:
            import trimesh
            import numpy as np
            
            coords = self._extract_coordinates(asset)
            if len(coords) < 2:
                return None
            
            # Get pipe properties
            radius = (asset.diameter or self.options.default_diameter) / 2
            color = self._hex_to_rgba(
                asset.color or ASSET_TYPE_COLORS.get(asset.asset_type, "#808080")
            )
            
            segments = []
            
            # Create cylinder for each segment
            for i in range(len(coords) - 1):
                start = np.array(coords[i])
                end = np.array(coords[i + 1])
                
                # Use depth as Z coordinate (negative because underground)
                if len(start) == 2:
                    start = np.append(start, -(asset.depth_start or self.options.default_depth))
                if len(end) == 2:
                    end = np.append(end, -(asset.depth_end or self.options.default_depth))
                
                # Create cylinder between points
                segment = self._create_cylinder(start, end, radius)
                if segment:
                    segment.visual.vertex_colors = color
                    segments.append(segment)
            
            if segments:
                return trimesh.util.concatenate(segments)
            return None
            
        except Exception as e:
            logger.warning(f"Failed to create mesh for asset: {e}")
            return None
    
    def _create_cylinder(self, start: 'np.ndarray', end: 'np.ndarray', radius: float):
        """Create a cylinder mesh between two points."""
        import trimesh
        import numpy as np
        
        # Vector from start to end
        direction = end - start
        length = np.linalg.norm(direction)
        
        if length < 0.001:
            return None
        
        # Create cylinder along Z axis
        cylinder = trimesh.creation.cylinder(
            radius=radius,
            height=length,
            sections=8
        )
        
        # Calculate rotation to align with direction
        direction_normalized = direction / length
        z_axis = np.array([0, 0, 1])
        
        # Rotation axis and angle
        rotation_axis = np.cross(z_axis, direction_normalized)
        rotation_axis_norm = np.linalg.norm(rotation_axis)
        
        if rotation_axis_norm > 0.001:
            rotation_axis = rotation_axis / rotation_axis_norm
            angle = np.arccos(np.clip(np.dot(z_axis, direction_normalized), -1, 1))
            
            # Create rotation matrix
            rotation_matrix = trimesh.transformations.rotation_matrix(
                angle, rotation_axis
            )
            cylinder.apply_transform(rotation_matrix)
        
        # Translate to midpoint
        midpoint = (start + end) / 2
        cylinder.apply_translation(midpoint)
        
        return cylinder
    
    def _hex_to_rgba(self, hex_color: str) -> list:
        """Convert hex color to RGBA."""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return [r, g, b, 255]
    
    def _extract_coordinates(self, asset: Asset) -> List[List[float]]:
        """Extract coordinates from asset."""
        if hasattr(asset, 'coordinates') and asset.coordinates:
            return asset.coordinates
        if asset.original_properties and 'points' in asset.original_properties:
            return asset.original_properties['points']
        return []


# Convenience functions
def export_geojson(assets: List[Asset], output_path: str, **kwargs) -> bool:
    """Export assets to GeoJSON."""
    options = ExportOptions(**kwargs) if kwargs else None
    exporter = GeoJSONExporter(options)
    return exporter.export(assets, output_path)


def export_csv(assets: List[Asset], output_path: str, **kwargs) -> bool:
    """Export assets to CSV."""
    options = ExportOptions(**kwargs) if kwargs else None
    exporter = CSVExporter(options)
    return exporter.export(assets, output_path)


def export_gltf(assets: List[Asset], output_path: str, **kwargs) -> bool:
    """Export assets to glTF."""
    options = ExportOptions(**kwargs) if kwargs else None
    exporter = GLTFExporter(options)
    return exporter.export(assets, output_path)
