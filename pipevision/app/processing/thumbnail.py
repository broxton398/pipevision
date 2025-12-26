"""
PipeVision Thumbnail Generator
Creates preview images from DWG/DXF files for the validation wizard UI
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple, List
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.processing.dwg_parser import ParseResult, ExtractedEntity
from app.models.models import ASSET_TYPE_COLORS, AssetType


logger = logging.getLogger(__name__)


@dataclass
class ThumbnailOptions:
    """Options for thumbnail generation."""
    width: int = 800
    height: int = 600
    background_color: str = "#1e293b"  # Dark slate
    grid_color: str = "#334155"
    default_line_color: str = "#94a3b8"
    line_width: int = 2
    padding: int = 40
    show_grid: bool = True
    show_origin: bool = True
    highlight_origin: bool = False  # For CRS selection step


class ThumbnailGenerator:
    """
    Generates thumbnail preview images from parsed DWG/DXF data.
    
    The thumbnail is used in the validation wizard to help users:
    - Verify they uploaded the correct file
    - Identify the drawing orientation
    - Select the origin point for georeferencing
    - See which layers/pipes are detected
    """
    
    # Map suggested types to colors
    TYPE_COLORS = {
        "sewer": "#8B4513",
        "storm": "#4169E1",
        "potable": "#00CED1",
        "gas": "#FFD700",
        "electric": "#FF4500",
        "telecom": "#9370DB",
        "fiber": "#32CD32",
    }
    
    def __init__(self, options: Optional[ThumbnailOptions] = None):
        self.options = options or ThumbnailOptions()
    
    def generate(
        self, 
        parse_result: ParseResult,
        output_path: str,
        highlight_layers: Optional[List[str]] = None,
    ) -> bool:
        """
        Generate a thumbnail image from parse results.
        
        Args:
            parse_result: The parsed DWG/DXF data
            output_path: Where to save the thumbnail
            highlight_layers: Optional list of layer names to highlight
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create image
            img = Image.new(
                "RGB",
                (self.options.width, self.options.height),
                self.options.background_color
            )
            draw = ImageDraw.Draw(img)
            
            # Calculate transform from drawing coords to image coords
            transform = self._calculate_transform(parse_result)
            if transform is None:
                logger.warning("Could not calculate transform - no entities with bounds")
                return False
            
            # Draw grid
            if self.options.show_grid:
                self._draw_grid(draw, transform)
            
            # Draw entities
            self._draw_entities(
                draw, 
                parse_result.entities, 
                transform,
                highlight_layers
            )
            
            # Draw origin marker
            if self.options.show_origin:
                self._draw_origin(draw, transform, parse_result)
            
            # Draw scale bar
            self._draw_scale_bar(draw, transform)
            
            # Draw info overlay
            self._draw_info_overlay(draw, parse_result)
            
            # Save
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img.save(output_path, "PNG", quality=95)
            
            logger.info(f"Generated thumbnail: {output_path}")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to generate thumbnail: {e}")
            return False
    
    def _calculate_transform(
        self, 
        parse_result: ParseResult
    ) -> Optional[dict]:
        """
        Calculate the transformation from drawing coordinates to image coordinates.
        
        Returns a dict with scale, offset_x, offset_y for transforming points.
        """
        if (parse_result.min_x is None or parse_result.max_x is None or
            parse_result.min_y is None or parse_result.max_y is None):
            return None
        
        # Drawing bounds
        draw_width = parse_result.max_x - parse_result.min_x
        draw_height = parse_result.max_y - parse_result.min_y
        
        if draw_width == 0 or draw_height == 0:
            return None
        
        # Available image space (with padding)
        img_width = self.options.width - (2 * self.options.padding)
        img_height = self.options.height - (2 * self.options.padding)
        
        # Calculate scale to fit
        scale_x = img_width / draw_width
        scale_y = img_height / draw_height
        scale = min(scale_x, scale_y)
        
        # Center the drawing
        scaled_width = draw_width * scale
        scaled_height = draw_height * scale
        offset_x = self.options.padding + (img_width - scaled_width) / 2
        offset_y = self.options.padding + (img_height - scaled_height) / 2
        
        return {
            "scale": scale,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "min_x": parse_result.min_x,
            "min_y": parse_result.min_y,
            "draw_width": draw_width,
            "draw_height": draw_height,
        }
    
    def _transform_point(
        self, 
        x: float, 
        y: float, 
        transform: dict
    ) -> Tuple[int, int]:
        """Transform a drawing coordinate to image coordinate."""
        # Transform X
        img_x = (x - transform["min_x"]) * transform["scale"] + transform["offset_x"]
        
        # Transform Y (flip because image Y is inverted)
        img_y = self.options.height - (
            (y - transform["min_y"]) * transform["scale"] + transform["offset_y"]
        )
        
        return int(img_x), int(img_y)
    
    def _draw_grid(self, draw: ImageDraw, transform: dict):
        """Draw a reference grid."""
        # Calculate grid spacing (aim for ~10 grid lines)
        grid_spacing = max(transform["draw_width"], transform["draw_height"]) / 10
        
        # Round to nice numbers
        magnitude = 10 ** int(len(str(int(grid_spacing))) - 1)
        grid_spacing = round(grid_spacing / magnitude) * magnitude
        
        if grid_spacing == 0:
            grid_spacing = 1
        
        # Draw vertical lines
        x = transform["min_x"] - (transform["min_x"] % grid_spacing)
        while x <= transform["min_x"] + transform["draw_width"]:
            x1, y1 = self._transform_point(x, transform["min_y"], transform)
            x2, y2 = self._transform_point(x, transform["min_y"] + transform["draw_height"], transform)
            draw.line([(x1, y1), (x2, y2)], fill=self.options.grid_color, width=1)
            x += grid_spacing
        
        # Draw horizontal lines
        y = transform["min_y"] - (transform["min_y"] % grid_spacing)
        while y <= transform["min_y"] + transform["draw_height"]:
            x1, y1 = self._transform_point(transform["min_x"], y, transform)
            x2, y2 = self._transform_point(transform["min_x"] + transform["draw_width"], y, transform)
            draw.line([(x1, y1), (x2, y2)], fill=self.options.grid_color, width=1)
            y += grid_spacing
    
    def _draw_entities(
        self, 
        draw: ImageDraw, 
        entities: List[ExtractedEntity],
        transform: dict,
        highlight_layers: Optional[List[str]] = None
    ):
        """Draw all entities on the thumbnail."""
        for entity in entities:
            # Determine color
            if entity.suggested_type and entity.suggested_type in self.TYPE_COLORS:
                color = self.TYPE_COLORS[entity.suggested_type]
            else:
                color = self.options.default_line_color
            
            # Highlight certain layers if requested
            line_width = self.options.line_width
            if highlight_layers and entity.layer in highlight_layers:
                line_width = self.options.line_width + 2
            
            # Draw based on entity type
            if entity.entity_type in ["LINE", "LWPOLYLINE", "POLYLINE"]:
                self._draw_line_entity(draw, entity, transform, color, line_width)
            elif entity.entity_type == "CIRCLE":
                self._draw_circle_entity(draw, entity, transform, color, line_width)
            elif entity.entity_type == "ARC":
                self._draw_arc_entity(draw, entity, transform, color, line_width)
    
    def _draw_line_entity(
        self, 
        draw: ImageDraw, 
        entity: ExtractedEntity,
        transform: dict,
        color: str,
        line_width: int
    ):
        """Draw a line or polyline entity."""
        if len(entity.points) < 2:
            return
        
        # Transform all points
        img_points = [
            self._transform_point(x, y, transform)
            for x, y, z in entity.points
        ]
        
        # Draw lines between consecutive points
        for i in range(len(img_points) - 1):
            draw.line(
                [img_points[i], img_points[i + 1]],
                fill=color,
                width=line_width
            )
        
        # Close polygon if needed
        if entity.properties.get("closed") and len(img_points) > 2:
            draw.line(
                [img_points[-1], img_points[0]],
                fill=color,
                width=line_width
            )
    
    def _draw_circle_entity(
        self, 
        draw: ImageDraw, 
        entity: ExtractedEntity,
        transform: dict,
        color: str,
        line_width: int
    ):
        """Draw a circle entity."""
        if not entity.points or "radius" not in entity.properties:
            return
        
        center_x, center_y, _ = entity.points[0]
        radius = entity.properties["radius"]
        
        # Transform center and calculate scaled radius
        cx, cy = self._transform_point(center_x, center_y, transform)
        scaled_radius = radius * transform["scale"]
        
        # Draw circle
        bbox = [
            cx - scaled_radius,
            cy - scaled_radius,
            cx + scaled_radius,
            cy + scaled_radius
        ]
        draw.ellipse(bbox, outline=color, width=line_width)
    
    def _draw_arc_entity(
        self, 
        draw: ImageDraw, 
        entity: ExtractedEntity,
        transform: dict,
        color: str,
        line_width: int
    ):
        """Draw an arc entity."""
        if not entity.points or "radius" not in entity.properties:
            return
        
        center_x, center_y, _ = entity.points[0]
        radius = entity.properties["radius"]
        start_angle = entity.properties.get("start_angle", 0)
        end_angle = entity.properties.get("end_angle", 360)
        
        # Transform center and calculate scaled radius
        cx, cy = self._transform_point(center_x, center_y, transform)
        scaled_radius = radius * transform["scale"]
        
        # Draw arc
        bbox = [
            cx - scaled_radius,
            cy - scaled_radius,
            cx + scaled_radius,
            cy + scaled_radius
        ]
        # Note: PIL angles are measured from 3 o'clock, counter-clockwise
        # DXF angles are measured from 3 o'clock, counter-clockwise
        # But PIL Y is inverted, so we need to flip
        draw.arc(bbox, -end_angle, -start_angle, fill=color, width=line_width)
    
    def _draw_origin(
        self, 
        draw: ImageDraw, 
        transform: dict,
        parse_result: ParseResult
    ):
        """Draw the origin/centroid marker."""
        # Calculate centroid
        if parse_result.min_x is not None and parse_result.max_x is not None:
            centroid_x = (parse_result.min_x + parse_result.max_x) / 2
            centroid_y = (parse_result.min_y + parse_result.max_y) / 2
        else:
            return
        
        cx, cy = self._transform_point(centroid_x, centroid_y, transform)
        
        # Draw crosshair
        size = 15
        color = "#f59e0b" if self.options.highlight_origin else "#64748b"
        
        draw.line([(cx - size, cy), (cx + size, cy)], fill=color, width=2)
        draw.line([(cx, cy - size), (cx, cy + size)], fill=color, width=2)
        
        # Draw circle around it
        draw.ellipse(
            [cx - size/2, cy - size/2, cx + size/2, cy + size/2],
            outline=color,
            width=2
        )
        
        # Label
        try:
            draw.text(
                (cx + size + 5, cy - 8),
                "CENTROID",
                fill=color,
            )
        except:
            pass
    
    def _draw_scale_bar(self, draw: ImageDraw, transform: dict):
        """Draw a scale bar in the bottom-left corner."""
        # Calculate a nice round scale bar length
        target_pixels = 100
        target_units = target_pixels / transform["scale"]
        
        # Round to nice number
        magnitude = 10 ** int(len(str(int(target_units))) - 1)
        if magnitude == 0:
            magnitude = 1
        nice_length = round(target_units / magnitude) * magnitude
        if nice_length == 0:
            nice_length = magnitude
        
        bar_pixels = nice_length * transform["scale"]
        
        # Position
        x = self.options.padding
        y = self.options.height - self.options.padding + 10
        
        # Draw bar
        draw.line([(x, y), (x + bar_pixels, y)], fill="#e2e8f0", width=3)
        draw.line([(x, y - 5), (x, y + 5)], fill="#e2e8f0", width=2)
        draw.line([(x + bar_pixels, y - 5), (x + bar_pixels, y + 5)], fill="#e2e8f0", width=2)
        
        # Label
        try:
            label = f"{nice_length:.0f} units"
            draw.text((x + bar_pixels/2 - 20, y + 8), label, fill="#94a3b8")
        except:
            pass
    
    def _draw_info_overlay(self, draw: ImageDraw, parse_result: ParseResult):
        """Draw file info overlay in top-left corner."""
        lines = [
            parse_result.filename,
            f"Layers: {len(parse_result.layers)}",
            f"Entities: {len(parse_result.entities)}",
        ]
        
        if parse_result.units:
            lines.append(f"Units: {parse_result.units}")
        
        y = 10
        for line in lines:
            try:
                draw.text((10, y), line, fill="#64748b")
                y += 18
            except:
                pass


def generate_thumbnail(
    parse_result: ParseResult, 
    output_path: str,
    **kwargs
) -> bool:
    """Convenience function to generate a thumbnail."""
    generator = ThumbnailGenerator()
    return generator.generate(parse_result, output_path, **kwargs)
