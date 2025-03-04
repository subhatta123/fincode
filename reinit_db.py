from report_manager_new import ReportManager
import sqlite3

def main():
    """Reinitialize the database with the correct schema"""
    try:
        # First drop existing tables
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS schedules")
            cursor.execute("DROP TABLE IF EXISTS schedule_runs")
            cursor.execute("DROP TABLE IF EXISTS _internal_tableau_connections")
            conn.commit()
            print("Dropped existing tables")
        
        # Initialize ReportManager which will create new tables
        report_manager = ReportManager()
        print("Database reinitialized successfully!")
    except Exception as e:
        print(f"Error reinitializing database: {str(e)}")

if __name__ == "__main__":
    main() 