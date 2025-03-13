import os
import pickle
import sqlite3

from flask import current_app as app

from modules import helpers

# Ensure the 'config' folder exists
CONFIG_DIR = os.path.join(os.getcwd(), "config")  # Ensures it's created in the current working directory
os.makedirs(CONFIG_DIR, exist_ok=True)

# Correctly set the database path
DATABASE_PATH = os.path.join(CONFIG_DIR, "quickstart.sqlite")


def persisted_section_table_create():
    return """CREATE TABLE IF NOT EXISTS section_data (
                                        name TEXT NOT NULL,
                                        section TEXT NOT NULL,
                                        validated BOOLEAN NOT NULL,
                                        user_entered BOOLEAN NOT NULL,
                                        data TEXT,
                                        PRIMARY KEY (name, section)
                                        );"""


def save_section_data(section, validated, user_entered, data, name="default"):
    try:
        sqliteConnection = sqlite3.connect(
            DATABASE_PATH,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )

        cursor = sqliteConnection.cursor()

        sqlite_create_table_query = persisted_section_table_create()

        cursor = sqliteConnection.cursor()

        cursor.execute(sqlite_create_table_query)

        # insert a new record or ignore an existing record
        sqlite_insert_with_param = """INSERT OR IGNORE INTO 'section_data'
                          ('name', 'section', 'validated', 'user_entered', 'data')
                          VALUES (?, ?, ?, ?, ?);"""

        pickled_data = pickle.dumps(data)

        data_tuple = (name, section, validated, user_entered, pickled_data)

        cursor.execute(sqlite_insert_with_param, data_tuple)

        # update an existing record
        sqlite_update_with_param = """UPDATE 'section_data'
                          SET 'validated' = ?,
                          'user_entered' = ?,
                          'data' = ?
                          WHERE name == ? AND
                          section == ?;"""

        data_tuple = (validated, user_entered, pickled_data, name, section)

        cursor.execute(sqlite_update_with_param, data_tuple)

        sqliteConnection.commit()

        cursor.close()

    except sqlite3.Error as error:
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Error while working with SQLite", error)
    finally:
        if sqliteConnection:
            sqliteConnection.close()


def retrieve_section_data(name, section):
    sqliteConnection = None  # Initialize the sqliteConnection variable
    try:
        try:
            sqliteConnection = sqlite3.connect(
                DATABASE_PATH,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
        except sqlite3.Error as error:
            if app.config["QS_DEBUG"]:
                print("[DEBUG] Error while connecting to SQLite", error)
                return False, False, None

        cursor = sqliteConnection.cursor()

        sqlite_create_table_query = persisted_section_table_create()

        cursor = sqliteConnection.cursor()
        cursor.execute(sqlite_create_table_query)

        sqlite_select_query = """SELECT validated, user_entered, data from section_data where name == ? AND section == ?"""

        data_tuple = (name, section)
        cursor.execute(sqlite_select_query, data_tuple)
        records = cursor.fetchall()

        if len(records) > 0:
            # since name-section is the primary key, there should be just one result here
            # [(1, 1, b'\x80\x04\x95\xad\x00\x00\x00\x00\x00\x00\x00}\x94(\x8c\x04plex\x94}\x94(\x8c\x03url\x94\x8c\x19http://192.168.1.11:32400\x94\x8c\x05token\x94\x8c\x142PxWuxX_NydKLKKEt3Z2\x94\x8c\x08db_cache\x94K(\x8c\x07timeout\x94K<\x8c\nverify_ssl\x94\x89\x8c\rclean_bundles\x94\x89\x8c\x0bempty_trash\x94\x89\x8c\x08optimize\x94\x89u\x8c\x05valid\x94\x88u.')]
            validated = helpers.booler(records[0][0])
            user_entered = helpers.booler(records[0][1])
            data = pickle.loads(records[0][2])
        else:
            validated = False
            user_entered = False
            data = None

        cursor.close()

    except sqlite3.Error as error:
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Error while working with SQLite", error)
    finally:
        if sqliteConnection:
            sqliteConnection.close()

    return validated, user_entered, data


def reset_data(name, section=None):
    try:
        sqliteConnection = sqlite3.connect(
            DATABASE_PATH,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        cursor = sqliteConnection.cursor()

        if section:
            sqlite_delete_query = (
                """DELETE from section_data where name == ? AND section == ?"""
            )

            data_tuple = (name, section)
        else:
            sqlite_delete_query = """DELETE from section_data where name == ?"""

            data_tuple = name

        cursor.execute(sqlite_delete_query, (data_tuple,))

        sqliteConnection.commit()

        cursor.close()

    except sqlite3.Error as error:
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Error while working with SQLite", error)
    finally:
        if sqliteConnection:
            sqliteConnection.close()


def get_unique_config_names():
    try:
        sqliteConnection = sqlite3.connect(DATABASE_PATH)
        cursor = sqliteConnection.cursor()
        query = "SELECT DISTINCT name FROM section_data ORDER BY name ASC"
        cursor.execute(query)
        configs = [row[0] for row in cursor.fetchall()]
        return configs
    except sqlite3.Error as error:
        if app.config["QS_DEBUG"]:
            print("[DEBUG] Error while fetching configurations:", error)
            return []
    finally:
        if sqliteConnection:
            sqliteConnection.close()
