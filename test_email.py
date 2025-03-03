from report_manager_new import ReportManager
import pandas as pd
import os
import sqlite3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Print environment variables for verification
print("\nEnvironment Variables:")
print(f"SMTP_SERVER: {os.getenv('SMTP_SERVER')}")
print(f"SMTP_PORT: {os.getenv('SMTP_PORT')}")
print(f"SENDER_EMAIL: {os.getenv('SENDER_EMAIL')}")
print(f"SENDER_PASSWORD: {'*' * 8 if os.getenv('SENDER_PASSWORD') else 'Not Set'}")

# Create sample data
data = {
    'Column1': [1, 2, 3, 4, 5],
    'Column2': ['A', 'B', 'C', 'D', 'E']
}
df = pd.DataFrame(data)

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# Save data to SQLite database
print("\nCreating test database table...")
with sqlite3.connect('data/tableau_data.db') as conn:
    df.to_sql('test_data', conn, if_exists='replace', index=False)
print("Test table created successfully")

# Initialize report manager
report_manager = ReportManager()

# Configure email settings
email_config = {
    'recipients': ['suddh123@gmail.com'],
    'subject': 'Test Email',
    'body': 'This is a test email to verify the configuration.'
}

# Configure format settings
format_config = {
    'header_title': 'Test Report',
    'header_color': '#6f42c1'  # Purple color
}

print("\nAttempting to send test email...")
try:
    success = report_manager.send_report(
        dataset_name='test_data',
        email_config=email_config,
        format_config=format_config
    )
    
    if success:
        print("\nTest email sent successfully!")
    else:
        print("\nFailed to send test email.")
except Exception as e:
    print(f"\nError sending test email: {str(e)}")