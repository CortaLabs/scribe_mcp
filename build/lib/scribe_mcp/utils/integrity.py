"""
File integrity utilities for Scribe MCP log rotation system.

Provides cryptographic SHA-256 hashing functions for file integrity verification
and tamper detection in log rotation operations.
"""

import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
import json
from datetime import datetime


def compute_file_hash(file_path: str) -> Tuple[str, int]:
    """
    Compute SHA-256 hash of a file and return both hash and file size.

    Args:
        file_path: Path to the file to hash

    Returns:
        Tuple of (hex_digest: str, file_size: int)

    Raises:
        FileNotFoundError: If file doesn't exist
        PermissionError: If file can't be read
        OSError: If other I/O errors occur
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    sha256_hash = hashlib.sha256()
    file_size = 0

    try:
        with open(path, 'rb') as f:
            # Read file in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
                file_size += len(chunk)

        return sha256_hash.hexdigest(), file_size

    except PermissionError:
        raise PermissionError(f"Permission denied reading file: {file_path}")
    except OSError as e:
        raise OSError(f"Error reading file {file_path}: {e}")


def verify_file_integrity(file_path: str, expected_hash: str) -> Tuple[bool, str]:
    """
    Verify file integrity by comparing its hash with expected hash.

    Args:
        file_path: Path to the file to verify
        expected_hash: Expected SHA-256 hash (hex digest)

    Returns:
        Tuple of (is_valid: bool, actual_hash: str)
    """
    try:
        actual_hash, file_size = compute_file_hash(file_path)
        is_valid = actual_hash.lower() == expected_hash.lower()
        return is_valid, actual_hash
    except (FileNotFoundError, PermissionError, OSError) as e:
        return False, f"Error computing hash: {e}"


def create_file_metadata(file_path: str, additional_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create comprehensive file metadata including hash, size, and timestamps.

    Args:
        file_path: Path to the file to analyze
        additional_metadata: Optional additional metadata to include

    Returns:
        Dictionary containing file metadata
    """
    path = Path(file_path)

    # Basic file stats
    stat = path.stat()

    # Compute hash and size
    try:
        file_hash, file_size = compute_file_hash(file_path)
    except (FileNotFoundError, PermissionError, OSError) as e:
        file_hash = f"Error: {e}"
        file_size = 0

    # Build metadata
    metadata = {
        "file_path": str(path.absolute()),
        "file_name": path.name,
        "file_size": file_size,
        "sha256_hash": file_hash,
        "created_timestamp": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified_timestamp": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "is_readable": os.access(file_path, os.R_OK),
        "is_writable": os.access(file_path, os.W_OK),
    }

    # Add additional metadata if provided
    if additional_metadata:
        metadata.update(additional_metadata)

    return metadata


def hash_file_string(file_path: str) -> str:
    """
    Compute SHA-256 hash and return as formatted string.

    Args:
        file_path: Path to the file to hash

    Returns:
        Formatted hash string: "sha256:<hex_digest>"
    """
    try:
        file_hash, _ = compute_file_hash(file_path)
        return f"sha256:{file_hash}"
    except (FileNotFoundError, PermissionError, OSError) as e:
        return f"sha256:error_{str(e).replace(' ', '_')}"


def count_file_lines(file_path: str) -> int:
    """
    Count the number of lines in a text file.

    Args:
        file_path: Path to the text file

    Returns:
        Number of lines in the file

    Raises:
        FileNotFoundError: If file doesn't exist
        UnicodeDecodeError: If file is not valid text
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except UnicodeDecodeError:
        raise UnicodeDecodeError(f"File is not valid text: {file_path}")
    except OSError as e:
        raise OSError(f"Error reading file {file_path}: {e}")


def create_rotation_metadata(
    archived_file_path: str,
    rotation_uuid: str,
    rotation_timestamp: str,
    sequence_number: int,
    previous_hash: Optional[str] = None,
    log_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create comprehensive rotation metadata for audit trail.

    Args:
        archived_file_path: Path to the archived log file
        rotation_uuid: Unique identifier for this rotation
        rotation_timestamp: ISO format timestamp of rotation
        sequence_number: Sequential rotation number
        previous_hash: Hash of previous log file in chain (if any)

    Returns:
        Dictionary containing rotation metadata
    """
    try:
        # Get file metadata
        file_metadata = create_file_metadata(archived_file_path)

        # Count entries (lines) in the archived file
        try:
            entry_count = count_file_lines(archived_file_path)
        except (UnicodeDecodeError, OSError):
            entry_count = -1  # Indicates error counting lines

        rotation_metadata = {
            "rotation_uuid": rotation_uuid,
            "rotation_timestamp_utc": rotation_timestamp,
            "sequence_number": sequence_number,
            "archived_file_path": archived_file_path,
            "archived_file_name": Path(archived_file_path).name,
            "entry_count": entry_count,
            "file_hash": file_metadata.get("sha256_hash"),
            "file_size": file_metadata.get("file_size"),
            "created_timestamp": file_metadata.get("created_timestamp"),
            "modified_timestamp": file_metadata.get("modified_timestamp"),
        }

        if previous_hash:
            rotation_metadata["hash_chain_previous"] = previous_hash
        if log_type:
            rotation_metadata["log_type"] = log_type

        return rotation_metadata

    except Exception as e:
        # Return minimal metadata if full creation fails
        return {
            "rotation_uuid": rotation_uuid,
            "rotation_timestamp_utc": rotation_timestamp,
            "sequence_number": sequence_number,
            "archived_file_path": archived_file_path,
            "error": f"Error creating metadata: {e}",
            "entry_count": -1,
            "file_hash": "error",
            "file_size": 0,
        }


# Performance benchmark utilities
def benchmark_hash_performance(file_path: str) -> Dict[str, float]:
    """
    Benchmark hash computation performance on a file.

    Args:
        file_path: Path to the file to benchmark

    Returns:
        Dictionary with performance metrics
    """
    import time

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = path.stat().st_size

    # Benchmark hash computation
    start_time = time.time()
    try:
        file_hash, _ = compute_file_hash(file_path)
        hash_time = time.time() - start_time

        # Calculate throughput (MB/s)
        throughput_mbps = (file_size / (1024 * 1024)) / hash_time if hash_time > 0 else 0

        return {
            "file_size_mb": file_size / (1024 * 1024),
            "hash_time_seconds": hash_time,
            "throughput_mbps": throughput_mbps,
            "hash_result": file_hash[:16] + "...",  # First 16 chars for verification
        }
    except Exception as e:
        return {
            "file_size_mb": file_size / (1024 * 1024),
            "hash_time_seconds": time.time() - start_time,
            "throughput_mbps": 0,
            "error": str(e),
        }
