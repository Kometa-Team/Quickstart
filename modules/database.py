import json
import os
import pickle
import sqlite3
from flask import current_app as app
from contextlib import closing

from modules import helpers


def get_database_path():
    return os.path.join(helpers.CONFIG_DIR, "quickstart.sqlite")


def persisted_section_table_create():
    return """CREATE TABLE IF NOT EXISTS section_data (
        name TEXT NOT NULL,
        section TEXT NOT NULL,
        validated BOOLEAN NOT NULL,
        user_entered BOOLEAN NOT NULL,
        data TEXT,
        PRIMARY KEY (name, section)
    )"""


def save_section_data(section, validated, user_entered, data, name="default"):
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            cursor.execute(persisted_section_table_create())
            pickled_data = pickle.dumps(data)

            cursor.execute(
                """INSERT OR IGNORE INTO
                    section_data(name, section, validated, user_entered, data)
                    VALUES (?, ?, ?, ?, ?)""",
                (name, section, validated, user_entered, pickled_data),
            )

            cursor.execute(
                """UPDATE section_data
                    SET validated = ?, user_entered = ?, data = ?
                    WHERE name == ? AND section == ?""",
                (validated, user_entered, pickled_data, name, section),
            )


def retrieve_section_data(name, section):
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            cursor.execute(persisted_section_table_create())
            cursor.execute(
                """SELECT validated, user_entered, data from section_data where name == ? AND section == ?""",
                (name, section),
            )
            row = cursor.fetchone()
            if row:
                unpickled = pickle.loads(row["data"])
                if app.config["QS_DEBUG"]:
                    helpers.ts_log(f"Retrieved data for name={name}, section={section}: {unpickled}", level="DEBUG")
                return (
                    helpers.booler(row["validated"]),
                    helpers.booler(row["user_entered"]),
                    unpickled,
                )
    return False, False, None


def reset_data(name, section=None):
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            sql = "DELETE from section_data where name == ?"
            if section:
                cursor.execute(f"{sql} AND section == ?", (name, section))
            else:
                cursor.execute(sql, (name,))


def get_unique_config_names():
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            cursor.execute("SELECT DISTINCT name FROM section_data ORDER BY name ASC")
            return [row["name"] for row in cursor.fetchall()]


def log_runs_table_create():
    return """CREATE TABLE IF NOT EXISTS log_runs (
        run_key TEXT PRIMARY KEY,
        finished_at TEXT,
        run_time_seconds INTEGER,
        kometa_version TEXT,
        kometa_newest_version TEXT,
        config_name TEXT,
        config_hash TEXT,
        run_command TEXT,
        command_signature TEXT,
        section_runtimes TEXT,
        recommendations TEXT,
        log_mtime REAL,
        log_size INTEGER,
        debug_count INTEGER,
        info_count INTEGER,
        warning_count INTEGER,
        error_count INTEGER,
        critical_count INTEGER,
        trace_count INTEGER,
        analysis_counts TEXT,
        library_counts TEXT,
        quickstart_run_marker INTEGER,
        config_line_count INTEGER,
        created_at TEXT
    )"""


def _ensure_log_runs_columns(cursor):
    cursor.execute(log_runs_table_create())
    existing = set()
    for row in cursor.execute("PRAGMA table_info(log_runs)"):
        if isinstance(row, sqlite3.Row):
            name = row["name"] if "name" in row.keys() else None
        else:
            name = row[1] if len(row) > 1 else row[0]
        if name:
            existing.add(name)
    columns = {
        "config_name": "TEXT",
        "config_hash": "TEXT",
        "run_command": "TEXT",
        "command_signature": "TEXT",
        "section_runtimes": "TEXT",
        "recommendations": "TEXT",
        "analysis_counts": "TEXT",
        "library_counts": "TEXT",
        "quickstart_run_marker": "INTEGER",
        "config_line_count": "INTEGER",
    }
    for name, ddl in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE log_runs ADD COLUMN {name} {ddl}")


def save_log_run(summary, recommendations=None):
    if not summary:
        return False
    run_key = summary.get("run_key")
    if not run_key:
        return False

    counts = summary.get("log_counts") or {}
    section_runtimes = summary.get("section_runtimes")
    if isinstance(section_runtimes, dict):
        section_runtimes = json.dumps(section_runtimes, ensure_ascii=True)
    if recommendations is None:
        recommendations = summary.get("recommendations")
    if isinstance(recommendations, (list, dict)):
        recommendations = json.dumps(recommendations, ensure_ascii=True)
    analysis_counts = summary.get("analysis_counts")
    if isinstance(analysis_counts, dict):
        analysis_counts = json.dumps(analysis_counts, ensure_ascii=True)
    library_counts = summary.get("library_counts")
    if isinstance(library_counts, dict):
        library_counts = json.dumps(library_counts, ensure_ascii=True)
    quickstart_run_marker = 1 if summary.get("quickstart_run_marker") else 0
    config_line_count = summary.get("config_line_count")
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            _ensure_log_runs_columns(cursor)
            cursor.execute(
                """INSERT OR IGNORE INTO log_runs (
                    run_key,
                    finished_at,
                    run_time_seconds,
                    kometa_version,
                    kometa_newest_version,
                    config_name,
                    config_hash,
                    run_command,
                    command_signature,
                    section_runtimes,
                    recommendations,
                    log_mtime,
                    log_size,
                    debug_count,
                    info_count,
                    warning_count,
                    error_count,
                    critical_count,
                    trace_count,
                    analysis_counts,
                    library_counts,
                    quickstart_run_marker,
                    config_line_count,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_key,
                    summary.get("finished_at"),
                    summary.get("run_time_seconds"),
                    summary.get("kometa_version"),
                    summary.get("kometa_newest_version"),
                    summary.get("config_name"),
                    summary.get("config_hash"),
                    summary.get("run_command"),
                    summary.get("command_signature"),
                    section_runtimes,
                    recommendations,
                    summary.get("log_mtime"),
                    summary.get("log_size"),
                    counts.get("debug", 0),
                    counts.get("info", 0),
                    counts.get("warning", 0),
                    counts.get("error", 0),
                    counts.get("critical", 0),
                    counts.get("trace", 0),
                    analysis_counts,
                    library_counts,
                    quickstart_run_marker,
                    config_line_count,
                    summary.get("created_at"),
                ),
            )
            return cursor.rowcount > 0
    return False


def clear_log_runs():
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            cursor.execute(log_runs_table_create())
            cursor.execute("DELETE FROM log_runs")
    return True


def get_log_runs(limit=100):
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            _ensure_log_runs_columns(cursor)
            cursor.execute(
                """SELECT run_key, finished_at, run_time_seconds, kometa_version, kometa_newest_version,
                          config_name, config_hash, run_command, command_signature, section_runtimes,
                          recommendations, log_mtime, log_size, debug_count, info_count, warning_count,
                          error_count, critical_count, trace_count, analysis_counts, library_counts,
                          quickstart_run_marker, config_line_count, created_at
                   FROM log_runs
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            for row in rows:
                section_runtimes = row.get("section_runtimes")
                if isinstance(section_runtimes, str):
                    try:
                        row["section_runtimes"] = json.loads(section_runtimes)
                    except json.JSONDecodeError:
                        row["section_runtimes"] = None
                recommendations = row.get("recommendations")
                if isinstance(recommendations, str):
                    try:
                        recommendations = json.loads(recommendations)
                    except json.JSONDecodeError:
                        recommendations = None
                if isinstance(recommendations, list):
                    row["recommendations_count"] = len(recommendations)
                else:
                    row["recommendations_count"] = 0
                row.pop("recommendations", None)
                analysis_counts = row.get("analysis_counts")
                if isinstance(analysis_counts, str):
                    try:
                        row["analysis_counts"] = json.loads(analysis_counts)
                    except json.JSONDecodeError:
                        row["analysis_counts"] = None
                library_counts = row.get("library_counts")
                if isinstance(library_counts, str):
                    try:
                        row["library_counts"] = json.loads(library_counts)
                    except json.JSONDecodeError:
                        row["library_counts"] = None
                row["quickstart_run_marker"] = bool(row.get("quickstart_run_marker"))
    return rows


def get_log_runs_count():
    with sqlite3.connect(get_database_path()) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            _ensure_log_runs_columns(cursor)
            cursor.execute("SELECT COUNT(*) FROM log_runs")
            result = cursor.fetchone()
            return int(result[0]) if result and result[0] is not None else 0


def get_log_run_recommendations(run_key):
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            _ensure_log_runs_columns(cursor)
            cursor.execute(
                "SELECT recommendations FROM log_runs WHERE run_key == ?",
                (run_key,),
            )
            row = cursor.fetchone()
            if not row:
                return []
            recs = row["recommendations"]
            if isinstance(recs, str):
                try:
                    recs = json.loads(recs)
                except json.JSONDecodeError:
                    recs = None
            return recs if isinstance(recs, list) else []


ANALYTICS_DEFAULT_PREFS = {
    "panels": {
        "summary": True,
        "daily_runs": True,
        "runtime_distribution": True,
        "counts_mix": True,
        "issue_trends": True,
        "library_inventory": True,
    },
    "issues": {
        "analyze_convert": True,
        "analyze_anidb": True,
        "analyze_regex": True,
        "people_posters": True,
        "tmdb_api_errors": True,
        "tmdb_fail_errors": False,
        "trakt_connection_errors": True,
        "omdb_errors": True,
        "omdb_api_limit_errors": False,
        "mdblist_errors": True,
        "mdblist_api_limit_errors": False,
        "mdblist_attr_errors": False,
        "mal_connection_errors": False,
        "tautulli_url_errors": False,
        "tautulli_apikey_errors": False,
        "flixpatrol_errors": False,
        "flixpatrol_paywall": False,
        "lsio_errors": False,
        "config_to_be_configured": False,
        "config_api_blank": False,
        "config_bad_version": False,
        "config_missing_path": False,
        "config_cache_false": False,
        "config_mass_update": False,
        "config_other_award": False,
        "config_delete_unmanaged": False,
        "plex_url_errors": False,
        "plex_regex_errors": False,
        "plex_library_errors": True,
        "plex_rounding_errors": False,
        "metadata_attribute_errors": False,
        "metadata_load_errors": True,
        "overlay_load_errors": True,
        "overlay_apply_errors": False,
        "overlay_level_errors": False,
        "overlay_font_missing": False,
        "overlay_image_missing": False,
        "playlist_load_errors": False,
        "playlist_errors": False,
        "overlays_bloat": False,
        "convert_issues": True,
        "image_corrupt": True,
        "image_size": False,
        "runtime_run_order": False,
        "runtime_checkfiles": False,
        "runtime_timeout": True,
        "update_kometa": True,
        "update_plexapi": False,
        "update_git": False,
        "platform_wsl": False,
        "platform_kometa_time": False,
        "platform_memory": False,
        "platform_db_cache": False,
        "anidb_69": True,
        "anidb_auth": False,
        "misc_internal_server": False,
        "misc_no_items": False,
        "misc_pmm_legacy": False,
    },
}


def analytics_preferences_table_create():
    return """CREATE TABLE IF NOT EXISTS analytics_preferences (
        config_name TEXT PRIMARY KEY,
        preferences TEXT,
        updated_at TEXT
    )"""


def _merge_analytics_preferences(preferences):
    merged = {
        "panels": dict(ANALYTICS_DEFAULT_PREFS["panels"]),
        "issues": dict(ANALYTICS_DEFAULT_PREFS["issues"]),
    }
    if not isinstance(preferences, dict):
        return merged
    panels = preferences.get("panels")
    if isinstance(panels, dict):
        for key in merged["panels"]:
            if key in panels:
                merged["panels"][key] = helpers.booler(panels[key])
        if "issue_trends" not in panels:
            legacy_value = None
            if "analyze_issues" in panels:
                legacy_value = helpers.booler(panels["analyze_issues"])
            if "analytics_breakdown" in panels:
                breakdown_value = helpers.booler(panels["analytics_breakdown"])
                legacy_value = breakdown_value if legacy_value is None else legacy_value or breakdown_value
            if legacy_value is not None:
                merged["panels"]["issue_trends"] = legacy_value
    issues = preferences.get("issues")
    if not isinstance(issues, dict):
        issues = preferences.get("breakdown") if isinstance(preferences.get("breakdown"), dict) else None
    if isinstance(issues, dict):
        for key in merged["issues"]:
            if key in issues:
                merged["issues"][key] = helpers.booler(issues[key])
    return merged


def get_analytics_preferences(config_name):
    name = (config_name or "all").strip() or "all"
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            cursor.execute(analytics_preferences_table_create())
            cursor.execute(
                "SELECT preferences FROM analytics_preferences WHERE config_name == ?",
                (name,),
            )
            row = cursor.fetchone()
            if not row:
                return _merge_analytics_preferences(None)
            prefs = row["preferences"]
            if isinstance(prefs, str):
                try:
                    prefs = json.loads(prefs)
                except json.JSONDecodeError:
                    prefs = None
            return _merge_analytics_preferences(prefs)


def save_analytics_preferences(config_name, preferences):
    name = (config_name or "all").strip() or "all"
    merged = _merge_analytics_preferences(preferences)
    payload = json.dumps(merged, ensure_ascii=True)
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            cursor.execute(analytics_preferences_table_create())
            cursor.execute(
                """INSERT OR REPLACE INTO analytics_preferences (
                    config_name,
                    preferences,
                    updated_at
                ) VALUES (?, ?, datetime('now'))""",
                (name, payload),
            )
            return cursor.rowcount > 0


def rename_config(old_name, new_name):
    if not old_name or not new_name or old_name == new_name:
        return {"success": False, "message": "Invalid config name."}
    updated = {"section_data": 0, "log_runs": 0, "analytics_preferences": 0}
    with sqlite3.connect(get_database_path(), detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES) as connection:
        connection.row_factory = sqlite3.Row
        with closing(connection.cursor()) as cursor:
            cursor.execute(persisted_section_table_create())
            cursor.execute(log_runs_table_create())
            cursor.execute(analytics_preferences_table_create())
            _ensure_log_runs_columns(cursor)

            cursor.execute("UPDATE section_data SET name = ? WHERE name == ?", (new_name, old_name))
            updated["section_data"] = cursor.rowcount

            cursor.execute("UPDATE log_runs SET config_name = ? WHERE config_name == ?", (new_name, old_name))
            updated["log_runs"] = cursor.rowcount

            cursor.execute(
                "UPDATE analytics_preferences SET config_name = ? WHERE config_name == ?",
                (new_name, old_name),
            )
            updated["analytics_preferences"] = cursor.rowcount

    updated["success"] = True
    return updated
