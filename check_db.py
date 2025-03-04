import sqlite3
import json
from pathlib import Path

def check_database(is_superadmin=False):
    """Check database tables and contents. Only superadmin can see schedule_runs table."""
    db_path = Path("data/tableau_data.db")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Show user-facing tables only
            if is_superadmin:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            else:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'schedule_runs'")
            
            tables = cursor.fetchall()
            print("\nUser-facing tables in database:")
            for table in tables:
                print(f"- {table[0]}")
            
            # Only show schedule_runs to superadmin
            if is_superadmin:
                print("\nSchedule Runs table contents:")
                cursor.execute("SELECT * FROM schedule_runs")
                rows = cursor.fetchall()
                if rows:
                    cursor.execute("PRAGMA table_info(schedule_runs)")
                    columns = [col[1] for col in cursor.fetchall()]
                    for row in rows:
                        print("\n" + "="*50)
                        for col, value in zip(columns, row):
                            print(f"{col}: {value}")
                else:
                    print("No schedule runs found")
            
            # Check schedules table
            print("\nSchedules table contents:")
            cursor.execute("SELECT * FROM schedules")
            rows = cursor.fetchall()
            
            if not rows:
                print("No schedules found in database")
                return
            
            # Get column names
            cursor.execute("PRAGMA table_info(schedules)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Print each schedule
            for row in rows:
                print("\n" + "="*50)
                for col, value in zip(columns, row):
                    if col in ['schedule_config', 'email_config', 'format_config'] and value:
                        try:
                            parsed = json.loads(value)
                            print(f"{col}:")
                            print(json.dumps(parsed, indent=2))
                        except:
                            print(f"{col}: {value}")
                    else:
                        print(f"{col}: {value}")
    
    except Exception as e:
        print(f"Error checking database: {str(e)}")

if __name__ == "__main__":
    check_database() 