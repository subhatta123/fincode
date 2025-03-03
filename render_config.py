"""
Render Configuration Helper

This module provides helper functions and utilities specifically for
deploying the Tableau Data Reporter application on Render.
"""

import os
from pathlib import Path

def is_running_on_render():
    """Check if the application is running on Render"""
    return os.environ.get('RENDER', 'false').lower() == 'true'

def get_base_url():
    """Get the base URL for the application based on environment"""
    if is_running_on_render():
        return os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
    else:
        return os.environ.get('BASE_URL', 'http://localhost:8501')

def ensure_directories():
    """Ensure all required directories exist"""
    # Main data directory
    os.makedirs('data', exist_ok=True)
    
    # Reports directories
    os.makedirs('data/reports', exist_ok=True)
    os.makedirs('static/reports', exist_ok=True)
    
    # Logo uploads directory
    os.makedirs('static/logos', exist_ok=True)
    
    # Any other required directories
    os.makedirs('uploads/logos', exist_ok=True)

def setup_render_environment():
    """Perform all necessary setup for Render deployment"""
    if is_running_on_render():
        print("Running on Render: Configuring environment...")
        ensure_directories()
        # Add any additional Render-specific setup here
        return True
    return False

# Export constants
RENDER_CONFIG = {
    'is_render': is_running_on_render(),
    'base_url': get_base_url(),
    'data_path': 'data',
    'upload_path': 'static/logos'
} 