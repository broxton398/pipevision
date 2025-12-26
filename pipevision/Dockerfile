# PipeVision Dockerfile
# Python 3.11 with geospatial dependencies and Blender for FBX export

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build dependencies
    build-essential \
    # PostgreSQL client
    libpq-dev \
    # Geospatial libraries
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    # Image processing
    libjpeg-dev \
    libpng-dev \
    # For Blender
    wget \
    xz-utils \
    libxi6 \
    libxxf86vm1 \
    libxfixes3 \
    libxrender1 \
    libgl1 \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Install Blender (headless)
RUN wget -q https://download.blender.org/release/Blender4.0/blender-4.0.2-linux-x64.tar.xz \
    && tar -xf blender-4.0.2-linux-x64.tar.xz \
    && mv blender-4.0.2-linux-x64 /opt/blender \
    && ln -s /opt/blender/blender /usr/local/bin/blender \
    && rm blender-4.0.2-linux-x64.tar.xz

# Set GDAL environment variables
ENV GDAL_CONFIG=/usr/bin/gdal-config

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application code
COPY . .

# Create storage directories
RUN mkdir -p /app/storage/uploads /app/storage/thumbnails /app/storage/exports

# Create non-root user
RUN useradd -m -u 1000 pipevision && \
    chown -R pipevision:pipevision /app
USER pipevision

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
