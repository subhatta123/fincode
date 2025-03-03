"""
WSGI entry point for the Tableau Data Reporter application.
"""
import os
from app import app
from render_config import is_running_on_render, setup_render_environment

# Initialize Render environment if needed
if is_running_on_render():
    print("Running on Render: Setting up environment...")
    setup_render_environment()

# Print debug information
print(f"Current working directory: {os.getcwd()}")
print(f"Static folder: {app.static_folder}")
print(f"Static folder exists: {os.path.exists(app.static_folder)}")
print(f"Is running on Render: {is_running_on_render()}")

# Entry point for Gunicorn
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port) 