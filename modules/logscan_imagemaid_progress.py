"""Imagemaid live-progress snapshot builder.

Extracted from :mod:`modules.logscan_imagemaid_analysis` to isolate
the 229-line ``build_imagemaid_progress_snapshot`` function.

Turns a parsed imagemaid summary dict (as produced by
:func:`modules.logscan_imagemaid_analyzer.analyze_imagemaid_log_content`)
into a UI-friendly progress payload used by the "Kometa/Imagemaid
is running..." dashboard: table rows for each imagemaid operation
(photo scan, photo remove, restore scan, restore action, empty
trash, clean bundles, optimize db) with per-row status badges and
runtime cells.

Kept as a single public function to preserve the existing call
surface used by ``quickstart.py`` and the various logscan
endpoints.
"""

from __future__ import annotations

from modules.logscan_resume import (
    format_compact_count_brief,
    format_duration_brief,
    format_imagemaid_bytes_brief,
)


def build_imagemaid_progress_snapshot(summary=None):
    summary = summary if isinstance(summary, dict) else {}
    if str(summary.get("tool_name") or "").strip().lower() != "imagemaid":
        return {}

    analysis_counts = summary.get("analysis_counts") if isinstance(summary.get("analysis_counts"), dict) else {}
    section_runtimes = summary.get("section_runtimes") if isinstance(summary.get("section_runtimes"), dict) else {}
    mode = str(summary.get("imagemaid_mode") or "report").strip().lower() or "report"
    run_complete = bool(summary.get("run_complete"))
    completion_reason = str(summary.get("completion_reason") or "").strip().lower()
    error_total = 0
    log_counts = summary.get("log_counts") if isinstance(summary.get("log_counts"), dict) else {}
    for key in ("error", "critical", "trace"):
        if isinstance(log_counts.get(key), (int, float)):
            error_total += int(log_counts.get(key) or 0)
    if isinstance(analysis_counts.get("imagemaid_error_lines"), (int, float)):
        error_total = max(error_total, int(analysis_counts.get("imagemaid_error_lines") or 0))

    rows = []
    total_scan_seconds = 0
    total_action_seconds = 0

    def _runtime_cell(value):
        if not isinstance(value, (int, float)):
            return {}
        seconds = max(0, int(value))
        return {"label": format_duration_brief(seconds), "tone": "primary"}

    def _badge_cell(label, tone="success"):
        text = str(label or "").strip()
        return {"label": text, "tone": tone} if text else {}

    def _row_status(observed=False, enabled=False):
        if completion_reason == "maintenance_blocked_start":
            return "Blocked", " text-bg-warning"
        if observed:
            if run_complete:
                if error_total > 0:
                    return "Completed", " text-bg-warning"
                return "Completed", " text-bg-success"
            if completion_reason == "user_stop":
                return "Stopped", " text-bg-warning"
            return "Observed", " text-bg-primary"
        if enabled:
            if completion_reason == "maintenance_blocked_start":
                return "Blocked", " text-bg-warning"
            return "Pending", " text-bg-secondary"
        return "Skipped", " text-bg-secondary"

    def _append_row(name, row_type, scan_seconds=None, action_seconds=None, items_label="", outcome_label="", enabled=False, items_tone="success", outcome_tone="success"):
        nonlocal total_scan_seconds, total_action_seconds
        observed = any(
            [
                isinstance(scan_seconds, (int, float)),
                isinstance(action_seconds, (int, float)),
                bool(str(items_label or "").strip()),
                bool(str(outcome_label or "").strip()),
            ]
        )
        if not enabled and not observed:
            return
        if isinstance(scan_seconds, (int, float)):
            total_scan_seconds += max(0, int(scan_seconds))
        if isinstance(action_seconds, (int, float)):
            total_action_seconds += max(0, int(action_seconds))
        status, status_class = _row_status(observed=observed, enabled=enabled)
        rows.append(
            {
                "name": name,
                "type": row_type,
                "status": status,
                "status_class": status_class,
                "phase_cells": [
                    _runtime_cell(scan_seconds),
                    _runtime_cell(action_seconds),
                    _badge_cell(items_label, tone=items_tone),
                    _badge_cell(outcome_label, tone=outcome_tone),
                ],
            }
        )

    database_seen = bool(analysis_counts.get("imagemaid_database_seen"))
    local_db_enabled = bool(analysis_counts.get("imagemaid_local_db_enabled"))
    use_existing_enabled = bool(analysis_counts.get("imagemaid_use_existing_enabled"))
    database_downloaded_new = bool(analysis_counts.get("imagemaid_database_downloaded_new"))
    database_download_failed = bool(analysis_counts.get("imagemaid_database_download_failed"))
    database_enabled = database_seen or "database_download" in section_runtimes or "database_query" in section_runtimes
    database_items = ""
    if local_db_enabled:
        database_items = "Local DB"
    elif use_existing_enabled:
        database_items = "Existing DB"
    elif database_downloaded_new:
        database_items = "Downloaded"
    elif database_seen:
        database_items = "Plex API"
    database_outcome = "Failed" if database_download_failed else ("Ready" if database_enabled else "")
    _append_row(
        "Database Prep",
        "Source",
        scan_seconds=section_runtimes.get("database_download"),
        action_seconds=section_runtimes.get("database_query"),
        items_label=database_items,
        outcome_label=database_outcome,
        enabled=database_enabled,
        items_tone="secondary",
        outcome_tone="danger" if database_download_failed else "success",
    )

    report_enabled = mode == "report" or "report_bloat_scan" in section_runtimes or "report_bloat_action" in section_runtimes
    report_outcome = "Reported" if report_enabled and run_complete else ""
    _append_row(
        "Bloat Report",
        "Metadata",
        scan_seconds=section_runtimes.get("report_bloat_scan"),
        action_seconds=section_runtimes.get("report_bloat_action"),
        items_label="Mode report" if report_enabled else "",
        outcome_label=report_outcome,
        enabled=report_enabled,
        items_tone="secondary",
        outcome_tone="success",
    )

    restore_found = int(analysis_counts.get("imagemaid_restore_found_files") or 0) if isinstance(analysis_counts.get("imagemaid_restore_found_files"), (int, float)) else 0
    restore_removed = int(analysis_counts.get("imagemaid_restore_removed_files") or 0) if isinstance(analysis_counts.get("imagemaid_restore_removed_files"), (int, float)) else 0
    restore_recovered = (
        int(analysis_counts.get("imagemaid_restore_recovered_bytes") or 0) if isinstance(analysis_counts.get("imagemaid_restore_recovered_bytes"), (int, float)) else 0
    )
    restore_enabled = mode in {"clear", "restore"} or "restore_dir_scan" in section_runtimes or "restore_dir_action" in section_runtimes or restore_found > 0 or restore_removed > 0
    restore_items = ""
    if restore_removed > 0:
        restore_items = f"Removed {format_compact_count_brief(restore_removed)}"
    elif restore_found > 0:
        restore_items = f"Found {format_compact_count_brief(restore_found)}"
    restore_outcome = format_imagemaid_bytes_brief(restore_recovered) if restore_recovered > 0 else ""
    _append_row(
        "Restore Cache",
        "File cleanup",
        scan_seconds=section_runtimes.get("restore_dir_scan"),
        action_seconds=section_runtimes.get("restore_dir_action"),
        items_label=restore_items,
        outcome_label=restore_outcome,
        enabled=restore_enabled,
        items_tone="primary",
        outcome_tone="success",
    )

    photo_found = int(analysis_counts.get("imagemaid_photo_found_files") or 0) if isinstance(analysis_counts.get("imagemaid_photo_found_files"), (int, float)) else 0
    photo_removed = int(analysis_counts.get("imagemaid_photo_removed_files") or 0) if isinstance(analysis_counts.get("imagemaid_photo_removed_files"), (int, float)) else 0
    photo_recovered = int(analysis_counts.get("imagemaid_photo_recovered_bytes") or 0) if isinstance(analysis_counts.get("imagemaid_photo_recovered_bytes"), (int, float)) else 0
    photo_enabled = (
        bool(analysis_counts.get("imagemaid_photo_transcoder_enabled"))
        or "photo_transcoder_scan" in section_runtimes
        or "photo_transcoder_remove" in section_runtimes
        or photo_found > 0
        or photo_removed > 0
    )
    photo_items = ""
    if photo_removed > 0:
        photo_items = f"Removed {format_compact_count_brief(photo_removed)}"
    elif photo_found > 0:
        photo_items = f"Found {format_compact_count_brief(photo_found)}"
    photo_outcome = format_imagemaid_bytes_brief(photo_recovered) if photo_recovered > 0 else ""
    _append_row(
        "PhotoTranscoder",
        "File cleanup",
        scan_seconds=section_runtimes.get("photo_transcoder_scan"),
        action_seconds=section_runtimes.get("photo_transcoder_remove"),
        items_label=photo_items,
        outcome_label=photo_outcome,
        enabled=photo_enabled,
        items_tone="primary",
        outcome_tone="success",
    )

    for label, enabled_key, started_key, runtime_key in [
        ("Empty Trash", "imagemaid_empty_trash_enabled", "imagemaid_empty_trash_started", "empty_trash_action"),
        ("Clean Bundles", "imagemaid_clean_bundles_enabled", "imagemaid_clean_bundles_started", "clean_bundles_action"),
        ("Optimize DB", "imagemaid_optimize_db_enabled", "imagemaid_optimize_db_started", "optimize_db_action"),
    ]:
        enabled = bool(analysis_counts.get(enabled_key)) or bool(analysis_counts.get(started_key)) or runtime_key in section_runtimes
        runtime_value = section_runtimes.get(runtime_key)
        items_label = "Enabled" if enabled else ""
        outcome_label = "Done" if isinstance(runtime_value, (int, float)) and run_complete else ""
        _append_row(
            label,
            "Plex task",
            scan_seconds=None,
            action_seconds=runtime_value,
            items_label=items_label,
            outcome_label=outcome_label,
            enabled=enabled,
            items_tone="secondary",
            outcome_tone="success",
        )

    if not rows:
        return {}

    total_removed = int(analysis_counts.get("imagemaid_total_removed_files") or 0) if isinstance(analysis_counts.get("imagemaid_total_removed_files"), (int, float)) else 0
    total_recovered = int(analysis_counts.get("imagemaid_total_recovered_bytes") or 0) if isinstance(analysis_counts.get("imagemaid_total_recovered_bytes"), (int, float)) else 0
    completed_count = 0
    for row in rows:
        if row.get("status") in {"Completed", "Skipped"}:
            completed_count += 1

    return {
        "name_label": "Operation",
        "type_label": "Area",
        "columns": [
            {"key": "scan", "label": "Scan Time"},
            {"key": "action", "label": "Action Time"},
            {"key": "items", "label": "Observed"},
            {"key": "outcome", "label": "Result"},
        ],
        "rows": rows,
        "completed_count": completed_count,
        "total_count": len(rows),
        "preparation_label": "",
        "footer_cells": [
            format_duration_brief(total_scan_seconds) if total_scan_seconds > 0 else "",
            format_duration_brief(total_action_seconds) if total_action_seconds > 0 else "",
            f"Removed {format_compact_count_brief(total_removed)}" if total_removed > 0 else "",
            format_imagemaid_bytes_brief(total_recovered) if total_recovered > 0 else "",
        ],
        "total_label": (
            format_duration_brief(summary.get("run_time_seconds")) if isinstance(summary.get("run_time_seconds"), (int, float)) and summary.get("run_time_seconds") else ""
        ),
    }
