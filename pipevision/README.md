# PipeVision

**DWG Preprocessing SaaS for AR/GIS Platforms**

PipeVision transforms messy DWG/DXF files into AR-ready 3D data. It's the missing link between raw CAD files and visualization platforms like VirtualGIS, vGIS, and Augview.

## The Problem

AR/GIS platforms expect clean, georeferenced data with proper metadata. But real-world DWG files are often missing:
- **Depth information** (Z coordinates)
- **Coordinate Reference System** (CRS/projection)
- **Rotation/orientation** (north alignment)
- **Asset labels** (what type of pipe is this?)

PipeVision detects what's missing, guides users through a validation wizard, and exports AR-ready data.

## Features

- 📤 **DWG/DXF Upload** - Drag-and-drop file upload with progress tracking
- 🔍 **Auto-Detection** - Automatically identifies missing metadata
- 🧙 **Validation Wizard** - Step-by-step prompts to fill in gaps
- 🏷️ **Smart Classification** - Auto-suggest asset types based on layer names
- 🖼️ **Visual Preview** - Thumbnail generation for verification
- 📊 **Multiple Exports** - GeoJSON, CSV, glTF, KML, Shapefile
- 🔑 **API Keys** - B2B integration support for platform partners
- 🪝 **Webhooks** - Notify external systems when processing completes

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│   FastAPI   │────▶│   Celery    │
│   (React)   │     │   Gateway   │     │   Workers   │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                   │
                    ┌──────┴──────┐     ┌──────┴──────┐
                    │  PostgreSQL │     │    Redis    │
                    │  + PostGIS  │     │   (Queue)   │
                    └─────────────┘     └─────────────┘
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Celery
- **Database**: PostgreSQL 15 + PostGIS
- **Queue**: Redis
- **DWG Processing**: ezdxf, ODA File Converter
- **Geospatial**: pyproj, Shapely, GeoAlchemy2
- **3D Export**: trimesh
- **Storage**: Local filesystem or S3-compatible

## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Optional) ODA File Converter for DWG support

### Development Setup

1. **Clone and start services:**
   ```bash
   git clone https://github.com/yourusername/pipevision.git
   cd pipevision
   docker-compose up -d
   ```

2. **Access the API:**
   - API: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - Database: localhost:5432

3. **Run tests:**
   ```bash
   docker-compose exec api pytest
   ```

### Local Development (without Docker)

1. **Install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```

2. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials
   ```

3. **Start services:**
   ```bash
   # Terminal 1: API
   uvicorn app.main:app --reload

   # Terminal 2: Celery worker
   celery -A app.processing.tasks worker --loglevel=info
   ```

## API Overview

### Upload a DWG file
```bash
curl -X POST http://localhost:8000/api/uploads/ \
  -F "file=@your_drawing.dwg" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Check processing status
```bash
curl http://localhost:8000/api/uploads/status/{project_id}
```

### Update metadata (validation wizard)
```bash
curl -X PATCH http://localhost:8000/api/projects/{project_id}/metadata \
  -H "Content-Type: application/json" \
  -d '{"source_crs": "EPSG:2263", "rotation_degrees": 0}'
```

### Export to GeoJSON
```bash
curl -X POST http://localhost:8000/api/exports/{project_id} \
  -H "Content-Type: application/json" \
  -d '{"format": "geojson"}'
```

## Project Structure

```
pipevision/
├── app/
│   ├── api/              # API route handlers
│   │   ├── auth.py       # Authentication endpoints
│   │   ├── uploads.py    # File upload handling
│   │   ├── projects.py   # Project CRUD & validation
│   │   └── exports.py    # Export generation
│   ├── core/             # Core configuration
│   │   ├── config.py     # Settings & environment
│   │   └── database.py   # Database connection
│   ├── models/           # SQLAlchemy models
│   │   └── models.py     # Project, Asset, User models
│   ├── processing/       # Background processing
│   │   ├── dwg_parser.py # DWG/DXF parsing engine
│   │   ├── thumbnail.py  # Preview image generation
│   │   ├── exporters.py  # GeoJSON, CSV, glTF export
│   │   └── tasks.py      # Celery task definitions
│   └── main.py           # FastAPI application entry
├── frontend/             # React frontend (TODO)
├── tests/                # Test suite
├── docker-compose.yml    # Local development setup
├── Dockerfile            # Container image
└── requirements.txt      # Python dependencies
```

## Roadmap

### Phase 1: Core Pipeline (Current)
- [x] Project structure
- [x] DWG/DXF parsing with ezdxf
- [x] Thumbnail generation
- [x] Missing metadata detection
- [x] GeoJSON export
- [ ] Frontend validation wizard
- [ ] User authentication

### Phase 2: Smart Features
- [ ] Auto-detect CRS from file metadata
- [ ] Machine learning for asset classification
- [ ] Batch processing for multiple files
- [ ] 3D preview in browser

### Phase 3: B2B Ready
- [ ] API keys for integrations
- [ ] Webhook notifications
- [ ] White-label options
- [ ] Usage analytics dashboard

## License

MIT License - See LICENSE file for details.

## Contributing

Contributions welcome! Please read CONTRIBUTING.md first.

## Support

- 📧 Email: support@pipevision.io
- 💬 Discord: [Join our community](#)
- 📖 Docs: https://docs.pipevision.io
