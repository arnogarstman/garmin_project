"""Moving the built DuckDB warehouse between the pipeline and the dashboard
through object storage. The pipeline builds the warehouse on local disk and
publishes it as one blob; the dashboard keeps a read-only local copy that it
refreshes when the published blob changes. Uploads replace the blob in one
commit, so a reader never sees half a file."""

import logging
import os
import tempfile
import time
from pathlib import Path

import fsspec

logger = logging.getLogger(__name__)

CHECK_INTERVAL_S = 300.0
_last_check: dict[str, float] = {}
_last_version: dict[str, str] = {}


def publish(local: Path, url: str) -> None:
    """Upload the warehouse file to `url` (e.g. abfs://warehouse/warehouse.duckdb)."""
    fs, path = fsspec.core.url_to_fs(url)
    fs.put_file(str(local), path)
    logger.info("Published %s (%.1f MB) to %s", local, local.stat().st_size / 1e6, url)


def sync_local_copy(url: str, local: Path, check_interval_s: float = CHECK_INTERVAL_S) -> None:
    """Make sure `local` is a current copy of the published warehouse.

    The remote version (its etag, or modification time on file systems without
    one) is checked at most every `check_interval_s` seconds; a download only
    happens when it changed. The new copy replaces the old one atomically, so
    queries running on the old file are not disturbed.
    """
    now = time.monotonic()
    if local.exists() and now - _last_check.get(url, -check_interval_s) < check_interval_s:
        return
    _last_check[url] = now

    fs, path = fsspec.core.url_to_fs(url)
    info = fs.info(path)
    version = str(info.get("etag") or info.get("mtime") or info.get("last_modified"))
    if local.exists() and _last_version.get(url) == version:
        return

    local.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=local.parent, suffix=".duckdb.part")
    os.close(fd)
    try:
        fs.get_file(path, tmp)
        os.replace(tmp, local)
    finally:
        Path(tmp).unlink(missing_ok=True)
    _last_version[url] = version
    logger.info("Fetched warehouse version %s from %s", version, url)
