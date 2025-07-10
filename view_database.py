import sqlite3
from rich.console import Console
from rich.table import Table

# Configuration
DB_FILE = "identity_database.db"

def view_id_cards():
    """
    Display all ID card records in a beautiful table using Rich.
    """
    try:
        # Connect to the database
        conn = sqlite3.connect(DB_FILE)
        # Enable dictionary cursor for easier column access
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Query all records
        cursor.execute("SELECT * FROM id_cards")
        records = cursor.fetchall()

        if not records:
            print("No records found in the database.")
            return

        # Create a table
        table = Table(
            title="ID Card Records",
            show_header=True,
            header_style="bold magenta",
            border_style="blue"
        )

        # Add columns based on the schema
        table.add_column("NIK", style="cyan")
        table.add_column("Nama", style="green")
        table.add_column("TTL", style="yellow")
        table.add_column("Gender", style="cyan")
        table.add_column("Alamat", style="green", max_width=30)
        table.add_column("RT/RW", style="yellow")
        table.add_column("Kelurahan", style="cyan")
        table.add_column("Kecamatan", style="green")
        table.add_column("Agama", style="yellow")
        table.add_column("Status", style="cyan")
        table.add_column("Berlaku Hingga", style="green")

        # Add rows
        for record in records:
            # Combine tempat and tanggal lahir
            ttl = f"{record['tempat_lahir']}, {record['tanggal_lahir']}"
            
            table.add_row(
                str(record['nik']),
                record['nama'],
                ttl,
                record['jenis_kelamin'],
                record['alamat'],
                record['rt_rw'],
                record['kel_desa'],
                record['kecamatan'],
                record['agama'],
                record['status_perkawinan'],
                record['berlaku_hingga']
            )

        # Create and print to console
        console = Console()
        console.print("\n")  # Add some spacing
        console.print(table)
        console.print("\n")  # Add some spacing

    except sqlite3.Error as e:
        print(f"Database error occurred: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    view_id_cards()
