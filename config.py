import os
from pathlib import Path

# Determine if we're running on Render
IS_RENDER = os.getenv('RENDER', False)

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Database directory
if IS_RENDER:
    # Use /tmp directory on Render
    DATA_DIR = Path('/tmp/data')
else:
    # Use local data directory
    DATA_DIR = BASE_DIR / 'data'

# Create data directory if it doesn't exist
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database path
DB_PATH = DATA_DIR / 'tableau_data.db'

# Reports directory
REPORTS_DIR = DATA_DIR / 'reports'
REPORTS_DIR.mkdir(exist_ok=True)

# Public reports directory
PUBLIC_REPORTS_DIR = Path('static/reports')
PUBLIC_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Email settings
SMTP_SERVER = os.getenv('SMTP_SERVER')
SMTP_PORT = os.getenv('SMTP_PORT')
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')

# Twilio settings
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')

# Application URL
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8501') 