"""
PipeVision DWG/DXF Parser
Core processing engine for extracting geometry and metadata from CAD files

Uses:
- ODA File Converter: DWG → DXF conversion (free, requires installation)
- ezdxf: DXF parsing and analysis (pure Python)
"""

import os
import subprocess
import tempfile
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
import json

import ezdxf
from ezdxf.entities import Line, LWPolyline, Polyline, Circle, Arc, Insert
from ezdxf.math import Vec3

from app.core.config import settings


logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    """Represents a single extracted entity from the DWG/DXF."""
    handle: str
    entity_type: str
    layer: str
    points: List[Tuple[float, float, float]]  # List of (x, y, z) coordinates
    properties: Dict[str, Any] = field(default_factory=dict)
    
    # Detected/inferred properties
    suggested_type: Optional[str] = None  # "sewer", "gas", etc.
    has_depth: bool = False
    depth_values: List[float] = field(default_factory=list)


@dataclass
class ParseResult:
    """Result of parsing a DWG/DXF file."""
    success: bool
    filename: str
    
    # File info
    dxf_version: Optional[str] = None
    units: Optional[str] = None
    
    # Detected metadata
    has_crs: bool = False
    detected_crs: Optional[str] = None
    has_depth: bool = False
    has_rotation: bool = False
    rotation_degrees: float = 0.0
    
    # Layers and entities
    layers: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[ExtractedEntity] = field(default_factory=list)
    
    # Bounding box
    min_x: Optional[float] = None
    min_y: Optional[float] = None
    max_x: Optional[float] = None
    max_y: Optional[float] = None
    
    # What's missing (for validation wizard)
    missing_fields: List[str] = field(default_factory=list)
    
    # Errors/warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class DWGParser:
    """
    Parser for DWG/DXF files.
    
    Workflow:
    1. If DWG: Convert to DXF using ODA File Converter
    2. Parse DXF with ezdxf
    3. Extract geometry, layers, and metadata
    4. Detect missing information
    5. Return structured result
    """
    
    # Keywords that suggest asset types (case-insensitive)
    ASSET_TYPE_KEYWORDS = {
        "sewer": ["sewer", "san", "sanitary", "ss", "swr"],
        "storm": ["storm", "drain", "sd", "stm", "drainage"],
        "potable": ["water", "potable", "wtr", "wm", "domestic"],
        "gas": ["gas", "natural", "ng", "fuel"],
        "electric": ["electric", "elec", "power", "hv", "lv", "mv"],
        "telecom": ["telecom", "telephone", "tel", "comm", "cable"],
        "fiber": ["fiber", "fibre", "fo", "optical"],
    }
    
    def __init__(self):
        self.oda_path = settings.ODA_CONVERTER_PATH
    
    def parse(self, file_path: str) -> ParseResult:
        """
        Parse a DWG or DXF file and extract all relevant information.
        
        Args:
            file_path: Path to the DWG or DXF file
            
        Returns:
            ParseResult with all extracted data and detected issues
        """
        file_path = Path(file_path)
        result = ParseResult(success=False, filename=file_path.name)
        
        if not file_path.exists():
            result.errors.append(f"File not found: {file_path}")
            return result
        
        try:
            # Convert DWG to DXF if necessary
            if file_path.suffix.lower() == ".dwg":
                dxf_path = self._convert_dwg_to_dxf(file_path)
                if dxf_path is None:
                    result.errors.append("Failed to convert DWG to DXF")
                    return result
            else:
                dxf_path = file_path
            
            # Parse the DXF file
            doc = ezdxf.readfile(str(dxf_path))
            
            # Extract basic info
            result.dxf_version = doc.dxfversion
            result.units = self._get_units(doc)
            
            # Extract layers
            result.layers = self._extract_layers(doc)
            
            # Extract entities
            result.entities = self._extract_entities(doc)
            
            # Calculate bounding box
            self._calculate_bounds(result)
            
            # Detect CRS from file
            result.has_crs, result.detected_crs = self._detect_crs(doc)
            
            # Check for depth information
            result.has_depth = self._check_depth(result.entities)
            
            # Detect rotation (from north arrow or metadata)
            result.has_rotation, result.rotation_degrees = self._detect_rotation(doc)
            
            # Determine what's missing
            result.missing_fields = self._determine_missing_fields(result)
            
            # Try to auto-classify entities
            self._classify_entities(result.entities, result.layers)
            
            result.success = True
            
            # Cleanup temp file if we converted
            if file_path.suffix.lower() == ".dwg" and dxf_path != file_path:
                try:
                    os.remove(dxf_path)
                except:
                    pass
                    
        except ezdxf.DXFError as e:
            result.errors.append(f"DXF parsing error: {str(e)}")
        except Exception as e:
            result.errors.append(f"Unexpected error: {str(e)}")
            logger.exception("Error parsing file")
        
        return result
    
    def _convert_dwg_to_dxf(self, dwg_path: Path) -> Optional[Path]:
        """
        Convert DWG to DXF using ODA File Converter.
        
        ODA File Converter command:
        ODAFileConverter <input_folder> <output_folder> <output_version> <output_type> <recurse> <audit>
        
        Returns path to converted DXF file or None on failure.
        """
        if not os.path.exists(self.oda_path):
            logger.warning(f"ODA File Converter not found at {self.oda_path}")
            # Fall back to checking if there's already a DXF version
            dxf_path = dwg_path.with_suffix(".dxf")
            if dxf_path.exists():
                return dxf_path
            return None
        
        # Create temp directory for output
        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = str(dwg_path.parent)
            output_dir = temp_dir
            
            # ODA command: convert to DXF 2018 format
            cmd = [
                self.oda_path,
                input_dir,
                output_dir,
                "ACAD2018",  # Output version
                "DXF",       # Output type
                "0",         # Don't recurse
                "1",         # Audit and fix errors
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120  # 2 minute timeout
                )
                
                # Look for the output file
                output_file = Path(output_dir) / dwg_path.with_suffix(".dxf").name
                if output_file.exists():
                    # Move to a persistent temp location
                    final_path = Path(tempfile.gettempdir()) / f"pv_{dwg_path.stem}.dxf"
                    output_file.rename(final_path)
                    return final_path
                else:
                    logger.error(f"ODA conversion produced no output: {result.stderr}")
                    return None
                    
            except subprocess.TimeoutExpired:
                logger.error("ODA conversion timed out")
                return None
            except Exception as e:
                logger.error(f"ODA conversion failed: {e}")
                return None
    
    def _get_units(self, doc: ezdxf.document.Drawing) -> Optional[str]:
        """Extract drawing units from the DXF header."""
        try:
            units_code = doc.header.get("$INSUNITS", 0)
            units_map = {
                0: "unitless",
                1: "inches",
                2: "feet",
                3: "miles",
                4: "millimeters",
                5: "centimeters",
                6: "meters",
                7: "kilometers",
            }
            return units_map.get(units_code, "unknown")
        except:
            return None
    
    def _extract_layers(self, doc: ezdxf.document.Drawing) -> List[Dict[str, Any]]:
        """Extract all layers with their properties."""
        layers = []
        for layer in doc.layers:
            layers.append({
                "name": layer.dxf.name,
                "color": layer.dxf.color,
                "is_on": layer.is_on(),
                "is_frozen": layer.is_frozen(),
                "linetype": layer.dxf.linetype,
            })
        return layers
    
    def _extract_entities(self, doc: ezdxf.document.Drawing) -> List[ExtractedEntity]:
        """Extract geometry entities from modelspace."""
        entities = []
        msp = doc.modelspace()
        
        for entity in msp:
            extracted = self._extract_single_entity(entity)
            if extracted:
                entities.append(extracted)
        
        return entities
    
    def _extract_single_entity(self, entity) -> Optional[ExtractedEntity]:
        """Extract a single entity based on its type."""
        try:
            handle = entity.dxf.handle
            layer = entity.dxf.layer
            entity_type = entity.dxftype()
            
            points = []
            properties = {}
            
            if isinstance(entity, Line):
                start = entity.dxf.start
                end = entity.dxf.end
                points = [
                    (start.x, start.y, start.z if hasattr(start, 'z') else 0),
                    (end.x, end.y, end.z if hasattr(end, 'z') else 0),
                ]
                
            elif isinstance(entity, LWPolyline):
                # LWPolyline is 2D with optional bulge
                for x, y, start_width, end_width, bulge in entity.get_points(format='xyseb'):
                    points.append((x, y, 0))
                properties["closed"] = entity.closed
                
            elif isinstance(entity, Polyline):
                # 3D Polyline
                for vertex in entity.vertices:
                    loc = vertex.dxf.location
                    points.append((loc.x, loc.y, loc.z if hasattr(loc, 'z') else 0))
                properties["closed"] = entity.is_closed
                
            elif isinstance(entity, Circle):
                center = entity.dxf.center
                points = [(center.x, center.y, center.z if hasattr(center, 'z') else 0)]
                properties["radius"] = entity.dxf.radius
                entity_type = "CIRCLE"
                
            elif isinstance(entity, Arc):
                center = entity.dxf.center
                points = [(center.x, center.y, center.z if hasattr(center, 'z') else 0)]
                properties["radius"] = entity.dxf.radius
                properties["start_angle"] = entity.dxf.start_angle
                properties["end_angle"] = entity.dxf.end_angle
                entity_type = "ARC"
                
            else:
                # Skip unsupported entity types for now
                return None
            
            if not points:
                return None
            
            # Check if any Z values indicate depth
            z_values = [p[2] for p in points if p[2] != 0]
            has_depth = len(z_values) > 0
            
            return ExtractedEntity(
                handle=handle,
                entity_type=entity_type,
                layer=layer,
                points=points,
                properties=properties,
                has_depth=has_depth,
                depth_values=z_values,
            )
            
        except Exception as e:
            logger.warning(f"Failed to extract entity: {e}")
            return None
    
    def _calculate_bounds(self, result: ParseResult):
        """Calculate bounding box from all entities."""
        all_x = []
        all_y = []
        
        for entity in result.entities:
            for x, y, z in entity.points:
                all_x.append(x)
                all_y.append(y)
        
        if all_x and all_y:
            result.min_x = min(all_x)
            result.max_x = max(all_x)
            result.min_y = min(all_y)
            result.max_y = max(all_y)
    
    def _detect_crs(self, doc: ezdxf.document.Drawing) -> Tuple[bool, Optional[str]]:
        """
        Attempt to detect CRS from DXF metadata.
        
        DXF files can store CRS info in:
        - XRECORD objects
        - Custom properties
        - Block attributes
        """
        # Check for GeoData (AutoCAD Civil 3D style)
        try:
            geodata = doc.geodata
            if geodata:
                return True, geodata.coordinate_system_definition
        except:
            pass
        
        # Check header variables
        try:
            # Some files store it in custom variables
            for var_name in ["$PROJECTNAME", "$PROJCRS", "$COORDINATE_SYSTEM"]:
                if var_name in doc.header:
                    return True, doc.header[var_name]
        except:
            pass
        
        return False, None
    
    def _check_depth(self, entities: List[ExtractedEntity]) -> bool:
        """Check if any entities have Z-coordinate depth information."""
        for entity in entities:
            if entity.has_depth and entity.depth_values:
                # Check if Z values are meaningful (not just 0)
                if any(abs(z) > 0.001 for z in entity.depth_values):
                    return True
        return False
    
    def _detect_rotation(self, doc: ezdxf.document.Drawing) -> Tuple[bool, float]:
        """
        Detect if the drawing has rotation information.
        
        Looks for:
        - North arrow blocks
        - UCS rotation
        - Header variables
        """
        # Check UCS
        try:
            ucs = doc.header.get("$UCSORG")
            angle = doc.header.get("$UCSXDIR")
            if angle:
                # Calculate rotation from X direction vector
                import math
                rotation = math.degrees(math.atan2(angle[1], angle[0]))
                if abs(rotation) > 0.1:
                    return True, rotation
        except:
            pass
        
        # Look for north arrow blocks
        north_arrow_names = ["NORTH", "NORTHARROW", "N_ARROW", "NORTH_ARROW"]
        msp = doc.modelspace()
        for entity in msp:
            if isinstance(entity, Insert):
                if any(na in entity.dxf.name.upper() for na in north_arrow_names):
                    rotation = entity.dxf.rotation
                    return True, rotation
        
        return False, 0.0
    
    def _determine_missing_fields(self, result: ParseResult) -> List[str]:
        """Determine what information is missing and needs user input."""
        missing = []
        
        if not result.has_depth:
            missing.append("depth")
        
        if not result.has_crs:
            missing.append("crs")
        
        if not result.has_rotation:
            missing.append("rotation")
        
        # Check if we have any labeled pipes
        has_labels = any(
            entity.suggested_type is not None 
            for entity in result.entities
        )
        if not has_labels:
            missing.append("labels")
        
        return missing
    
    def _classify_entities(
        self, 
        entities: List[ExtractedEntity], 
        layers: List[Dict[str, Any]]
    ):
        """
        Attempt to auto-classify entities based on layer names and patterns.
        This is the "lossy match" step from the diagram.
        """
        # Build a layer name to asset type mapping
        layer_types = {}
        for layer in layers:
            layer_name = layer["name"].upper()
            for asset_type, keywords in self.ASSET_TYPE_KEYWORDS.items():
                if any(kw.upper() in layer_name for kw in keywords):
                    layer_types[layer["name"]] = asset_type
                    break
        
        # Apply classifications to entities
        for entity in entities:
            if entity.layer in layer_types:
                entity.suggested_type = layer_types[entity.layer]


# Convenience function for external use
def parse_dwg(file_path: str) -> ParseResult:
    """Parse a DWG/DXF file and return structured results."""
    parser = DWGParser()
    return parser.parse(file_path)
