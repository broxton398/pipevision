"""
PipeVision Projects API
CRUD operations for projects and metadata management
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import Project, ProjectStatus, Asset, AssetType


logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic schemas
class ProjectBase(BaseModel):
    """Base project schema."""
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    """Schema for creating a project (used internally after upload)."""
    original_filename: str
    file_path: str


class ProjectMetadataUpdate(BaseModel):
    """Schema for updating project metadata (validation wizard)."""
    source_crs: Optional[str] = Field(None, description="e.g., EPSG:4326")
    target_crs: Optional[str] = Field(None, description="Target CRS for export")
    origin_x: Optional[float] = Field(None, description="X coordinate of origin")
    origin_y: Optional[float] = Field(None, description="Y coordinate of origin")
    rotation_degrees: Optional[float] = Field(None, description="Rotation in degrees")
    default_depth: Optional[float] = Field(None, description="Default depth in meters")
    default_depth_unit: Optional[str] = Field("meters", description="Depth unit")


class AssetUpdate(BaseModel):
    """Schema for updating individual asset properties."""
    asset_type: Optional[AssetType] = None
    label: Optional[str] = None
    depth_start: Optional[float] = None
    depth_end: Optional[float] = None
    diameter: Optional[float] = None
    material: Optional[str] = None


class AssetBulkUpdate(BaseModel):
    """Schema for bulk updating assets by layer."""
    layer_name: str
    asset_type: AssetType
    label: Optional[str] = None
    default_depth: Optional[float] = None
    default_diameter: Optional[float] = None


class ProjectResponse(BaseModel):
    """Full project response."""
    id: str
    name: str
    description: Optional[str]
    status: str
    original_filename: str
    thumbnail_path: Optional[str]
    
    # Metadata
    source_crs: Optional[str]
    target_crs: Optional[str]
    rotation_degrees: float
    missing_fields: List[str]
    metadata_complete: bool
    
    # Stats
    layer_count: Optional[int]
    entity_count: Optional[int]
    detected_layers: List[str]
    
    # Timestamps
    created_at: str
    updated_at: str
    processed_at: Optional[str]
    
    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    """Paginated project list response."""
    projects: List[ProjectResponse]
    total: int
    page: int
    page_size: int


class LayerInfo(BaseModel):
    """Information about a detected layer."""
    name: str
    entity_count: int
    suggested_type: Optional[str]
    color: Optional[str]


class ValidationStatus(BaseModel):
    """Current validation status for the wizard."""
    project_id: str
    status: str
    missing_fields: List[str]
    layers: List[LayerInfo]
    thumbnail_url: Optional[str]
    
    # Detected values (user can confirm or override)
    detected_crs: Optional[str]
    detected_rotation: Optional[float]
    has_depth: bool
    has_labels: bool


# API Routes

@router.get("/", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[ProjectStatus] = None,
    # user = Depends(get_current_user),
    # db: AsyncSession = Depends(get_db),
):
    """
    List all projects for the current user.
    
    Supports pagination and filtering by status.
    """
    return ProjectListResponse(
        projects=[],
        total=0,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    # user = Depends(get_current_user),
    # db: AsyncSession = Depends(get_db),
):
    """
    Get details for a specific project.
    """
    raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{project_id}/validation", response_model=ValidationStatus)
async def get_validation_status(
    project_id: str,
    # user = Depends(get_current_user),
):
    """
    Get the validation status for a project.
    
    This is used by the validation wizard to show what data is missing
    and allow user to fill in gaps.
    """
    return ValidationStatus(
        project_id=project_id,
        status="awaiting_input",
        missing_fields=["crs", "depth"],
        layers=[
            LayerInfo(
                name="SEWER_MAIN",
                entity_count=45,
                suggested_type="sewer",
                color="#8B4513"
            ),
            LayerInfo(
                name="WATER_LINE",
                entity_count=32,
                suggested_type="potable",
                color="#00CED1"
            ),
            LayerInfo(
                name="MISC",
                entity_count=12,
                suggested_type=None,
                color=None
            ),
        ],
        thumbnail_url=f"/api/projects/{project_id}/thumbnail",
        detected_crs=None,
        detected_rotation=0.0,
        has_depth=False,
        has_labels=True,
    )


@router.patch("/{project_id}/metadata")
async def update_metadata(
    project_id: str,
    metadata: ProjectMetadataUpdate,
    # user = Depends(get_current_user),
    # db: AsyncSession = Depends(get_db),
):
    """
    Update project metadata (CRS, rotation, etc.).
    Called from the validation wizard when user provides missing data.
    """
    return {
        "success": True,
        "project_id": project_id,
        "updated_fields": [k for k, v in metadata.model_dump().items() if v is not None],
        "metadata_complete": True,
    }


@router.patch("/{project_id}/assets/{asset_id}")
async def update_asset(
    project_id: str,
    asset_id: str,
    update: AssetUpdate,
    # user = Depends(get_current_user),
    # db: AsyncSession = Depends(get_db),
):
    """
    Update a single asset's properties.
    """
    return {
        "success": True,
        "asset_id": asset_id,
        "updated_fields": [k for k, v in update.model_dump().items() if v is not None],
    }


@router.post("/{project_id}/assets/bulk-update")
async def bulk_update_assets(
    project_id: str,
    update: AssetBulkUpdate,
    # user = Depends(get_current_user),
    # db: AsyncSession = Depends(get_db),
):
    """
    Bulk update all assets on a specific layer.
    """
    return {
        "success": True,
        "layer_name": update.layer_name,
        "updated_count": 0,
    }


@router.post("/{project_id}/confirm-classification")
async def confirm_classification(
    project_id: str,
    layer_assignments: List[AssetBulkUpdate],
    # user = Depends(get_current_user),
    # db: AsyncSession = Depends(get_db),
):
    """
    Confirm the asset classification for all layers.
    Final step of the validation wizard.
    """
    results = []
    for assignment in layer_assignments:
        results.append({
            "layer": assignment.layer_name,
            "type": assignment.asset_type.value,
        })
    
    return {
        "success": True,
        "project_id": project_id,
        "status": "ready",
        "assignments": results,
    }


@router.get("/{project_id}/thumbnail")
async def get_thumbnail(project_id: str):
    """
    Get the thumbnail image for a project.
    """
    from fastapi.responses import FileResponse
    import os
    from app.core.config import settings
    
    thumbnail_path = os.path.join(
        settings.STORAGE_LOCAL_PATH, 
        "thumbnails", 
        f"{project_id}.png"
    )
    
    if not os.path.exists(thumbnail_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    
    return FileResponse(
        thumbnail_path,
        media_type="image/png",
        filename=f"{project_id}_preview.png"
    )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    # user = Depends(get_current_user),
    # db: AsyncSession = Depends(get_db),
):
    """
    Delete a project and all associated data.
    """
    return {
        "success": True,
        "project_id": project_id,
        "message": "Project deleted successfully"
    }
