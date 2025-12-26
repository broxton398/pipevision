"""
PipeVision Celery Tasks
Background processing for DWG parsing, thumbnail generation, and exports
"""

import os
import logging
from datetime import datetime
from typing import Optional

from celery import Celery
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.processing.dwg_parser import DWGParser, ParseResult
from app.processing.thumbnail import ThumbnailGenerator
from app.processing.exporters import GeoJSONExporter, CSVExporter, GLTFExporter, ExportOptions
from app.processing.fbx_exporter import FBXExporter


logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery(
    "pipevision",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minute timeout
    worker_prefetch_multiplier=1,  # Process one task at a time
)


@celery_app.task(bind=True, name="process_dwg_upload")
def process_dwg_upload(self, project_id: str, file_path: str) -> dict:
    """
    Main task for processing a newly uploaded DWG file.
    
    Steps:
    1. Parse the DWG/DXF file
    2. Generate thumbnail
    3. Detect missing metadata
    4. Store results in database
    5. Update project status
    
    Args:
        project_id: UUID of the project
        file_path: Path to the uploaded file
        
    Returns:
        Dict with processing results
    """
    logger.info(f"Processing DWG upload: {project_id}")
    
    try:
        # Update task state
        self.update_state(state="PARSING", meta={"step": "Parsing DWG file"})
        
        # Parse the file
        parser = DWGParser()
        result = parser.parse(file_path)
        
        if not result.success:
            return {
                "success": False,
                "project_id": project_id,
                "errors": result.errors,
            }
        
        # Generate thumbnail
        self.update_state(state="THUMBNAIL", meta={"step": "Generating preview"})
        
        thumbnail_dir = os.path.join(settings.STORAGE_LOCAL_PATH, "thumbnails")
        thumbnail_path = os.path.join(thumbnail_dir, f"{project_id}.png")
        
        thumb_generator = ThumbnailGenerator()
        thumb_success = thumb_generator.generate(result, thumbnail_path)
        
        # Prepare results
        self.update_state(state="STORING", meta={"step": "Storing results"})
        
        # In a real implementation, this would update the database
        # For now, return the results
        return {
            "success": True,
            "project_id": project_id,
            "filename": result.filename,
            "dxf_version": result.dxf_version,
            "units": result.units,
            "layer_count": len(result.layers),
            "entity_count": len(result.entities),
            "layers": [l["name"] for l in result.layers],
            "has_crs": result.has_crs,
            "detected_crs": result.detected_crs,
            "has_depth": result.has_depth,
            "has_rotation": result.has_rotation,
            "rotation_degrees": result.rotation_degrees,
            "missing_fields": result.missing_fields,
            "bounds": {
                "min_x": result.min_x,
                "min_y": result.min_y,
                "max_x": result.max_x,
                "max_y": result.max_y,
            },
            "thumbnail_path": thumbnail_path if thumb_success else None,
            "warnings": result.warnings,
            "classified_entities": sum(
                1 for e in result.entities if e.suggested_type
            ),
        }
        
    except Exception as e:
        logger.exception(f"Error processing DWG: {e}")
        return {
            "success": False,
            "project_id": project_id,
            "errors": [str(e)],
        }


@celery_app.task(bind=True, name="generate_export")
def generate_export(
    self, 
    project_id: str, 
    export_format: str,
    options: Optional[dict] = None
) -> dict:
    """
    Generate an export file for a processed project.
    
    Args:
        project_id: UUID of the project
        export_format: One of "geojson", "csv", "gltf", "kml"
        options: Export options (CRS, etc.)
        
    Returns:
        Dict with export file path and metadata
    """
    logger.info(f"Generating {export_format} export for project {project_id}")
    
    try:
        self.update_state(state="LOADING", meta={"step": "Loading project data"})
        
        # In a real implementation, load assets from database
        # For now, we'll demonstrate the structure
        assets = []  # Would be: db.query(Asset).filter(Asset.project_id == project_id).all()
        
        if not assets:
            return {
                "success": False,
                "error": "No assets found for project",
            }
        
        # Prepare export options
        export_options = ExportOptions(**(options or {}))
        
        # Generate export based on format
        self.update_state(state="EXPORTING", meta={"step": f"Generating {export_format}"})
        
        export_dir = os.path.join(settings.STORAGE_LOCAL_PATH, "exports")
        os.makedirs(export_dir, exist_ok=True)
        
        if export_format == "geojson":
            output_path = os.path.join(export_dir, f"{project_id}.geojson")
            exporter = GeoJSONExporter(export_options)
            success = exporter.export(assets, output_path)
            
        elif export_format == "csv":
            output_path = os.path.join(export_dir, f"{project_id}.csv")
            exporter = CSVExporter(export_options)
            success = exporter.export(assets, output_path)
            
        elif export_format == "gltf":
            output_path = os.path.join(export_dir, f"{project_id}.glb")
            exporter = GLTFExporter(export_options)
            success = exporter.export(assets, output_path)
            
        elif export_format == "fbx":
            output_path = os.path.join(export_dir, f"{project_id}.fbx")
            exporter = FBXExporter(export_options)
            success = exporter.export(assets, output_path)
            
        else:
            return {
                "success": False,
                "error": f"Unsupported export format: {export_format}",
            }
        
        if success:
            file_size = os.path.getsize(output_path)
            return {
                "success": True,
                "project_id": project_id,
                "format": export_format,
                "file_path": output_path,
                "file_size_bytes": file_size,
            }
        else:
            return {
                "success": False,
                "error": "Export generation failed",
            }
            
    except Exception as e:
        logger.exception(f"Error generating export: {e}")
        return {
            "success": False,
            "error": str(e),
        }


@celery_app.task(name="cleanup_expired_exports")
def cleanup_expired_exports():
    """
    Periodic task to clean up expired export files.
    Run via Celery Beat scheduler.
    """
    logger.info("Running expired export cleanup")
    
    # In a real implementation:
    # 1. Query exports where expires_at < now
    # 2. Delete files from storage
    # 3. Update database records
    
    return {"cleaned": 0}


@celery_app.task(name="send_webhook_notification")
def send_webhook_notification(
    webhook_url: str,
    event_type: str,
    payload: dict
) -> dict:
    """
    Send webhook notification to external systems.
    
    Used to notify integrating platforms (like VirtualGIS) when
    processing is complete.
    """
    import httpx
    
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                webhook_url,
                json={
                    "event": event_type,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": payload,
                },
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            
        return {
            "success": True,
            "status_code": response.status_code,
        }
        
    except Exception as e:
        logger.error(f"Webhook notification failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
