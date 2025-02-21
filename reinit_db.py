import sqlite3
from pathlib import Path

def reinit_database():
    """Reinitialize the database with the correct schema"""
    db_path = Path("data/tableau_data.db")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Drop existing tables
            tables_to_drop = [
                'schedules',
                'schedule_runs',
                '_internal_tableau_connections'
            ]
            
            for table in tables_to_drop:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")
            print("Dropped existing tables")
            
            # Create schedules table with proper schema
            cursor.execute("""
                CREATE TABLE schedules (
                    id TEXT PRIMARY KEY,
                    dataset_name TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    schedule_config TEXT NOT NULL,
                    email_config TEXT NOT NULL,
                    format_config TEXT,
                    timezone TEXT DEFAULT 'UTC',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_run TEXT,
                    next_run TEXT,
                    status TEXT DEFAULT 'active'
                )
            """)
            
            # Create schedule_runs table
            cursor.execute("""
                CREATE TABLE schedule_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule_id TEXT NOT NULL,
                    run_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    FOREIGN KEY (schedule_id) REFERENCES schedules (id)
                )
            """)
            
            # Create tableau_connections table
            cursor.execute("""
                CREATE TABLE _internal_tableau_connections (
                    dataset_name TEXT PRIMARY KEY,
                    server_url TEXT NOT NULL,
                    auth_method TEXT NOT NULL,
                    credentials TEXT NOT NULL,
                    site_name TEXT,
                    workbook_name TEXT NOT NULL,
                    view_ids TEXT NOT NULL,
                    view_names TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            print("Database reinitialized successfully with correct schema!")
            
            # Verify the schema
            cursor.execute("PRAGMA table_info(schedules)")
            columns = cursor.fetchall()
            print("\nVerifying schedules table schema:")
            for col in columns:
                print(f"Column: {col[1]}, Type: {col[2]}, NotNull: {col[3]}, DefaultValue: {col[4]}")
            
    except Exception as e:
        print(f"Error reinitializing database: {str(e)}")
        raise

if __name__ == "__main__":
    reinit_database() 