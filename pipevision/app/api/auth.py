"""
PipeVision Authentication API
JWT-based auth for users, API keys for B2B integrations
"""

import logging
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from jose import jwt, JWTError

from app.core.config import settings


logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()


# Pydantic schemas

class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    company: Optional[str] = None


class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    """User info response."""
    id: str
    email: str
    full_name: Optional[str]
    company: Optional[str]
    is_verified: bool
    created_at: str


class APIKeyCreate(BaseModel):
    """API key creation request."""
    name: str
    expires_in_days: Optional[int] = 365


class APIKeyResponse(BaseModel):
    """API key creation response (only time the key is shown)."""
    id: str
    name: str
    key: str  # Only shown once!
    created_at: str
    expires_at: Optional[str]


class APIKeyListItem(BaseModel):
    """API key in list (no actual key shown)."""
    id: str
    name: str
    created_at: str
    expires_at: Optional[str]
    last_used_at: Optional[str]
    is_active: bool


# Helper functions

def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt."""
    # In production, use bcrypt or argon2
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    try:
        salt, hash_value = hashed.split("$")
        check = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return check == hash_value
    except:
        return False


def create_access_token(user_id: str) -> tuple[str, int]:
    """Create a JWT access token."""
    expires_delta = timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    expires_at = datetime.utcnow() + expires_delta
    
    payload = {
        "sub": user_id,
        "exp": expires_at,
        "iat": datetime.utcnow(),
        "type": "access",
    }
    
    token = jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM
    )
    
    return token, int(expires_delta.total_seconds())


def generate_api_key() -> tuple[str, str]:
    """Generate an API key and its hash."""
    # Generate a random key with prefix
    key = f"{settings.API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
    # Hash for storage
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Dependency to get current user from JWT token.
    
    Usage:
        @router.get("/protected")
        async def protected_route(user = Depends(get_current_user)):
            return {"user_id": user["id"]}
    """
    token = credentials.credentials
    
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # In production, fetch user from database
        return {"id": user_id}
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_api_key_user(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Optional[dict]:
    """
    Dependency to authenticate via API key.
    
    Usage for B2B endpoints:
        @router.get("/api/v1/process")
        async def api_process(user = Depends(get_api_key_user)):
            return {"user_id": user["id"]}
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    if not x_api_key.startswith(settings.API_KEY_PREFIX):
        raise HTTPException(status_code=401, detail="Invalid API key format")
    
    # Hash the key and look it up
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    
    # In production, query database:
    # api_key = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()
    # if not api_key or not api_key.is_active:
    #     raise HTTPException(status_code=401, detail="Invalid API key")
    # if api_key.expires_at and api_key.expires_at < datetime.utcnow():
    #     raise HTTPException(status_code=401, detail="API key expired")
    # Update last_used_at
    # return {"id": str(api_key.user_id)}
    
    raise HTTPException(status_code=401, detail="Invalid API key")


# API Routes

@router.post("/register", response_model=UserResponse)
async def register(request: UserRegister):
    """
    Register a new user account.
    """
    # In production:
    # 1. Check if email already exists
    # 2. Hash password
    # 3. Create user in database
    # 4. Send verification email
    
    # For now, return a placeholder
    import uuid
    return UserResponse(
        id=str(uuid.uuid4()),
        email=request.email,
        full_name=request.full_name,
        company=request.company,
        is_verified=False,
        created_at=datetime.utcnow().isoformat(),
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLogin):
    """
    Login with email and password.
    Returns a JWT access token.
    """
    # In production:
    # 1. Find user by email
    # 2. Verify password
    # 3. Generate token
    
    # For demo, accept any login
    import uuid
    user_id = str(uuid.uuid4())
    token, expires_in = create_access_token(user_id)
    
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    user: dict = Depends(get_current_user)
):
    """
    Get current user's information.
    """
    # In production, fetch from database
    return UserResponse(
        id=user["id"],
        email="user@example.com",
        full_name=None,
        company=None,
        is_verified=True,
        created_at=datetime.utcnow().isoformat(),
    )


@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    request: APIKeyCreate,
    user: dict = Depends(get_current_user)
):
    """
    Create a new API key for B2B integrations.
    
    IMPORTANT: The key is only shown once in this response.
    Store it securely - it cannot be retrieved again.
    """
    import uuid
    
    key, key_hash = generate_api_key()
    key_id = str(uuid.uuid4())
    
    expires_at = None
    if request.expires_in_days:
        expires_at = (
            datetime.utcnow() + timedelta(days=request.expires_in_days)
        ).isoformat()
    
    # In production, store key_hash in database
    
    return APIKeyResponse(
        id=key_id,
        name=request.name,
        key=key,  # Only time this is shown!
        created_at=datetime.utcnow().isoformat(),
        expires_at=expires_at,
    )


@router.get("/api-keys", response_model=list[APIKeyListItem])
async def list_api_keys(
    user: dict = Depends(get_current_user)
):
    """
    List all API keys for the current user.
    Note: The actual key values are not shown.
    """
    # In production, query database
    return []


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Revoke an API key.
    """
    # In production, soft-delete or hard-delete the key
    return {"success": True, "message": "API key revoked"}


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    user: dict = Depends(get_current_user)
):
    """
    Refresh an access token.
    """
    token, expires_in = create_access_token(user["id"])
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
    )
