"""
PipeVision FBX Export Module
Converts DXF/DWG data to FBX format for use in:
- Unity
- Unreal Engine
- Blender
- 3ds Max
- Maya
- AR/VR applications

Uses Blender's Python API in headless mode for high-quality FBX export.
"""

import json
import logging
import subprocess
import tempfile
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from app.models.models import Asset, AssetType, ASSET_TYPE_COLORS
from app.processing.exporters import ExportOptions

logger = logging.getLogger(__name__)


# Blender Python script template for FBX export
BLENDER_FBX_SCRIPT = '''
import bpy
import json
import math
import sys

# Clear the default scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# Get the data file path from command line args
data_file = sys.argv[-2]
output_file = sys.argv[-1]

# Load asset data
with open(data_file, 'r') as f:
    data = json.load(f)

assets = data.get('assets', [])
options = data.get('options', {})

def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple (0-1 range)."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))

def create_pipe_segment(start, end, radius, name, color):
    """Create a cylinder (pipe segment) between two points."""
    
    # Calculate midpoint and direction
    mid = [(s + e) / 2 for s, e in zip(start, end)]
    direction = [e - s for s, e in zip(start, end)]
    length = math.sqrt(sum(d**2 for d in direction))
    
    if length < 0.001:
        return None
    
    # Create cylinder
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius,
        depth=length,
        location=mid,
        vertices=16
    )
    
    obj = bpy.context.active_object
    obj.name = name
    
    # Calculate rotation to align cylinder with direction
    # Default cylinder is along Z axis
    if length > 0:
        dx, dy, dz = [d / length for d in direction]
        
        # Calculate rotation angles
        # Rotation around X axis
        rot_x = math.atan2(math.sqrt(dx**2 + dy**2), dz)
        # Rotation around Z axis  
        rot_z = math.atan2(dy, dx) if abs(dx) > 0.001 or abs(dy) > 0.001 else 0
        
        obj.rotation_euler = (rot_x, 0, rot_z + math.pi/2)
    
    # Create and assign material with color
    mat = bpy.data.materials.new(name=f"{name}_material")
    mat.use_nodes = True
    
    # Get the principled BSDF node
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        rgb = hex_to_rgb(color)
        bsdf.inputs['Base Color'].default_value = (*rgb, 1.0)
        bsdf.inputs['Metallic'].default_value = 0.3
        bsdf.inputs['Roughness'].default_value = 0.6
    
    obj.data.materials.append(mat)
    
    return obj

def create_pipe_from_asset(asset_data, index):
    """Create a full pipe from asset data with multiple segments."""
    
    coords = asset_data.get('coordinates', [])
    if len(coords) < 2:
        return []
    
    asset_type = asset_data.get('type', 'unknown')
    color = asset_data.get('color', '#808080')
    radius = asset_data.get('diameter', 0.15) / 2
    depth_start = asset_data.get('depth_start', 1.5)
    depth_end = asset_data.get('depth_end', 1.5)
    label = asset_data.get('label', f'pipe_{index}')
    
    objects = []
    
    for i in range(len(coords) - 1):
        # Get start and end points
        start = coords[i]
        end = coords[i + 1]
        
        # Add Z coordinate (depth) if not present - negative because underground
        if len(start) == 2:
            start = [start[0], start[1], -depth_start]
        elif len(start) >= 3:
            start = [start[0], start[1], -abs(start[2]) if start[2] != 0 else -depth_start]
            
        if len(end) == 2:
            end = [end[0], end[1], -depth_end]
        elif len(end) >= 3:
            end = [end[0], end[1], -abs(end[2]) if end[2] != 0 else -depth_end]
        
        segment_name = f"{label}_segment_{i}"
        obj = create_pipe_segment(start, end, radius, segment_name, color)
        if obj:
            objects.append(obj)
    
    # Parent all segments to an empty for organization
    if objects:
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
        parent = bpy.context.active_object
        parent.name = label
        
        for obj in objects:
            obj.parent = parent
    
    return objects

# Process all assets
all_objects = []
for i, asset in enumerate(assets):
    objs = create_pipe_from_asset(asset, i)
    all_objects.extend(objs)

print(f"Created {len(all_objects)} pipe segments from {len(assets)} assets")

# Select all objects for export
bpy.ops.object.select_all(action='SELECT')

# Export to FBX
bpy.ops.export_scene.fbx(
    filepath=output_file,
    use_selection=False,
    global_scale=1.0,
    apply_unit_scale=True,
    apply_scale_options='FBX_SCALE_ALL',
    use_mesh_modifiers=True,
    mesh_smooth_type='FACE',
    use_mesh_edges=False,
    path_mode='AUTO',
    embed_textures=False,
    batch_mode='OFF',
    axis_forward='-Z',
    axis_up='Y'
)

print(f"Exported FBX to: {output_file}")
'''


class FBXExporter:
    """
    Export assets to FBX format using Blender.
    
    FBX is widely used in:
    - Unity game engine
    - Unreal Engine
    - Autodesk products (Maya, 3ds Max)
    - AR/VR applications
    """
    
    def __init__(self, options: Optional[ExportOptions] = None):
        self.options = options or ExportOptions()
        self.blender_path = self._find_blender()
    
    def _find_blender(self) -> Optional[str]:
        """Find Blender executable."""
        # Common Blender locations
        possible_paths = [
            'blender',  # If in PATH
            '/usr/bin/blender',
            '/usr/local/bin/blender',
            '/snap/bin/blender',
            '/Applications/Blender.app/Contents/MacOS/Blender',  # macOS
            'C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe',  # Windows
            'C:\\Program Files\\Blender Foundation\\Blender 3.6\\blender.exe',
            'C:\\Program Files\\Blender Foundation\\Blender\\blender.exe',
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run(
                    [path, '--version'],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    logger.info(f"Found Blender at: {path}")
                    return path
            except (subprocess.SubprocessError, FileNotFoundError, OSError):
                continue
        
        logger.warning("Blender not found - FBX export will use fallback method")
        return None
    
    def export(self, assets: List[Asset], output_path: str) -> bool:
        """
        Export assets to FBX format.
        
        Args:
            assets: List of Asset objects to export
            output_path: Path for the output FBX file
            
        Returns:
            True if successful
        """
        if self.blender_path:
            return self._export_with_blender(assets, output_path)
        else:
            return self._export_fallback(assets, output_path)
    
    def _export_with_blender(self, assets: List[Asset], output_path: str) -> bool:
        """Export using Blender in headless mode."""
        try:
            # Prepare asset data for Blender script
            asset_data = []
            for asset in assets:
                coords = self._extract_coordinates(asset)
                if not coords:
                    continue
                
                asset_data.append({
                    'coordinates': coords,
                    'type': asset.asset_type.value if asset.asset_type else 'unknown',
                    'color': asset.color or ASSET_TYPE_COLORS.get(asset.asset_type, '#808080'),
                    'diameter': asset.diameter or self.options.default_diameter,
                    'depth_start': asset.depth_start or self.options.default_depth,
                    'depth_end': asset.depth_end or self.options.default_depth,
                    'label': asset.label or f"pipe_{asset.id}",
                })
            
            if not asset_data:
                logger.warning("No valid assets to export")
                return False
            
            # Create temporary files
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as data_file:
                json.dump({
                    'assets': asset_data,
                    'options': {
                        'default_depth': self.options.default_depth,
                        'default_diameter': self.options.default_diameter,
                    }
                }, data_file)
                data_path = data_file.name
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as script_file:
                script_file.write(BLENDER_FBX_SCRIPT)
                script_path = script_file.name
            
            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Run Blender
            result = subprocess.run(
                [
                    self.blender_path,
                    '--background',
                    '--python', script_path,
                    '--', data_path, output_path
                ],
                capture_output=True,
                timeout=120  # 2 minute timeout
            )
            
            # Clean up temp files
            os.unlink(data_path)
            os.unlink(script_path)
            
            if result.returncode != 0:
                logger.error(f"Blender export failed: {result.stderr.decode()}")
                return False
            
            logger.info(f"Exported {len(asset_data)} assets to FBX: {output_path}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("Blender export timed out")
            return False
        except Exception as e:
            logger.exception(f"FBX export failed: {e}")
            return False
    
    def _export_fallback(self, assets: List[Asset], output_path: str) -> bool:
        """
        Fallback export when Blender is not available.
        Uses trimesh to create an intermediate format, then converts.
        """
        try:
            import trimesh
            import numpy as np
            
            logger.info("Using trimesh fallback for FBX export")
            
            meshes = []
            
            for asset in assets:
                mesh = self._asset_to_mesh(asset)
                if mesh:
                    meshes.append(mesh)
            
            if not meshes:
                logger.warning("No meshes generated for FBX export")
                return False
            
            # Combine all meshes
            combined = trimesh.util.concatenate(meshes)
            
            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Try to export as FBX (may require additional dependencies)
            # If FBX fails, export as glTF which can be converted
            try:
                combined.export(output_path, file_type='fbx')
            except Exception:
                # Fallback to OBJ which is widely compatible
                obj_path = output_path.replace('.fbx', '.obj')
                combined.export(obj_path)
                logger.warning(f"FBX not available, exported as OBJ: {obj_path}")
                return True
            
            logger.info(f"Exported {len(meshes)} assets to FBX: {output_path}")
            return True
            
        except ImportError:
            logger.error("trimesh not installed - cannot export FBX")
            return False
        except Exception as e:
            logger.exception(f"FBX fallback export failed: {e}")
            return False
    
    def _asset_to_mesh(self, asset: Asset):
        """Convert an asset to a 3D mesh (pipe/cylinder)."""
        try:
            import trimesh
            import numpy as np
            
            coords = self._extract_coordinates(asset)
            if len(coords) < 2:
                return None
            
            radius = (asset.diameter or self.options.default_diameter) / 2
            color = self._hex_to_rgba(
                asset.color or ASSET_TYPE_COLORS.get(asset.asset_type, '#808080')
            )
            
            segments = []
            
            for i in range(len(coords) - 1):
                start = np.array(coords[i], dtype=float)
                end = np.array(coords[i + 1], dtype=float)
                
                # Add depth as Z coordinate
                if len(start) == 2:
                    start = np.append(start, -(asset.depth_start or self.options.default_depth))
                if len(end) == 2:
                    end = np.append(end, -(asset.depth_end or self.options.default_depth))
                
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
        
        direction = end - start
        length = np.linalg.norm(direction)
        
        if length < 0.001:
            return None
        
        cylinder = trimesh.creation.cylinder(
            radius=radius,
            height=length,
            sections=12
        )
        
        direction_normalized = direction / length
        z_axis = np.array([0, 0, 1])
        
        rotation_axis = np.cross(z_axis, direction_normalized)
        rotation_axis_norm = np.linalg.norm(rotation_axis)
        
        if rotation_axis_norm > 0.001:
            rotation_axis = rotation_axis / rotation_axis_norm
            angle = np.arccos(np.clip(np.dot(z_axis, direction_normalized), -1, 1))
            
            rotation_matrix = trimesh.transformations.rotation_matrix(
                angle, rotation_axis
            )
            cylinder.apply_transform(rotation_matrix)
        
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


def export_fbx(assets: List[Asset], output_path: str, **kwargs) -> bool:
    """Export assets to FBX format."""
    options = ExportOptions(**kwargs) if kwargs else None
    exporter = FBXExporter(options)
    return exporter.export(assets, output_path)
