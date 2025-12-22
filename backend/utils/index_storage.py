"""
Index file storage abstraction.

Supports GCS (production) and local file storage (development).
"""

import os
import hashlib
import json
from typing import Dict, Optional, Tuple
from pathlib import Path

# Try to import GCS client (may not be available in dev)
try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False


def _compute_sha256(data: bytes) -> str:
    """Compute SHA256 hash of data."""
    return hashlib.sha256(data).hexdigest()


def _get_local_storage_path(machine_id: str, version_id: str) -> Path:
    """Get local storage path for index file.
    
    Uses absolute path based on repo root to ensure stability
    regardless of where the script is run from.
    Windows-compatible: uses Path which handles / and \ correctly.
    """
    # Get repo root: backend/utils/index_storage.py -> backend/utils -> backend -> repo root
    repo_root = Path(__file__).parent.parent.parent.resolve()
    base_dir = repo_root / 'dev_storage' / 'error_debug' / machine_id
    # Use Path.mkdir for cross-platform compatibility
    base_dir.mkdir(parents=True, exist_ok=True)
    # Path handles path separators correctly on Windows
    return base_dir / f"{version_id}.json"


def save_index_file(machine_id: str, version_id: str, uploaded_bytes: bytes) -> Dict[str, str]:
    """
    Save index file to storage (GCS or local).
    
    Args:
        machine_id: UUID string of machine
        version_id: UUID string of version
        uploaded_bytes: Raw JSON bytes of index file
    
    Returns:
        Dict with keys: bucket (or None), object_path, sha256
    """
    sha256 = _compute_sha256(uploaded_bytes)
    
    # Check for GCS configuration
    gcs_bucket_name = os.environ.get('GCS_BUCKET')
    gcs_credentials = os.environ.get('GCS_CREDENTIALS')
    
    if gcs_bucket_name and GCS_AVAILABLE:
        # Use GCS
        try:
            # Initialize GCS client
            if gcs_credentials:
                # Use credentials file
                client = storage.Client.from_service_account_json(gcs_credentials)
            else:
                # Use default credentials
                client = storage.Client()
            
            bucket = client.bucket(gcs_bucket_name)
            # Object layout: error_debug/{machine_id}/{version_id}.json
            object_path = f"error_debug/{machine_id}/{version_id}.json"
            blob = bucket.blob(object_path)
            
            # Upload file with proper content type
            blob.upload_from_string(
                uploaded_bytes,
                content_type='application/json'
            )
            
            return {
                'bucket': gcs_bucket_name,
                'object_path': object_path,
                'sha256': sha256
            }
        except Exception as e:
            # Fallback to local if GCS fails
            print(f"Warning: GCS upload failed, using local storage: {e}")
    
    # Use local storage
    local_path = _get_local_storage_path(machine_id, version_id)
    local_path.write_bytes(uploaded_bytes)
    
    return {
        'bucket': None,
        'object_path': str(local_path),
        'sha256': sha256
    }


def load_index_file(bucket: Optional[str], object_path: str) -> bytes:
    """
    Load index file from storage (GCS or local).
    
    Args:
        bucket: GCS bucket name (None for local storage)
        object_path: GCS object path or local file path
    
    Returns:
        Raw bytes of index file
    
    Raises:
        FileNotFoundError if file doesn't exist
    """
    if bucket and GCS_AVAILABLE:
        # Load from GCS
        try:
            client = storage.Client()
            gcs_bucket = client.bucket(bucket)
            blob = gcs_bucket.blob(object_path)
            
            if not blob.exists():
                raise FileNotFoundError(f"Index file not found in GCS: {bucket}/{object_path}")
            
            return blob.download_as_bytes()
        except Exception as e:
            raise FileNotFoundError(f"Failed to load from GCS: {e}")
    
    # Load from local storage
    local_path = Path(object_path)
    if not local_path.exists():
        raise FileNotFoundError(f"Index file not found: {object_path}")
    
    return local_path.read_bytes()


def delete_index_file(bucket: Optional[str], object_path: str) -> None:
    """
    Delete index file from storage (GCS or local).
    
    Args:
        bucket: GCS bucket name (None for local storage)
        object_path: GCS object path or local file path
    """
    if bucket and GCS_AVAILABLE:
        # Delete from GCS
        try:
            client = storage.Client()
            gcs_bucket = client.bucket(bucket)
            blob = gcs_bucket.blob(object_path)
            if blob.exists():
                blob.delete()
        except Exception as e:
            print(f"Warning: Failed to delete from GCS: {e}")
    else:
        # Delete from local storage
        local_path = Path(object_path)
        if local_path.exists():
            local_path.unlink()

