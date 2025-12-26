"""
PipeVision Database Models
SQLAlchemy models for PostgreSQL + PostGIS
"""

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, 
    ForeignKey, Text, Enum, JSON
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from geoalchemy2 import Geometry
from datetime import datetime
import uuid
import enum


Base = declarative_base()


class ProjectStatus(str, enum.Enum):
    """Project processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_INPUT = "awaiting_input"
    READY = "ready"
    FAILED = "failed"


class AssetType(str, enum.Enum):
    """Underground asset types."""
    SEWER = "sewer"
    STORM = "storm"
    POTABLE = "potable"
    GAS = "gas"
    ELECTRIC = "electric"
    TELECOM = "telecom"
    FIBER = "fiber"
    UNKNOWN = "unknown"


class User(Base):
    """User account model."""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    company = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    projects = relationship("Project", back_populates="owner")
    api_keys = relationship("APIKey", back_populates="user")


class APIKey(Base):
    """API keys for B2B integrations."""
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="api_keys")


class Project(Base):
    """DWG processing project."""
    __tablename__ = "projects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.PENDING)
    
    # Original file
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer)
    thumbnail_path = Column(String(500))
    
    # Metadata (user-provided or detected)
    metadata_complete = Column(Boolean, default=False)
    missing_fields = Column(JSONB, default=list)  # ["depth", "crs", "rotation", "labels"]
    
    # Coordinate Reference System
    source_crs = Column(String(50))  # e.g., "EPSG:4326"
    target_crs = Column(String(50), default="EPSG:4326")
    
    # Georeferencing
    origin_x = Column(Float)
    origin_y = Column(Float)
    rotation_degrees = Column(Float, default=0.0)
    
    # Bounding box (PostGIS geometry)
    bounds = Column(Geometry("POLYGON", srid=4326))
    
    # Processing results
    layer_count = Column(Integer)
    entity_count = Column(Integer)
    detected_layers = Column(JSONB, default=list)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime)
    
    # Relationships
    owner = relationship("User", back_populates="projects")
    assets = relationship("Asset", back_populates="project", cascade="all, delete-orphan")
    exports = relationship("Export", back_populates="project", cascade="all, delete-orphan")


class Asset(Base):
    """Individual underground asset (pipe, conduit, etc.)."""
    __tablename__ = "assets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    
    # Classification
    asset_type = Column(Enum(AssetType), default=AssetType.UNKNOWN)
    label = Column(String(255))  # User-provided or detected label
    layer_name = Column(String(255))  # Original DWG layer
    
    # Geometry (PostGIS)
    geometry_2d = Column(Geometry("LINESTRING", srid=4326))
    geometry_3d = Column(Geometry("LINESTRINGZ", srid=4326))
    
    # Depth information
    depth_start = Column(Float)  # Depth at start point (meters)
    depth_end = Column(Float)    # Depth at end point (meters)
    depth_unit = Column(String(20), default="meters")
    
    # Pipe properties
    diameter = Column(Float)  # Pipe diameter
    diameter_unit = Column(String(20), default="inches")
    material = Column(String(100))
    
    # Display properties
    color = Column(String(20))  # Hex color for visualization
    
    # Original DWG data
    original_handle = Column(String(50))  # DWG entity handle
    original_properties = Column(JSONB, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="assets")


class Export(Base):
    """Export history and files."""
    __tablename__ = "exports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    
    # Export details
    format = Column(String(50), nullable=False)  # "geojson", "gltf", "csv", "kml", "shp"
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer)
    
    # Export options used
    options = Column(JSONB, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)  # Optional expiration for cleanup
    download_count = Column(Integer, default=0)
    
    # Relationships
    project = relationship("Project", back_populates="exports")


# Color mapping for asset types (used in UI and exports)
ASSET_TYPE_COLORS = {
    AssetType.SEWER: "#8B4513",      # Brown
    AssetType.STORM: "#4169E1",      # Royal Blue
    AssetType.POTABLE: "#00CED1",    # Dark Turquoise
    AssetType.GAS: "#FFD700",        # Gold
    AssetType.ELECTRIC: "#FF4500",   # Orange Red
    AssetType.TELECOM: "#9370DB",    # Medium Purple
    AssetType.FIBER: "#32CD32",      # Lime Green
    AssetType.UNKNOWN: "#808080",    # Gray
}
