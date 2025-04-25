import os
import pickle
import sqlite3
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
                return (
                    helpers.booler(row["validated"]),
                    helpers.booler(row["user_entered"]),
                    pickle.loads(row["data"]),
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
