import sqlite3
import logging
from typing import Dict, Any

from pydantic import BaseModel, Field
from langchain_core.tools import tool

# --- Configuration ---
DB_FILE = "identity_database.db"

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Tool 1: Check for Duplicate NIK (No changes needed here) ---
class CheckDuplicateNikInput(BaseModel):
    """Input schema for the NIK duplication check tool."""
    nik: str = Field(description="The 16-digit NIK to check for in the database.")

@tool("check_duplicate_nik_tool", args_schema=CheckDuplicateNikInput)
def check_duplicate_nik_tool(nik: str) -> Dict[str, str]:
    """Checks if a given NIK already exists in the 'id_cards' table."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM id_cards WHERE nik = ?", (nik,))
        if cursor.fetchone():
            logger.warning(f"Duplicate NIK found in database: {nik}")
            return {"status": "duplicate", "nik": nik}
        else:
            return {"status": "not_found", "nik": nik}
    except sqlite3.Error as e:
        logger.error(f"Database error while checking NIK {nik}: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        if conn:
            conn.close()

# --- Tool 2: Insert ID Card Data (Corrected and Enhanced) ---
class InsertIdCardInput(BaseModel):
    """Input schema for the tool that inserts validated ID card data."""
    data: Dict[str, Any] = Field(description="A dictionary containing all the extracted and validated ID card fields from the vision model.")

@tool("insert_id_card_tool", args_schema=InsertIdCardInput)
def insert_id_card_tool(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Parses, transforms, and inserts a new ID card record into the database.
    This tool maps keys from the AI model output to the database schema.
    """
    # Define the mapping from AI output keys to database columns
    key_mapping = {
        'NIK': 'nik',
        'Nama': 'nama',
        'Jenis Kelamin': 'jenis_kelamin',
        'Gol. Darah': 'gol_darah',
        'Alamat': 'alamat',
        'RT/RW': 'rt_rw',
        'Kel/Desa': 'kel_desa',
        'Kecamatan': 'kecamatan',
        'Agama': 'agama',
        'Status Perkawinan': 'status_perkawinan',
        'Kewarganegaraan': 'kewarganegaraan',
        'Berlaku Hingga': 'berlaku_hingga',
        'Place and Date of Creation': 'place_of_creation',
    }

    # Create a new dictionary with the correct keys
    db_record = {}
    for ai_key, db_key in key_mapping.items():
        db_record[db_key] = data.get(ai_key)

    # Handle special combined fields
    try:
        if 'Tempat/Tgl Lahir' in data and data['Tempat/Tgl Lahir']:
            parts = data['Tempat/Tgl Lahir'].split(',')
            db_record['tempat_lahir'] = parts[0].strip()
            if len(parts) > 1:
                db_record['tanggal_lahir'] = parts[1].strip()
            else: # Handle cases where there might be no comma
                db_record['tanggal_lahir'] = None
    except Exception as e:
        logger.error(f"Error parsing 'Tempat/Tgl Lahir': {data.get('Tempat/Tgl Lahir')} - {e}")
        return {"status": "error", "error": "Failed to parse 'Tempat/Tgl Lahir' field."}

    # Optional: Split place and date of creation
    if db_record.get('place_of_creation'):
        parts = db_record['place_of_creation'].split(' ')
        db_record['place_of_creation'] = parts[0].strip()
        if len(parts) > 1:
             db_record['date_of_creation'] = ' '.join(parts[1:]).strip()


    # Now, validate that all required database fields are present
    required_db_keys = [
        'nik', 'nama', 'tempat_lahir', 'tanggal_lahir', 'jenis_kelamin', 'alamat', 'rt_rw',
        'kel_desa', 'kecamatan', 'agama', 'status_perkawinan', 'kewarganegaraan', 'berlaku_hingga'
    ]
    
    missing_keys = [key for key in required_db_keys if not db_record.get(key)]
    if missing_keys:
        error_msg = f"After parsing, required fields are still missing: {', '.join(missing_keys)}"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}


    # --- Proceed with Database Insertion ---
    query = """
    INSERT INTO id_cards (nik, nama, tempat_lahir, tanggal_lahir, jenis_kelamin, gol_darah, alamat, rt_rw, kel_desa, kecamatan, agama, status_perkawinan, kewarganegaraan, berlaku_hingga, place_of_creation, date_of_creation)
    VALUES (:nik, :nama, :tempat_lahir, :tanggal_lahir, :jenis_kelamin, :gol_darah, :alamat, :rt_rw, :kel_desa, :kecamatan, :agama, :status_perkawinan, :kewarganegaraan, :berlaku_hingga, :place_of_creation, :date_of_creation)
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(query, db_record)
        conn.commit()
        logger.info(f"Successfully inserted new record for NIK: {db_record['nik']}")
        return {"status": "success", "message": f"Record for NIK {db_record['nik']} added successfully."}
    except sqlite3.IntegrityError:
        logger.warning(f"Attempted to insert a duplicate NIK: {db_record['nik']}")
        return {"status": "error", "error": "This NIK already exists in the database."}
    except sqlite3.Error as e:
        logger.error(f"Database error during insertion for NIK {db_record['nik']}: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        if conn:
            conn.close()