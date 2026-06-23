import json
import re
from datetime import datetime, timezone
from pathlib import Path

from modules import helpers
from modules.process_control import is_logscan_maintenance_sidecar

_is_logscan_gzip_path = helpers.is_logscan_gzip_path


def get_logscan_cache_dir():
    cache_dir = Path(helpers.CONFIG_DIR) / "cache" / "logscan"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def normalize_logscan_tool_name(tool_name):
    normalized = str(tool_name or "kometa").strip().lower()
    return "imagemaid" if normalized == "imagemaid" else "kometa"


def get_logscan_live_dir(tool_name="kometa", log_dir=None):
    normalized = normalize_logscan_tool_name(tool_name)
    if normalized == "imagemaid":
        return helpers.get_imagemaid_root_path() / "config" / "logs"
    return Path(log_dir) if log_dir else helpers.get_kometa_log_dir()


def get_logscan_archive_root_dir():
    archive_root = get_logscan_cache_dir() / "archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    return archive_root


def get_logscan_archive_dir(tool_name="kometa"):
    normalized = normalize_logscan_tool_name(tool_name)
    base_archive_dir = get_logscan_archive_root_dir()
    archive_dir = base_archive_dir / normalized
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def detect_logscan_tool_from_path(path, log_dir=None):
    if not path:
        return "kometa"
    try:
        resolved = Path(path).resolve()
    except Exception:
        return "kometa"
    if "imagemaid" in resolved.name.lower():
        return "imagemaid"
    imagemaid_live_dir = get_logscan_live_dir("imagemaid").resolve()
    imagemaid_archive_dir = get_logscan_archive_dir("imagemaid").resolve()
    kometa_live_dir = get_logscan_live_dir("kometa", log_dir=log_dir).resolve()
    kometa_archive_dir = get_logscan_archive_dir("kometa").resolve()
    legacy_archive_dir = get_logscan_archive_root_dir().resolve()
    for tool_name, base_dir in (
        ("imagemaid", imagemaid_archive_dir),
        ("imagemaid", imagemaid_live_dir),
        ("kometa", kometa_archive_dir),
        ("kometa", kometa_live_dir),
    ):
        try:
            resolved.relative_to(base_dir)
            return tool_name
        except ValueError:
            continue
    try:
        resolved.relative_to(legacy_archive_dir)
        return "imagemaid" if "imagemaid" in resolved.name.lower() else "kometa"
    except ValueError:
        pass
    return "kometa"


def build_logscan_archive_filename(path, stats=None, counter=None, preferred_suffix=None):
    path = Path(path)
    if stats is None:
        stats = path.stat()
    timestamp = datetime.fromtimestamp(float(stats.st_mtime), tz=timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    size = int(stats.st_size)
    suffix = preferred_suffix or "".join(path.suffixes)
    if not suffix:
        suffix = ".log"
    stem = path.name
    for suffix_part in path.suffixes:
        if stem.endswith(suffix_part):
            stem = stem[: -len(suffix_part)]
    tool_name = detect_logscan_tool_from_path(path)
    if tool_name == "kometa":
        stem = "meta"
    elif tool_name == "imagemaid":
        stem = "imagemaid"
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-").lower() or "log"
    base_name = f"{stem}-{timestamp}-{size}"
    if counter and counter > 1:
        base_name = f"{base_name}-{counter}"
    return f"{base_name}{suffix}"


def build_logscan_archive_destination(path, archive_dir, stats=None, preferred_suffix=None):
    path = Path(path)
    archive_dir = Path(archive_dir)
    if stats is None:
        stats = path.stat()
    counter = 1
    while True:
        candidate = archive_dir / build_logscan_archive_filename(path, stats=stats, counter=counter, preferred_suffix=preferred_suffix)
        if candidate.resolve() == path.resolve():
            return candidate
        if not candidate.exists():
            return candidate
        counter += 1


def iter_logscan_candidate_files(log_dir=None, include_archive=True, include_compressed=False, tool_name=None):
    tool_names = [normalize_logscan_tool_name(tool_name)] if tool_name else ["kometa", "imagemaid"]
    log_files = []
    for current_tool in tool_names:
        live_dir = get_logscan_live_dir(current_tool, log_dir=log_dir if current_tool == "kometa" else None)
        archive_dir = get_logscan_archive_dir(current_tool) if include_archive else None
        dirs = [live_dir]
        if include_archive and archive_dir:
            dirs.append(archive_dir)
        if include_archive and current_tool == "kometa":
            dirs.append(get_logscan_archive_root_dir())
        patterns = ["*meta*.log*"] if current_tool == "kometa" else ["*.log*"]
        for base_dir in dirs:
            if not base_dir.exists():
                continue
            for pattern in patterns:
                for path in base_dir.glob(pattern):
                    if not path.is_file():
                        continue
                    if is_logscan_maintenance_sidecar(path):
                        continue
                    suffixes = [suffix.lower() for suffix in path.suffixes]
                    if suffixes and suffixes[-1] in (".zip", ".7z"):
                        continue
                    if not include_compressed and suffixes and suffixes[-1] == ".gz":
                        continue
                    if ".log" not in path.name.lower():
                        continue
                    log_files.append(path)

    def _mtime(value):
        try:
            return value.stat().st_mtime
        except Exception:
            return 0

    return sorted({path.resolve() for path in log_files}, key=_mtime)


def get_logscan_log_files(log_dir=None, include_archive=True):
    return iter_logscan_candidate_files(log_dir=log_dir, include_archive=include_archive, include_compressed=True)


def logscan_cache_entry_matches(path, cache_entry=None, stats=None, require_complete=False):
    if not isinstance(cache_entry, dict):
        return False
    if require_complete and cache_entry.get("run_complete") is not True:
        return False
    try:
        stats = stats or Path(path).stat()
    except Exception:
        return False
    cached_mtime = cache_entry.get("mtime")
    cached_size = cache_entry.get("size")
    try:
        if cached_mtime is None or cached_size is None:
            return False
        return float(cached_mtime) == float(stats.st_mtime) and int(cached_size) == int(stats.st_size)
    except Exception:
        return False


def get_logscan_delta_files(log_dir=None, include_archive=True):
    import quickstart

    ingest_cache = quickstart._load_logscan_ingest_cache()
    cache_logs = ingest_cache.get("logs", {}) if isinstance(ingest_cache, dict) else {}
    candidates = []
    for path in get_logscan_log_files(log_dir=log_dir, include_archive=include_archive):
        cache_entry = cache_logs.get(str(path.resolve()), {})
        if not logscan_cache_entry_matches(path, cache_entry=cache_entry):
            candidates.append(path)

    def _mtime_desc(value):
        try:
            return value.stat().st_mtime
        except Exception:
            return 0

    return sorted(candidates, key=_mtime_desc, reverse=True)


def classify_logscan_file_location(path, log_dir=None):
    if not path:
        return "missing"
    try:
        resolved = Path(path).resolve()
    except Exception:
        return "missing"
    legacy_archive_dir = get_logscan_archive_root_dir().resolve()
    for tool_name in ("kometa", "imagemaid"):
        live_dir = get_logscan_live_dir(tool_name, log_dir=log_dir if tool_name == "kometa" else None).resolve()
        archive_dir = get_logscan_archive_dir(tool_name).resolve()
        try:
            resolved.relative_to(archive_dir)
            return "archive"
        except ValueError:
            pass
        try:
            resolved.relative_to(live_dir)
            if tool_name == "kometa":
                return "live" if resolved.name.lower() == "meta.log" else "archive"
            return "live"
        except ValueError:
            pass
    try:
        resolved.relative_to(legacy_archive_dir)
        return "archive"
    except ValueError:
        pass
    return "other"


def format_archived_log_retention_label(keep_limit):
    if keep_limit <= 0:
        return "Keep all archived logs"
    if keep_limit == 1:
        return "Keep last 1 archived log"
    return f"Keep last {keep_limit} archived logs"


def get_logscan_keep_limit(tool_name="kometa"):
    import quickstart

    normalized = normalize_logscan_tool_name(tool_name)
    config_key = "QS_IMAGEMAID_LOG_KEEP" if normalized == "imagemaid" else "QS_KOMETA_LOG_KEEP"
    try:
        return max(0, int(quickstart.app.config.get(config_key, 0) or 0))
    except (TypeError, ValueError):
        return 0


def get_logscan_ingest_cache_path():
    return get_logscan_cache_dir() / "ingest_cache.json"


def load_logscan_ingest_cache():
    cache_path = get_logscan_ingest_cache_path()
    if not cache_path.exists():
        return {"version": 1, "logs": {}}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "logs": {}}
    if not isinstance(data, dict):
        return {"version": 1, "logs": {}}
    logs = data.get("logs")
    if not isinstance(logs, dict):
        logs = {}
    data["version"] = data.get("version", 1)
    data["logs"] = logs
    return data


def save_logscan_ingest_cache(cache):
    if not isinstance(cache, dict):
        return
    if "version" not in cache:
        cache["version"] = 1
    if "logs" not in cache or not isinstance(cache["logs"], dict):
        cache["logs"] = {}
    cache_path = get_logscan_ingest_cache_path()
    try:
        cache_path.write_text(json.dumps(cache, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def clear_logscan_ingest_cache():
    cache_path = get_logscan_ingest_cache_path()
    try:
        if cache_path.exists():
            cache_path.unlink()
    except Exception:
        pass


def remove_logscan_ingest_cache_entries(run_key=None, raw_path=None):
    import quickstart

    cache = quickstart._load_logscan_ingest_cache()
    logs = cache.get("logs", {}) if isinstance(cache, dict) else {}
    if not isinstance(logs, dict):
        return False
    changed = False
    for cache_key, entry in list(logs.items()):
        matches_run = bool(run_key and isinstance(entry, dict) and entry.get("run_key") == run_key)
        matches_path = bool(raw_path and cache_key == raw_path)
        if not matches_run and not matches_path:
            continue
        logs.pop(cache_key, None)
        changed = True
    if changed:
        cache["logs"] = logs
        quickstart._save_logscan_ingest_cache(cache)
    return changed
