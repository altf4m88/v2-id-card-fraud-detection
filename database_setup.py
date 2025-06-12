import sqlite3
import os
import logging

# --- Configuration ---
DB_FILE = "identity_database.db"

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_database():
    """
    Sets up the SQLite database.
    This creates the database file and the 'id_cards' table with a detailed schema,
    if it doesn't already exist.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Check if the table already exists to prevent errors on re-running
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='id_cards'")
        if cursor.fetchone():
            logger.info(f"Table 'id_cards' already exists in '{DB_FILE}'. Setup not required.")
            return

        # --- Create the 'id_cards' table with the new detailed schema ---
        create_table_query = """
        CREATE TABLE id_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nik TEXT NOT NULL UNIQUE,
            nama TEXT NOT NULL,
            tempat_lahir TEXT NOT NULL,
            tanggal_lahir TEXT NOT NULL,
            jenis_kelamin TEXT NOT NULL,
            gol_darah TEXT,
            alamat TEXT NOT NULL,
            rt_rw TEXT NOT NULL,
            kel_desa TEXT NOT NULL,
            kecamatan TEXT NOT NULL,
            agama TEXT NOT NULL,
            status_perkawinan TEXT NOT NULL,
            kewarganegaraan TEXT NOT NULL,
            berlaku_hingga TEXT NOT NULL,
            place_of_creation TEXT,
            date_of_creation TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        cursor.execute(create_table_query)
        conn.commit()
        logger.info(f"Successfully created table 'id_cards' in '{DB_FILE}'.")

    except sqlite3.Error as e:
        logger.error(f"An error occurred while setting up the database: {e}")

    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

if __name__ == "__main__":
    logger.info("Initializing database setup...")
    setup_database()