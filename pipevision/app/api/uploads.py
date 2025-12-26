"""
PipeVision Uploads API
Handles file uploads and initiates processing
"""

import os
import uuid
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_db
from app.processing.tasks import process_dwg_upload


logger = logging.getLogger(__name__)
router = APIRouter()


class UploadResponse(BaseModel):
    """Response model for file upload."""
    success: bool
    project_id: str
    filename: str
    file_size: int
    task_id: Optional[str] = None
    message: str


class UploadStatus(BaseModel):
    """Status of an upload/processing task."""
    project_id: str
    status: str
    progress: Optional[int] = None
    step: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


@router.post("/", response_model=UploadResponse)
async def upload_dwg(
    file: UploadFile = File(...),
    project_name: Optional[str] = None,
    # user = Depends(get_current_user),  # Would add auth
):
    """
    Upload a DWG or DXF file for processing.
    
    The file will be:
    1. Validated (extension, size)
    2. Saved to storage
    3. Queued for background processing
    
    Returns a project_id to track processing status.
    """
    # Validate file extension
    filename = file.filename or "unnamed"
    extension = filename.lower().split(".")[-1] if "." in filename else ""
    
    if extension not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {settings.ALLOWED_EXTENSIONS}"
        )
    
    # Read file and check size
    content = await file.read()
    file_size = len(content)
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )
    
    # Generate project ID
    project_id = str(uuid.uuid4())
    
    # Save file
    upload_dir = os.path.join(settings.STORAGE_LOCAL_PATH, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    
    # Use project_id in filename to avoid collisions
    safe_filename = f"{project_id}_{filename}"
    file_path = os.path.join(upload_dir, safe_filename)
    
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.exception(f"Failed to save upload: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to save file"
        )
    
    # Queue processing task
    task = process_dwg_upload.delay(project_id, file_path)
    
    logger.info(f"Upload received: {filename} -> {project_id}, task: {task.id}")
    
    return UploadResponse(
        success=True,
        project_id=project_id,
        filename=filename,
        file_size=file_size,
        task_id=task.id,
        message="File uploaded successfully. Processing started."
    )


@router.get("/status/{project_id}", response_model=UploadStatus)
async def get_upload_status(project_id: str):
    """
    Get the processing status of an uploaded file.
    
    Returns current status, progress, and results when complete.
    """
    # In a real implementation, this would:
    # 1. Check the Celery task status
    # 2. Query the database for project status
    # 3. Return combined status info
    
    from celery.result import AsyncResult
    from app.processing.tasks import celery_app
    
    # Try to find the task
    # Note: In production, you'd store task_id with the project in the database
    # For now, we'll return a placeholder
    
    return UploadStatus(
        project_id=project_id,
        status="processing",
        progress=50,
        step="Analyzing geometry",
    )


@router.post("/{project_id}/retry")
async def retry_processing(project_id: str):
    """
    Retry processing for a failed upload.
    """
    # Look up the original file path and requeue
    upload_dir = os.path.join(settings.STORAGE_LOCAL_PATH, "uploads")
    
    # Find the file
    for filename in os.listdir(upload_dir):
        if filename.startswith(project_id):
            file_path = os.path.join(upload_dir, filename)
            task = process_dwg_upload.delay(project_id, file_path)
            return {
                "success": True,
                "task_id": task.id,
                "message": "Processing restarted"
            }
    
    raise HTTPException(
        status_code=404,
        detail="Original file not found"
    )


@router.delete("/{project_id}")
async def delete_upload(project_id: str):
    """
    Delete an upload and all associated data.
    """
    # In production:
    # 1. Delete from database
    # 2. Delete files from storage
    # 3. Cancel any pending tasks
    
    upload_dir = os.path.join(settings.STORAGE_LOCAL_PATH, "uploads")
    thumbnail_dir = os.path.join(settings.STORAGE_LOCAL_PATH, "thumbnails")
    
    deleted_files = []
    
    # Delete upload
    for filename in os.listdir(upload_dir):
        if filename.startswith(project_id):
            os.remove(os.path.join(upload_dir, filename))
            deleted_files.append(filename)
    
    # Delete thumbnail
    thumbnail_path = os.path.join(thumbnail_dir, f"{project_id}.png")
    if os.path.exists(thumbnail_path):
        os.remove(thumbnail_path)
        deleted_files.append(f"{project_id}.png")
    
    return {
        "success": True,
        "deleted_files": deleted_files,
    }
