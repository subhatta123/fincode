"""
Render Configuration Helper

This module provides helper functions and utilities specifically for
deploying the Tableau Data Reporter application on Render.
"""

import os
import shutil
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def is_running_on_render():
    """Check if the application is running on Render."""
    return os.environ.get('RENDER', 'false').lower() == 'true'

def get_base_url():
    """Get the base URL for the application based on environment."""
    if is_running_on_render():
        return os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    return os.environ.get('BASE_URL', 'http://localhost:5000')

def ensure_directories():
    """Create necessary directories if they don't exist."""
    required_dirs = [
        'data',
        'static',
        'static/reports',
        'static/logos',
        'uploads/logos'
    ]
    
    for directory in required_dirs:
        dir_path = os.path.join(os.getcwd(), directory)
        if not os.path.exists(dir_path):
            logger.info(f"Creating directory: {dir_path}")
            os.makedirs(dir_path, exist_ok=True)
    
    # Ensure static/index.html exists
    static_index_path = os.path.join(os.getcwd(), 'static', 'index.html')
    if not os.path.exists(static_index_path):
        logger.info(f"Static index.html not found - creating default index.html")
        create_default_index_html()
    else:
        logger.info(f"Static index.html exists at {static_index_path}")

def create_default_index_html():
    """Create a default index.html file in the static directory."""
    static_dir = os.path.join(os.getcwd(), 'static')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir, exist_ok=True)
    
    index_path = os.path.join(static_dir, 'index.html')
    
    with open(index_path, 'w') as f:
        f.write("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tableau Data Reporter</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        .header {
            background-color: #f8f9fa;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            border-left: 5px solid #0066cc;
        }
        h1 {
            margin-top: 0;
            color: #0066cc;
        }
        .card {
            background-color: #fff;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        .login-section {
            background-color: #f0f7ff;
            padding: 20px;
            border-radius: 8px;
            margin-top: 30px;
        }
        .btn {
            display: inline-block;
            background-color: #0066cc;
            color: white;
            padding: 12px 24px;
            text-decoration: none;
            border-radius: 4px;
            font-weight: bold;
            margin-right: 10px;
            margin-top: 10px;
        }
        .btn:hover {
            background-color: #0056b3;
        }
        .feature {
            display: flex;
            margin-bottom: 15px;
        }
        .feature-icon {
            margin-right: 15px;
            color: #0066cc;
            font-size: 24px;
            min-width: 30px;
            text-align: center;
        }
        .status {
            background-color: #e3f2fd;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Tableau Data Reporter</h1>
        <p>A powerful application for scheduling and generating reports from Tableau data sources</p>
    </div>

    <div class="status">
        <h3>✅ API server is running successfully</h3>
        <p>You can access the application functionality through the login page.</p>
    </div>

    <div class="card">
        <h2>Features</h2>
        <div class="feature">
            <div class="feature-icon">📊</div>
            <div>Connect to Tableau Server and download data</div>
        </div>
        <div class="feature">
            <div class="feature-icon">⏰</div>
            <div>Schedule report generation (One-time, Daily, Weekly, Monthly)</div>
        </div>
        <div class="feature">
            <div class="feature-icon">📧</div>
            <div>Send reports via Email and WhatsApp</div>
        </div>
        <div class="feature">
            <div class="feature-icon">🎨</div>
            <div>Customize report formats and styles</div>
        </div>
        <div class="feature">
            <div class="feature-icon">👥</div>
            <div>User Management with different permission levels</div>
        </div>
        <div class="feature">
            <div class="feature-icon">📈</div>
            <div>Data visualization and analysis</div>
        </div>
    </div>

    <div class="login-section">
        <h2>Access the Application</h2>
        <p>Please log in to access the full functionality of the Tableau Data Reporter.</p>
        <a href="/login" class="btn">Login</a>
        <a href="/register" class="btn">Register</a>
    </div>
</body>
</html>""")
    logger.info(f"Created default index.html at {index_path}")

def setup_render_environment():
    """Set up environment variables for Render deployment."""
    if is_running_on_render():
        logger.info("Running on Render: Setting up environment...")
        os.environ['FLASK_ENV'] = 'production'
        os.environ['RENDER'] = 'true'
        
        # Ensure all directories exist
        ensure_directories()
        
    return is_running_on_render()

# Export constants
RENDER_CONFIG = {
    'is_render': is_running_on_render(),
    'base_url': get_base_url(),
    'data_path': 'data',
    'upload_path': 'static/logos'
} 