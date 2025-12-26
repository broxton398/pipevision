"""
PipeVision Exports API
Generate and download AR/GIS-ready export files
"""

import os
import logging
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings
from app.processing.tasks import generate_export


logger = logging.getLogger(__name__)
router = APIRouter()


class ExportFormat(str, Enum):
    """Supported export formats."""
    GEOJSON = "geojson"
    CSV = "csv"
    GLTF = "gltf"
    GLB = "glb"
    KML = "kml"
    SHAPEFILE = "shp"
    FBX = "fbx"  # For Unity, Unreal, Blender, etc.


class ExportRequest(BaseModel):
    """Request to generate an export."""
    format: ExportFormat
    source_crs: Optional[str] = None  # Override project CRS
    target_crs: Optional[str] = "EPSG:4326"
    include_depth: bool = True
    include_properties: bool = True
    asset_types: Optional[List[str]] = None  # Filter by type


class ExportResponse(BaseModel):
    """Response for export generation."""
    success: bool
    export_id: Optional[str] = None
    task_id: Optional[str] = None
    status: str
    message: str


class ExportStatus(BaseModel):
    """Status of an export generation task."""
    export_id: str
    status: str  # "pending", "processing", "ready", "failed"
    progress: Optional[int] = None
    download_url: Optional[str] = None
    file_size: Optional[int] = None
    error: Optional[str] = None


class ExportListItem(BaseModel):
    """Export item in list."""
    id: str
    project_id: str
    format: str
    file_size: Optional[int]
    created_at: str
    download_count: int


@router.post("/{project_id}", response_model=ExportResponse)
async def create_export(
    project_id: str,
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    # user = Depends(get_current_user),
):
    """
    Generate a new export for a project.
    
    Supports multiple formats:
    - GeoJSON: Standard for web mapping and AR platforms
    - CSV: Simple spreadsheet format
    - glTF/GLB: 3D models for AR viewers
    - KML: Google Earth
    - Shapefile: Legacy GIS systems
    
    Export is generated asynchronously. Use the status endpoint
    to check progress and get the download URL.
    """
    import uuid
    
    export_id = str(uuid.uuid4())
    
    # Queue the export task
    task = generate_export.delay(
        project_id,
        request.format.value,
        {
            "source_crs": request.source_crs,
            "target_crs": request.target_crs,
            "include_depth": request.include_depth,
            "include_properties": request.include_properties,
        }
    )
    
    return ExportResponse(
        success=True,
        export_id=export_id,
        task_id=task.id,
        status="processing",
        message=f"Export generation started. Format: {request.format.value}"
    )


@router.get("/{project_id}", response_model=List[ExportListItem])
async def list_exports(
    project_id: str,
    # user = Depends(get_current_user),
):
    """
    List all exports for a project.
    """
    # In production, query database
    return []


@router.get("/{project_id}/status/{export_id}", response_model=ExportStatus)
async def get_export_status(
    project_id: str,
    export_id: str,
    # user = Depends(get_current_user),
):
    """
    Get the status of an export generation task.
    """
    # Check if export file exists
    export_dir = os.path.join(settings.STORAGE_LOCAL_PATH, "exports")
    
    # Look for any file matching export_id
    for ext in [".geojson", ".csv", ".glb", ".gltf", ".kml", ".zip", ".fbx", ".obj"]:
        file_path = os.path.join(export_dir, f"{export_id}{ext}")
        if os.path.exists(file_path):
            return ExportStatus(
                export_id=export_id,
                status="ready",
                progress=100,
                download_url=f"/api/exports/{project_id}/download/{export_id}",
                file_size=os.path.getsize(file_path),
            )
    
    # If not found, assume still processing
    return ExportStatus(
        export_id=export_id,
        status="processing",
        progress=50,
    )


@router.get("/{project_id}/download/{export_id}")
async def download_export(
    project_id: str,
    export_id: str,
    # user = Depends(get_current_user),
):
    """
    Download an exported file.
    """
    export_dir = os.path.join(settings.STORAGE_LOCAL_PATH, "exports")
    
    # Find the export file
    for ext in [".geojson", ".csv", ".glb", ".gltf", ".kml", ".zip", ".fbx", ".obj"]:
        file_path = os.path.join(export_dir, f"{export_id}{ext}")
        if os.path.exists(file_path):
            # Map extension to media type
            media_types = {
                ".geojson": "application/geo+json",
                ".csv": "text/csv",
                ".glb": "model/gltf-binary",
                ".gltf": "model/gltf+json",
                ".kml": "application/vnd.google-earth.kml+xml",
                ".zip": "application/zip",
                ".fbx": "application/octet-stream",
                ".obj": "model/obj",
            }
            
            return FileResponse(
                file_path,
                media_type=media_types.get(ext, "application/octet-stream"),
                filename=f"pipevision_export_{export_id}{ext}"
            )
    
    raise HTTPException(status_code=404, detail="Export not found")


@router.delete("/{project_id}/{export_id}")
async def delete_export(
    project_id: str,
    export_id: str,
    # user = Depends(get_current_user),
):
    """
    Delete an export file.
    """
    export_dir = os.path.join(settings.STORAGE_LOCAL_PATH, "exports")
    deleted = False
    
    for ext in [".geojson", ".csv", ".glb", ".gltf", ".kml", ".zip", ".fbx", ".obj"]:
        file_path = os.path.join(export_dir, f"{export_id}{ext}")
        if os.path.exists(file_path):
            os.remove(file_path)
            deleted = True
    
    if deleted:
        return {"success": True, "message": "Export deleted"}
    
    raise HTTPException(status_code=404, detail="Export not found")


# Quick export endpoints for common formats

@router.get("/{project_id}/quick/geojson")
async def quick_export_geojson(
    project_id: str,
    # user = Depends(get_current_user),
):
    """
    Quick GeoJSON export with default settings.
    Returns the file directly (blocking call for small projects).
    """
    # For MVP, generate synchronously for small files
    # In production, check project size and either:
    # - Generate inline for small projects
    # - Return task_id for large projects
    
    raise HTTPException(
        status_code=501, 
        detail="Quick export not implemented yet. Use POST endpoint."
    )


@router.get("/{project_id}/quick/csv")
async def quick_export_csv(
    project_id: str,
    # user = Depends(get_current_user),
):
    """
    Quick CSV export with default settings.
    """
    raise HTTPException(
        status_code=501,
        detail="Quick export not implemented yet. Use POST endpoint."
    )
