"""
Error Debug API routes.

All routes require TECHNICIAN or ADMIN role.
"""

import json
import os
import uuid
import hashlib
import logging
import time
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_

# Setup logging
logger = logging.getLogger(__name__)

from backend.models.error_debug_models import Machine, MachineIndexVersion
from backend.utils.auth import require_role, DevUser
from backend.utils.db import get_db
from backend.utils.index_storage import save_index_file, load_index_file, delete_index_file
from backend.utils.index_search import search_chunk_index

router = APIRouter(prefix="/api/error-debug", tags=["error-debug"])

# In-memory cache for loaded indexes (LRU with max 5 entries)
_index_cache = {}
_cache_max_size = 5


def _get_cached_index(machine_id: str, version_id: str) -> Optional[dict]:
    """Get index from cache."""
    cache_key = f"{machine_id}:{version_id}"
    result = _index_cache.get(cache_key)
    if result:
        logger.info(f"Cache HIT: machine_id={machine_id}, version_id={version_id}")
    else:
        logger.info(f"Cache MISS: machine_id={machine_id}, version_id={version_id}")
    return result


def _set_cached_index(machine_id: str, version_id: str, index_data: dict):
    """Cache index data."""
    cache_key = f"{machine_id}:{version_id}"
    
    # Simple LRU: remove oldest if at capacity
    if len(_index_cache) >= _cache_max_size:
        # Remove first (oldest) entry
        oldest_key = next(iter(_index_cache))
        evicted = _index_cache.pop(oldest_key)
        logger.info(f"Cache EVICT: {oldest_key} (cache at capacity {_cache_max_size})")
    
    _index_cache[cache_key] = index_data
    logger.info(f"Cache SET: machine_id={machine_id}, version_id={version_id}, cache_size={len(_index_cache)}")


def _clear_cache_for_machine(machine_id: str):
    """Clear all cache entries for a machine."""
    keys_to_remove = [k for k in _index_cache.keys() if k.startswith(f"{machine_id}:")]
    for key in keys_to_remove:
        del _index_cache[key]
    if keys_to_remove:
        logger.info(f"Cache CLEARED for machine_id={machine_id}: {len(keys_to_remove)} entries removed")


# Machine CRUD Routes

@router.get("/machines")
async def list_machines(
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """List all machines with active version stats."""
    machines = db.query(Machine).all()
    
    result = []
    for machine in machines:
        active_version = None
        if machine.active_version_id:
            active_version = db.query(MachineIndexVersion).filter(
                MachineIndexVersion.id == machine.active_version_id
            ).first()
        
        result.append({
            "id": str(machine.id),
            "display_name": machine.display_name,
            "printer_model": machine.printer_model,
            "printing_type": machine.printing_type,
            "created_at": machine.created_at.isoformat(),
            "updated_at": machine.updated_at.isoformat(),
            "active_version": {
                "id": str(active_version.id) if active_version else None,
                "indexed_at": active_version.indexed_at.isoformat() if active_version else None,
                "total_chunks": active_version.total_chunks if active_version else 0,
                "total_errors": active_version.total_errors if active_version else 0,
                "schema_version": active_version.schema_version if active_version else None,
            } if active_version else None
        })
    
    return result


@router.post("/machines")
async def create_machine(
    display_name: str = Form(...),
    printer_model: str = Form(...),
    printing_type: str = Form(...),
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """Create a new machine."""
    # Check for duplicate display_name
    existing = db.query(Machine).filter(Machine.display_name == display_name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Machine with display_name '{display_name}' already exists")
    
    machine = Machine(
        display_name=display_name,
        printer_model=printer_model,
        printing_type=printing_type
    )
    
    db.add(machine)
    db.commit()
    db.refresh(machine)
    
    return {
        "id": str(machine.id),
        "display_name": machine.display_name,
        "printer_model": machine.printer_model,
        "printing_type": machine.printing_type,
        "created_at": machine.created_at.isoformat(),
        "updated_at": machine.updated_at.isoformat()
    }


@router.put("/machines/{machine_id}")
async def update_machine(
    machine_id: str,
    display_name: Optional[str] = Form(None),
    printer_model: Optional[str] = Form(None),
    printing_type: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """Update machine fields."""
    try:
        machine_uuid = uuid.UUID(machine_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid machine_id format")
    
    machine = db.query(Machine).filter(Machine.id == machine_uuid).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    # Check for duplicate display_name if changing
    if display_name and display_name != machine.display_name:
        existing = db.query(Machine).filter(
            and_(Machine.display_name == display_name, Machine.id != machine_uuid)
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Machine with display_name '{display_name}' already exists")
        machine.display_name = display_name
    
    if printer_model is not None:
        machine.printer_model = printer_model
    if printing_type is not None:
        machine.printing_type = printing_type
    
    machine.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(machine)
    
    return {
        "id": str(machine.id),
        "display_name": machine.display_name,
        "printer_model": machine.printer_model,
        "printing_type": machine.printing_type,
        "created_at": machine.created_at.isoformat(),
        "updated_at": machine.updated_at.isoformat()
    }


@router.delete("/machines/{machine_id}")
async def delete_machine(
    machine_id: str,
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """
    Delete machine and all its versions.
    
    Note: TECHNICIAN and ADMIN can delete machines.
    """
    try:
        machine_uuid = uuid.UUID(machine_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid machine_id format")
    
    machine = db.query(Machine).filter(Machine.id == machine_uuid).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    # Delete all index files from storage
    versions = db.query(MachineIndexVersion).filter(
        MachineIndexVersion.machine_id == machine_uuid
    ).all()
    
    for version in versions:
        try:
            delete_index_file(version.gcs_bucket, version.gcs_object)
        except Exception as e:
            print(f"Warning: Failed to delete index file {version.gcs_object}: {e}")
    
    # Delete machine (cascade will delete versions)
    db.delete(machine)
    db.commit()
    
    return {"message": "Machine deleted successfully"}


# Index Version Routes

@router.get("/machines/{machine_id}/versions")
async def list_versions(
    machine_id: str,
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """List all versions for a machine."""
    try:
        machine_uuid = uuid.UUID(machine_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid machine_id format")
    
    machine = db.query(Machine).filter(Machine.id == machine_uuid).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    versions = db.query(MachineIndexVersion).filter(
        MachineIndexVersion.machine_id == machine_uuid
    ).order_by(MachineIndexVersion.created_at.desc()).all()
    
    result = []
    for version in versions:
        stats_data = version.stats_json
        if isinstance(stats_data, str):
            try:
                stats_data = json.loads(stats_data)
            except:
                stats_data = {}
        
        result.append({
            "id": str(version.id),
            "created_at": version.created_at.isoformat(),
            "indexed_at": version.indexed_at.isoformat(),
            "schema_version": version.schema_version,
            "is_active": version.is_active,
            "total_chunks": version.total_chunks,
            "total_errors": version.total_errors,
            "stats": stats_data or {}
        })
    
    return result


@router.post("/machines/{machine_id}/versions")
async def upload_version(
    machine_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """Upload index.json file for a machine."""
    logger.info(f"Upload request: machine_id={machine_id}, user={user.email}, role={user.role}")
    
    try:
        machine_uuid = uuid.UUID(machine_id)
    except ValueError:
        logger.error(f"Invalid machine_id format: {machine_id}")
        raise HTTPException(status_code=400, detail="Invalid machine_id format")
    
    machine = db.query(Machine).filter(Machine.id == machine_uuid).first()
    if not machine:
        logger.error(f"Machine not found: {machine_id}")
        raise HTTPException(status_code=404, detail="Machine not found")
    
    # Read uploaded file with streaming for large files (compute SHA256 during read)
    chunks = []
    sha256_hash = hashlib.sha256()
    
    try:
        # Stream read in chunks (1MB at a time)
        while True:
            chunk = await file.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            chunks.append(chunk)
            sha256_hash.update(chunk)
        
        file_bytes = b''.join(chunks)
        computed_sha256 = sha256_hash.hexdigest()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")
    
    # Parse JSON
    try:
        index_data = json.loads(file_bytes.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    
    # Comprehensive validation
    required_fields = ['schema_version', 'created_at', 'chunks', 'error_index', 'stats']
    for field in required_fields:
        if field not in index_data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    # Validate types and counts
    if not isinstance(index_data['chunks'], list):
        raise HTTPException(status_code=400, detail="Field 'chunks' must be an array")
    if not isinstance(index_data['error_index'], dict):
        raise HTTPException(status_code=400, detail="Field 'error_index' must be an object")
    if not isinstance(index_data['stats'], dict):
        raise HTTPException(status_code=400, detail="Field 'stats' must be an object")
    
    # Validate counts match
    total_chunks = index_data.get('total_chunks')
    total_errors = index_data.get('total_errors')
    
    if total_chunks is not None and total_chunks != len(index_data['chunks']):
        raise HTTPException(
            status_code=400,
            detail=f"total_chunks ({total_chunks}) does not match chunks array length ({len(index_data['chunks'])})"
        )
    
    if total_errors is not None:
        error_count = sum(len(matches) for matches in index_data['error_index'].values())
        if total_errors != error_count:
            raise HTTPException(
                status_code=400,
                detail=f"total_errors ({total_errors}) does not match error_index count ({error_count})"
            )
    
    # Extract metadata
    schema_version = index_data.get('schema_version')
    if not schema_version:
        raise HTTPException(status_code=400, detail="Missing 'schema_version' field in index")
    
    created_at_str = index_data.get('created_at')
    if not created_at_str:
        raise HTTPException(status_code=400, detail="Missing 'created_at' field in index")
    
    try:
        indexed_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        if indexed_at.tzinfo:
            indexed_at = indexed_at.replace(tzinfo=None)  # Convert to naive UTC
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid 'created_at' format: {e}")
    
    stats = index_data.get('stats', {})
    total_chunks = index_data.get('total_chunks', len(index_data.get('chunks', [])))
    total_errors = index_data.get('total_errors', sum(len(matches) for matches in index_data.get('error_index', {}).values()))
    
    # Save to storage (use computed SHA256)
    version_id = uuid.uuid4()
    logger.info(f"Upload: machine_id={machine_id}, version_id={version_id}, file_size={len(file_bytes)} bytes, sha256={computed_sha256[:16]}...")
    
    storage_info = save_index_file(str(machine.id), str(version_id), file_bytes)
    # Override with computed SHA256 for consistency
    storage_info['sha256'] = computed_sha256
    
    storage_mode = "GCS" if storage_info['bucket'] else "LOCAL"
    logger.info(f"Upload: storage_mode={storage_mode}, path={storage_info['object_path']}")
    
    # Atomic transaction: deactivate previous active version and create new one
    try:
        # Deactivate previous active version
        db.query(MachineIndexVersion).filter(
            and_(
                MachineIndexVersion.machine_id == machine_uuid,
                MachineIndexVersion.is_active == True
            )
        ).update({'is_active': False})
        
        # Create version record
        version = MachineIndexVersion(
            id=version_id,
            machine_id=machine_uuid,
            indexed_at=indexed_at,
            schema_version=schema_version,
            gcs_bucket=storage_info['bucket'],
            gcs_object=storage_info['object_path'],
            file_sha256=computed_sha256,
            total_chunks=total_chunks,
            total_errors=total_errors,
            stats_json=stats,
            is_active=True
        )
        
        db.add(version)
        
        # Update machine's active_version_id
        machine.active_version_id = version_id
        machine.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(version)
        
        # Clear cache for this machine (new active version)
        _clear_cache_for_machine(str(machine.id))
        logger.info(f"Upload SUCCESS: machine_id={machine_id}, version_id={version_id}, chunks={total_chunks}, errors={total_errors}")
    except Exception as e:
        db.rollback()
        # Clean up storage on failure
        try:
            delete_index_file(storage_info['bucket'], storage_info['object_path'])
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to save version: {e}")
    
    stats_data = version.stats_json
    if isinstance(stats_data, str):
        try:
            stats_data = json.loads(stats_data)
        except:
            stats_data = {}
    
    return {
        "id": str(version.id),
        "created_at": version.created_at.isoformat(),
        "indexed_at": version.indexed_at.isoformat(),
        "schema_version": version.schema_version,
        "is_active": version.is_active,
        "total_chunks": version.total_chunks,
        "total_errors": version.total_errors,
        "stats": stats_data or {}
    }


@router.post("/machines/{machine_id}/versions/{version_id}/activate")
async def activate_version(
    machine_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """Activate a specific version (atomic operation)."""
    logger.info(f"Activate request: machine_id={machine_id}, version_id={version_id}, user={user.email}")
    
    try:
        machine_uuid = uuid.UUID(machine_id)
        version_uuid = uuid.UUID(version_id)
    except ValueError:
        logger.error(f"Invalid UUID format: machine_id={machine_id}, version_id={version_id}")
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    machine = db.query(Machine).filter(Machine.id == machine_uuid).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    version = db.query(MachineIndexVersion).filter(
        and_(
            MachineIndexVersion.id == version_uuid,
            MachineIndexVersion.machine_id == machine_uuid
        )
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Atomic transaction: deactivate all, then activate this one
    try:
        # Deactivate current active version
        db.query(MachineIndexVersion).filter(
            and_(
                MachineIndexVersion.machine_id == machine_uuid,
                MachineIndexVersion.is_active == True
            )
        ).update({'is_active': False})
        
        # Activate this version
        version.is_active = True
        machine.active_version_id = version_uuid
        machine.updated_at = datetime.utcnow()
        
        db.commit()
        
        # Clear cache for this machine (active version changed)
        _clear_cache_for_machine(str(machine.id))
        logger.info(f"Activate SUCCESS: machine_id={machine_id}, version_id={version_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Activate FAILED: machine_id={machine_id}, version_id={version_id}, error={e}")
        raise HTTPException(status_code=500, detail=f"Failed to activate version: {e}")
    
    return {"message": "Version activated successfully"}


@router.get("/machines/{machine_id}/versions/{version_id}/download")
async def download_version(
    machine_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """Download index file for a version."""
    logger.info(f"Download request: machine_id={machine_id}, version_id={version_id}, user={user.email}")
    
    try:
        machine_uuid = uuid.UUID(machine_id)
        version_uuid = uuid.UUID(version_id)
    except ValueError:
        logger.error(f"Invalid UUID format: machine_id={machine_id}, version_id={version_id}")
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    version = db.query(MachineIndexVersion).filter(
        and_(
            MachineIndexVersion.id == version_uuid,
            MachineIndexVersion.machine_id == machine_uuid
        )
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    # Load index file from storage
    try:
        index_bytes = load_index_file(version.gcs_bucket, version.gcs_object)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Index file not found in storage")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load index: {e}")
    
    from fastapi.responses import Response
    
    # Get machine name for filename
    machine = db.query(Machine).filter(Machine.id == machine_uuid).first()
    machine_name = machine.display_name.replace(' ', '_') if machine else 'unknown'
    filename = f"index_{machine_name}_{version_id[:8]}.json"
    
    logger.info(f"Download SUCCESS: machine_id={machine_id}, version_id={version_id}, size={len(index_bytes)} bytes")
    
    return Response(
        content=index_bytes,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.delete("/machines/{machine_id}/versions/{version_id}")
async def delete_version(
    machine_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """Delete a version. If active, set newest remaining version as active or clear active."""
    logger.info(f"Delete version request: machine_id={machine_id}, version_id={version_id}, user={user.email}")
    
    try:
        machine_uuid = uuid.UUID(machine_id)
        version_uuid = uuid.UUID(version_id)
    except ValueError:
        logger.error(f"Invalid UUID format: machine_id={machine_id}, version_id={version_id}")
        raise HTTPException(status_code=400, detail="Invalid UUID format")
    
    machine = db.query(Machine).filter(Machine.id == machine_uuid).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    version = db.query(MachineIndexVersion).filter(
        and_(
            MachineIndexVersion.id == version_uuid,
            MachineIndexVersion.machine_id == machine_uuid
        )
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    
    was_active = version.is_active
    
    try:
        # If deleting active version, find a replacement
        if was_active:
            # Find newest remaining version
            replacement = db.query(MachineIndexVersion).filter(
                and_(
                    MachineIndexVersion.machine_id == machine_uuid,
                    MachineIndexVersion.id != version_uuid
                )
            ).order_by(MachineIndexVersion.created_at.desc()).first()
            
            if replacement:
                replacement.is_active = True
                machine.active_version_id = replacement.id
            else:
                machine.active_version_id = None
            machine.updated_at = datetime.utcnow()
        
        # Delete index file from storage
        try:
            delete_index_file(version.gcs_bucket, version.gcs_object)
        except Exception as e:
            print(f"Warning: Failed to delete index file: {e}")
        
        # Delete version record
        db.delete(version)
        db.commit()
        
        # Clear cache for this machine (version deleted, active may have changed)
        _clear_cache_for_machine(str(machine.id))
        logger.info(f"Delete SUCCESS: machine_id={machine_id}, version_id={version_id}, was_active={was_active}")
    except Exception as e:
        db.rollback()
        logger.error(f"Delete FAILED: machine_id={machine_id}, version_id={version_id}, error={e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete version: {e}")
    
    return {"message": "Version deleted successfully"}


# Search Route

@router.post("/search")
async def search_index(
    machine_id: str = Form(...),
    query_text: str = Form(...),
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """Search active index for error message."""
    start_time = time.time()
    logger.info(f"Search request: machine_id={machine_id}, query='{query_text[:50]}...', user={user.email}")
    
    try:
        machine_uuid = uuid.UUID(machine_id)
    except ValueError:
        logger.error(f"Invalid machine_id format: {machine_id}")
        raise HTTPException(status_code=400, detail="Invalid machine_id format")
    
    machine = db.query(Machine).filter(Machine.id == machine_uuid).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    if not machine.active_version_id:
        raise HTTPException(status_code=400, detail="No active index for this machine")
    
    # Get active version
    version = db.query(MachineIndexVersion).filter(
        MachineIndexVersion.id == machine.active_version_id
    ).first()
    
    if not version:
        raise HTTPException(status_code=404, detail="Active version not found")
    
    # Try cache first
    index_data = _get_cached_index(str(machine.id), str(version.id))
    
    if not index_data:
        # Load from storage
        try:
            index_bytes = load_index_file(version.gcs_bucket, version.gcs_object)
            index_data = json.loads(index_bytes.decode('utf-8'))
            _set_cached_index(str(machine.id), str(version.id), index_data)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Index file not found in storage")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load index: {e}")
    
    # Search
    from backend.utils.index_search import normalize_error_message
    normalized_query = normalize_error_message(query_text)
    results = search_chunk_index(query_text, index_data)
    
    elapsed_ms = int((time.time() - start_time) * 1000)
    match_types = {'exact': 0, 'partial': 0}
    for r in results:
        match_types[r.get('match_type', 'partial')] += 1
    
    logger.info(
        f"Search result: machine_id={machine_id}, "
        f"normalized_query='{normalized_query[:50]}...', "
        f"match_type=exact:{match_types['exact']}/partial:{match_types['partial']}, "
        f"total_results={len(results)}, "
        f"elapsed_ms={elapsed_ms}"
    )
    
    return {
        "machine_id": machine_id,
        "query": query_text,
        "results": results,
        "total_matches": len(results)
    }


# Email Script Route

@router.post("/email-ingest")
async def email_ingest_script(
    email: str = Form(...),
    user: DevUser = Depends(require_role)
):
    """Email ingest.py script to technician."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email import encoders
    
    # Check SMTP configuration
    smtp_host = os.environ.get('SMTP_HOST')
    smtp_port = os.environ.get('SMTP_PORT', '587')
    smtp_username = os.environ.get('SMTP_USERNAME')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    smtp_use_tls = os.environ.get('SMTP_USE_TLS', 'true').lower() == 'true'
    from_email = os.environ.get('INVITE_FROM_EMAIL', 'noreply@example.com')
    from_name = os.environ.get('INVITE_FROM_NAME', 'Arrow Log Helper')
    
    # Log configuration status (without sensitive data)
    logger.info(f"SMTP config check: host={'SET' if smtp_host else 'NOT SET'}, username={'SET' if smtp_username else 'NOT SET'}, password={'SET' if smtp_password else 'NOT SET'}")
    
    if not smtp_host:
        logger.warning("Email request received but SMTP_HOST not configured")
        raise HTTPException(
            status_code=503,
            detail="SMTP not configured. SMTP_HOST environment variable is not set. Email functionality is disabled in development mode."
        )
    
    if not smtp_username or not smtp_password:
        logger.warning(f"SMTP credentials incomplete: username={'SET' if smtp_username else 'MISSING'}, password={'SET' if smtp_password else 'MISSING'}")
        raise HTTPException(
            status_code=503,
            detail="SMTP credentials incomplete. Both SMTP_USERNAME and SMTP_PASSWORD must be set for Gmail authentication."
        )
    
    # Read ingest.py file
    ingest_path = os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'ingest.py')
    if not os.path.exists(ingest_path):
        raise HTTPException(status_code=500, detail="ingest.py file not found")
    
    try:
        with open(ingest_path, 'rb') as f:
            ingest_content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read ingest.py: {e}")
    
    # Create email
    msg = MIMEMultipart()
    msg['From'] = f"{from_name} <{from_email}>"
    msg['To'] = email
    msg['Subject'] = "Error Debug Index Script - ingest.py"
    
    # Email body with exact instructions
    body = """Hello,

Please find attached the ingest.py script for indexing your printer codebase.

Instructions:
1) Save ingest.py to /root on the printer:
   - Copy the attached ingest.py file to /root/ingest.py

2) Run the script (no arguments needed, defaults are set):
   python /root/ingest.py

The script will:
- Index all Python files under /opt/memjet (default --root)
- Extract functions and error messages
- Generate /root/index.json (default --out)
- Show progress updates (default --progress)

After indexing completes, upload the /root/index.json file to the Error Debug portal.

If you have questions, please contact support.

Best regards,
Arrow Log Helper
"""
    
    msg.attach(MIMEText(body, 'plain'))
    
    # Attach ingest.py
    attachment = MIMEBase('application', 'octet-stream')
    attachment.set_payload(ingest_content)
    encoders.encode_base64(attachment)
    attachment.add_header(
        'Content-Disposition',
        f'attachment; filename=ingest.py'
    )
    msg.attach(attachment)
    
    # Send email
    try:
        server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=10)
        if smtp_use_tls:
            server.starttls()
        if smtp_username and smtp_password:
            server.login(smtp_username, smtp_password)
        server.send_message(msg)
        server.quit()
        logger.info(f"Email sent successfully to {email}")
        
        return {
            "message": "Email sent successfully",
            "to": email
        }
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email to {email}: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"SMTP server error: {str(e)}. Please check SMTP configuration."
        )
    except Exception as e:
        logger.error(f"Unexpected error sending email to {email}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send email: {str(e)}"
        )


@router.get("/machines/{machine_id}/error-keys")
async def get_machine_error_keys(
    machine_id: str,
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """Get all error keys from a machine's active index."""
    try:
        machine_uuid = uuid.UUID(machine_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid machine_id format")
    
    machine = db.query(Machine).filter(Machine.id == machine_uuid).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")
    
    if not machine.active_version_id:
        return {
            "machine_id": machine_id,
            "error_keys": [],
            "total_errors": 0,
            "message": "No active index for this machine"
        }
    
    # Load active index
    try:
        version = db.query(MachineIndexVersion).filter(
            MachineIndexVersion.id == machine.active_version_id
        ).first()
        if not version:
            raise HTTPException(status_code=404, detail="Active version not found")
        
        # Try cache first
        index_data = _get_cached_index(machine_id, str(version.id))
        if not index_data:
            # Load from storage
            try:
                index_bytes = load_index_file(version.gcs_bucket, version.gcs_object)
                index_data = json.loads(index_bytes.decode('utf-8'))
                _set_cached_index(machine_id, str(version.id), index_data)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Index file not found in storage")
            except Exception as e:
                logger.error(f"Failed to load index: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to load index: {e}")
        
        # Extract error keys from error_index
        error_index = index_data.get('error_index', {})
        error_keys = []
        
        for error_key, chunk_ids in error_index.items():
            error_keys.append({
                "key": error_key,
                "chunk_count": len(chunk_ids) if isinstance(chunk_ids, list) else 1
            })
        
        # Sort by chunk count (descending) then by key
        error_keys.sort(key=lambda x: (-x['chunk_count'], x['key']))
        
        return {
            "machine_id": machine_id,
            "error_keys": error_keys,
            "total_errors": len(error_keys),
            "total_chunks": version.total_chunks,
            "indexed_at": version.indexed_at.isoformat() if version.indexed_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get error keys: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get error keys: {str(e)}")

