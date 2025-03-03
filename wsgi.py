"""
WSGI entry point for the Tableau Data Reporter application.
"""
import os
import sys
from app import app
from render_config import is_running_on_render, setup_render_environment

# Initialize Render environment if needed
if is_running_on_render():
    print("Running on Render: Setting up environment...")
    setup_render_environment()

# Print debug information
print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print(f"Static folder path: {app.static_folder}")
print(f"Static folder exists: {os.path.exists(app.static_folder) if app.static_folder else 'No static folder set'}")
print(f"Is running on Render: {is_running_on_render()}")
print(f"Environment variables set: {[key for key in os.environ.keys() if key.startswith('FLASK_') or key.startswith('RENDER_')]}")

# Check for frontend
frontend_path = os.path.join(os.getcwd(), 'frontend', 'build')
has_frontend = os.path.exists(frontend_path)
print(f"Frontend path: {frontend_path}")
print(f"Frontend exists: {has_frontend}")

# Entry point for Gunicorn
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port) 