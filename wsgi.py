import os
import sys
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Log environment for debugging
logger.info(f"Environment variables: {dict(os.environ)}")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Python path: {sys.path}")

# Import the app directly from app.py (not app/__init__.py)
try:
    # First try importing Flask directly
    from flask import Flask
    
    # Create the app directly here for simplicity
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
    
    # Import necessary views from app.py
    sys.path.insert(0, os.getcwd())
    from app import (
        login, register, home, logout, normal_user_dashboard, 
        power_user_dashboard, admin_dashboard, api_status,
        login_required, role_required, process_schedule_form
    )
    
    # Register all the routes from app.py
    app.route('/')(home)
    app.route('/login', methods=['GET', 'POST'])(login)
    app.route('/register', methods=['GET', 'POST'])(register)
    app.route('/logout')(logout)
    app.route('/normal-user')(login_required(role_required(['normal'])(normal_user_dashboard)))
    app.route('/power-user')(login_required(role_required(['power'])(power_user_dashboard)))
    app.route('/admin-dashboard')(login_required(role_required(['superadmin'])(admin_dashboard)))
    app.route('/api/status')(api_status)
    app.route('/create_schedule', methods=['POST'])(process_schedule_form)
    
    logger.info("Created Flask app and registered routes directly in wsgi.py")
except Exception as e:
    # Fall back to importing from app.py
    logger.error(f"Failed to create Flask app directly: {str(e)}")
    logger.info("Falling back to importing app from app.py")
    from app import app

# Add debug info
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Static folder: {app.static_folder}")
logger.info(f"Static folder exists: {os.path.exists(app.static_folder)}")

# Print routes for debugging
logger.info("Available routes:")
for rule in app.url_map.iter_rules():
    logger.info(f"Route: {rule}, Endpoint: {rule.endpoint}")

# Define a simple root route as fallback
@app.route('/')
def root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Fincode API Server</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            h1 { color: #333; }
            .status { padding: 15px; background-color: #f0f8ff; border-radius: 5px; }
            .nav { margin-top: 20px; }
            .nav a { display: inline-block; margin-right: 15px; padding: 8px 15px; background: #0d6efd; color: white; text-decoration: none; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>Fincode API Server</h1>
        <div class="status">
            <p>API server is running successfully on Render.</p>
            <p>Use the links below to access different parts of the application.</p>
        </div>
        <div class="nav">
            <a href="/login">Login</a>
            <a href="/register">Register</a>
            <a href="/api/status">API Status</a>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    # Get port from environment variable or use default
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True) 