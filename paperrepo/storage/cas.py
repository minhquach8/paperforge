from __future__ import annotations

import hashlib
from pathlib import Path

import zstandard as zstd


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_path(objects_dir: Path, digest: str) -> Path:
    return objects_dir / digest[:2] / digest[2:]


def put_bytes(objects_dir: Path, data: bytes) -> str:
    """
    Store bytes with zstd compression under objects/<hh>/<rest>.
    Returns the sha256 hex digest (content id).
    """
    digest = _hash_bytes(data)
    dst = blob_path(objects_dir, digest)
    if dst.exists():
        return digest
    dst.parent.mkdir(parents=True, exist_ok=True)
    cctx = zstd.ZstdCompressor(level=10)
    compressed = cctx.compress(data)
    tmp = dst.with_suffix(".tmp")
    tmp.write_bytes(compressed)
    tmp.replace(dst)
    return digest


def put_file(objects_dir: Path, path: Path) -> str:
    return put_bytes(objects_dir, path.read_bytes())


def get_bytes(objects_dir: Path, digest: str) -> bytes:
    src = blob_path(objects_dir, digest)
    if not src.exists():
        raise FileNotFoundError(f"Blob not found: {digest}")
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(src.read_bytes())
