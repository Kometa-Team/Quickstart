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
        created_at TEXT
    )"""


def _ensure_log_runs_columns(cursor):
    cursor.execute(log_runs_table_create())
    existing = {row["name"] for row in cursor.execute("PRAGMA table_info(log_runs)")}
    columns = {
        "config_name": "TEXT",
        "config_hash": "TEXT",
        "run_command": "TEXT",
        "command_signature": "TEXT",
        "section_runtimes": "TEXT",
        "recommendations": "TEXT",
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
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                          error_count, critical_count, trace_count, created_at
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
            return rows


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
