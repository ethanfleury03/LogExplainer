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
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_

# Setup logging
logger = logging.getLogger(__name__)

from backend.models.error_debug_models import Machine, MachineIndexVersion
from backend.utils.auth import require_role, DevUser
from backend.utils.db import get_db
from backend.utils.index_storage import save_index_file, load_index_file, delete_index_file
from backend.utils.index_search import search_chunk_index, search_chunk_index_multi
from backend.utils.log_parser import parse_log_line
from backend.utils.query_candidates import build_query_candidates
from backend.utils.anthropic_client import call_claude_messages

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
    debug: bool = Form(False),
    db: Session = Depends(get_db),
    user: DevUser = Depends(require_role)
):
    """Search active index for error message using multi-candidate search."""
    start_time = time.time()
    logger.info(
        f"Search request: machine_id={machine_id}, "
        f"query='{query_text[:50]}{'...' if len(query_text) > 50 else ''}', "
        f"debug={debug}, user={user.email}"
    )
    
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
    
    # Parse log line to get route and normalized query
    parsed = parse_log_line(query_text)
    route = parsed['route']
    confidence = parsed['confidence']
    normalized_query = parsed['query_text']
    
    logger.info(
        f"Log parsed: route={route}, confidence={confidence:.2f}, "
        f"query_text='{normalized_query[:60]}{'...' if len(normalized_query) > 60 else ''}'"
    )
    
    # Check if route filtering is enabled via environment variable (default: False)
    enable_route_filter = os.getenv("ERROR_DEBUG_ENABLE_ROUTE_FILTER", "false").lower() in ("true", "1", "yes")
    
    # Determine allowed routes (only if filtering is enabled)
    # When disabled, always search all chunks regardless of detected route
    allowed_routes = None
    would_have_filtered = None  # For logging when filtering is disabled
    
    if enable_route_filter:
        # Old behavior: filter by route when enabled
        if route in ('kareela', 'gymea') and confidence >= 0.8:
            allowed_routes = [route, 'unknown']
            logger.info(f"Route filtering ENABLED: applying filter routes={allowed_routes}")
        else:
            if route == 'unknown':
                logger.info(f"Route filtering ENABLED: no filter (route={route} is unknown)")
            elif confidence < 0.8:
                logger.info(f"Route filtering ENABLED: no filter (route={route}, confidence={confidence:.2f} < 0.8)")
            else:
                logger.info(f"Route filtering ENABLED: no filter (route={route}, confidence={confidence:.2f})")
    else:
        # New behavior: logging-only, no filtering
        if route in ('kareela', 'gymea') and confidence >= 0.8:
            would_have_filtered = [route, 'unknown']
            logger.info(
                f"Route filtering DISABLED: would have filtered routes={would_have_filtered} (not applied) - "
                f"searching all chunks"
            )
        else:
            logger.info(
                f"Route filtering DISABLED: route={route}, confidence={confidence:.2f} - "
                f"searching all chunks (no filter would have been applied anyway)"
            )
    
    # Generate query candidates (pass enable_route_filter flag)
    try:
        candidates = build_query_candidates(parsed, query_text, enable_route_filter=enable_route_filter)
        logger.info(f"Generated {len(candidates)} query candidates")
        
        if debug:
            logger.debug("Query candidates:")
            for i, cand in enumerate(candidates, 1):
                # Show what would have been applied (for debugging)
                cand_allowed_routes = cand.get('allowed_routes') or cand.get('route_filter') or allowed_routes
                if not enable_route_filter and cand_allowed_routes:
                    allowed_routes_display = f"{cand_allowed_routes} (not applied - filtering disabled)"
                else:
                    allowed_routes_display = cand_allowed_routes
                logger.debug(
                    f"  {i}. {cand['name']}: '{cand['text'][:60]}{'...' if len(cand['text']) > 60 else ''}' "
                    f"(weight={cand['weight']:.1f}, allowed_routes={allowed_routes_display})"
                )
    except Exception as e:
        logger.warning(f"Error generating query candidates, falling back to single query: {e}", exc_info=True)
        candidates = None
    
    # Use multi-candidate search if candidates were generated, otherwise fallback to single query
    debug_info = None
    if candidates and len(candidates) > 0:
        try:
            # Pass enable_route_filter to multi-candidate search
            results, debug_info = search_chunk_index_multi(
                candidates, 
                index_data, 
                allowed_routes=allowed_routes,
                enable_route_filter=enable_route_filter
            )
            
            # Log candidate stats
            logger.info("Candidate search stats:")
            for stat in debug_info.get('candidates', []):
                if 'error' in stat:
                    logger.warning(f"  {stat['name']}: ERROR - {stat['error']}")
                else:
                    # Include candidate text in log (truncate to 80 chars)
                    candidate_text = stat.get('text', '')
                    text_display = candidate_text[:80] + ('...' if len(candidate_text) > 80 else '')
                    match_types = stat['match_counts']
                    match_str = (
                        f"exact:{match_types.get('exact', 0)}/"
                        f"partial:{match_types.get('partial', 0)}/"
                        f"code:{match_types.get('code_search', 0)}"
                    )
                    if match_types.get('token_overlap', 0) > 0:
                        match_str += f"/token_overlap:{match_types.get('token_overlap', 0)}"
                    logger.info(
                        f"  {stat['name']}(\"{text_display}\"): {stat['total_results']} results "
                        f"({match_str})"
                    )
            
            # Log merge summary
            logger.info(
                f"Merge summary: {debug_info['total_unique_hits']} unique hits, "
                f"{debug_info['total_grouped_results']} grouped results"
            )
            
            if debug_info.get('route_filter_fallback_triggered'):
                logger.info("Route filter fallback was triggered (searched globally after route-filtered search returned no results)")
            
            # Log top hits
            top_hits = debug_info.get('top_hits', [])[:5]
            if top_hits:
                logger.info("Top 5 hits:")
                for i, hit in enumerate(top_hits, 1):
                    logger.info(
                        f"  {i}. error_key='{hit['error_key'][:50]}{'...' if len(hit['error_key']) > 50 else ''}' "
                        f"score={hit['score']:.3f}, candidates={hit['candidate_count']}, "
                        f"match_type={hit['match_type']}"
                    )
                    if debug:
                        logger.debug(f"      candidates_hit: {hit['candidates_hit']}")
        
        except Exception as e:
            logger.error(f"Error in multi-candidate search, falling back to single query: {e}", exc_info=True)
            # Fallback to single query
            results = search_chunk_index(
                normalized_query, 
                index_data, 
                allowed_routes=allowed_routes,
                enable_route_filter=enable_route_filter
            )
    else:
        # Fallback to single query search
        logger.info("Using single-query search (no candidates or candidate generation failed)")
        results = search_chunk_index(
            normalized_query, 
            index_data, 
            allowed_routes=allowed_routes,
            enable_route_filter=enable_route_filter
        )
    
    elapsed_ms = int((time.time() - start_time) * 1000)
    match_types = {'exact': 0, 'partial': 0, 'code_search': 0}
    for r in results:
        match_type = r.get('match_type', 'partial')
        if match_type not in match_types:
            match_types[match_type] = 0
        match_types[match_type] += 1
    
    logger.info(
        f"Search complete: machine_id={machine_id}, "
        f"match_type=exact:{match_types.get('exact', 0)}/partial:{match_types.get('partial', 0)}/code_search:{match_types.get('code_search', 0)}, "
        f"total_results={len(results)}, "
        f"elapsed_ms={elapsed_ms}ms"
    )
    
    # Build response
    response = {
        "machine_id": machine_id,
        "query": query_text,
        "parsed": {
            "route": route,
            "confidence": confidence,
            "query_text": normalized_query,
        },
        "results": results,
        "total_matches": len(results)
    }
    
    # Add debug info only if requested
    if debug and debug_info:
        response["debug"] = debug_info
    
    return response


# AI Summary Route

@router.post("/ai-summary")
async def generate_ai_summary(
    payload: dict = Body(...),
    debug: bool = Query(False),
    user: DevUser = Depends(require_role)
):
    """
    Generate AI summary using Claude for a query and its search results.
    
    Accepts the ai_summary_v1 payload and returns a structured summary.
    """
    import time
    start_time = time.time()
    
    logger.info(f"AI Summary request: user={user.email}, debug={debug}")
    
    try:
        # Validate payload schema
        schema_version = payload.get("schema_version")
        if schema_version != "ai_summary_v1":
            raise HTTPException(
                status_code=400,
                detail=f"Invalid schema_version: expected 'ai_summary_v1', got '{schema_version}'"
            )
        
        query_raw = payload.get("query", {}).get("raw")
        if not query_raw:
            raise HTTPException(
                status_code=400,
                detail="Missing required field: query.raw"
            )
        
        # Truncate code fields to prevent oversized prompts
        MAX_CODE_LENGTH = 6000
        truncated_payload = _truncate_code_fields(payload, MAX_CODE_LENGTH)
        
        # Build prompt
        prompt = _build_summary_prompt(truncated_payload)
        
        # Get model from env or use default
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", "800"))
        
        logger.debug(f"Calling Claude: model={model}, prompt_length={len(prompt)}")
        
        # Call Claude
        raw_response = call_claude_messages(
            prompt_text=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=0.2
        )
        
        logger.debug(f"Claude raw response length: {len(raw_response)} chars")
        if debug:
            logger.debug(f"Claude raw response (first 500 chars): {raw_response[:500]}")
        
        # Parse JSON response
        try:
            summary_json = json.loads(raw_response.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude JSON response: {e}")
            logger.debug(f"Raw response (first 500 chars): {raw_response[:500]}")
            
            # Return error with raw response if debug=true
            error_detail = {
                "error": "Failed to parse Claude response as JSON",
                "error_type": "json_parse_error"
            }
            if debug:
                error_detail["raw_response_truncated"] = raw_response[:500]
            
            raise HTTPException(status_code=502, detail=error_detail)
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"AI Summary generated successfully: elapsed_ms={elapsed_ms}")
        
        return {
            "ok": True,
            "summary": summary_json,
            "meta": {
                "model": model,
                "elapsed_ms": elapsed_ms,
                "tokens": None  # Anthropic API doesn't return token count in this response format
            }
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        # API key missing or similar config error
        logger.error(f"Configuration error in AI Summary: {e}")
        raise HTTPException(status_code=500, detail=f"AI service configuration error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error generating AI Summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate AI summary: {str(e)}")


def _truncate_code_fields(payload: dict, max_length: int) -> dict:
    """Truncate code fields in payload to prevent oversized prompts."""
    import copy
    truncated = copy.deepcopy(payload)
    
    results = truncated.get("results", [])
    for result in results:
        chunks = result.get("chunks", [])
        for chunk in chunks:
            if "code" in chunk and chunk["code"]:
                code = chunk["code"]
                if len(code) > max_length:
                    truncated_code = code[:max_length] + f"\n... [truncated {len(code) - max_length} chars]"
                    chunk["code"] = truncated_code
                    logger.debug(f"Truncated code field: {len(code)} -> {len(truncated_code)} chars")
    
    return truncated


def _build_summary_prompt(payload: dict) -> str:
    """Build the prompt for Claude to generate a summary."""
    payload_json = json.dumps(payload, indent=2)
    
    prompt = """You are assisting a field technician debugging printer logs. Use ONLY the provided payload data to generate a structured summary. If evidence is insufficient, say so clearly and set confidence to "low".

Return ONLY valid JSON matching this exact schema. No markdown formatting. No code blocks. No extra text before or after the JSON.

Schema:
{
  "what_it_means": "string - A clear, concise explanation of what this error message means in plain language",
  "most_likely_cause": "string - The most likely root cause based on the code and error context",
  "what_to_check": ["step 1", "step 2", "step 3"] - An array of 3-5 actionable troubleshooting steps,
  "where_in_code": [
    {
      "file_path": "relative/path/to/file.py",
      "lines": "start-end or null",
      "symbol": "function_or_class_name",
      "why": "short reason why this location is relevant"
    }
  ] - An array of 1-3 relevant code locations,
  "confidence": {
    "level": "high|medium|low",
    "why": "string explaining why this confidence level"
  }
}

Important:
- "what_to_check" should be practical troubleshooting steps the technician can perform
- "where_in_code" should reference actual files/symbols from the payload results
- "confidence.level" should reflect how much evidence is available in the payload
- If code fields are truncated or missing, note that in confidence.why
- Keep all strings concise and actionable

Payload data:
"""
    prompt += payload_json
    
    return prompt


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
    # Reload .env file to ensure we have latest values (in case it was updated)
    try:
        from dotenv import load_dotenv
        from pathlib import Path
        repo_root = Path(__file__).parent.parent.parent.resolve()
        env_file = repo_root / '.env'
        if env_file.exists():
            load_dotenv(env_file, override=True)
            logger.info(f"Reloaded .env file from {env_file}")
    except Exception as e:
        logger.warning(f"Could not reload .env file: {e}")
    
    smtp_host = os.environ.get('SMTP_HOST')
    smtp_port = os.environ.get('SMTP_PORT', '587')
    smtp_username = os.environ.get('SMTP_USERNAME')
    smtp_password = os.environ.get('SMTP_PASSWORD')
    smtp_use_tls = os.environ.get('SMTP_USE_TLS', 'true').lower() == 'true'
    from_email = os.environ.get('INVITE_FROM_EMAIL', 'noreply@example.com')
    from_name = os.environ.get('INVITE_FROM_NAME', 'Arrow Log Helper')
    
    # Log configuration status (without sensitive data)
    logger.info(f"SMTP config check: host={'SET' if smtp_host else 'NOT SET'}, username={'SET' if smtp_username else 'NOT SET'}, password={'SET' if smtp_password else 'NOT SET'}")
    logger.info(f"SMTP details: host={smtp_host}, port={smtp_port}, use_tls={smtp_use_tls}, from={from_email}")
    
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
    
    # For Gmail, validate password format (should be 16 chars, no spaces)
    if smtp_host == "smtp.gmail.com":
        password_clean = smtp_password.replace(" ", "")
        if len(password_clean) != 16:
            logger.warning(f"Gmail App Password length is {len(password_clean)} (expected 16). May cause authentication issues.")
        if " " in smtp_password:
            logger.warning("Gmail App Password contains spaces. Removing spaces...")
            smtp_password = password_clean
    
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

