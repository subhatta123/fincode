"""
WSGI entry point for the Tableau Data Reporter application.
"""
import os
import sys
import logging
from app import app
from render_config import is_running_on_render, setup_render_environment

# Set up logging for clearer debug information
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Render environment if needed
if is_running_on_render():
    print("Running on Render: Setting up environment...")
    setup_render_environment()

# Print debug information
logger.info(f"Python version: {sys.version}")
logger.info(f"Current working directory: {os.getcwd()}")

# Check static folders
static_path = os.path.join(os.getcwd(), 'static')
frontend_path = os.path.join(os.getcwd(), 'frontend', 'build')

logger.info(f"Static directory exists: {os.path.exists(static_path)}")
logger.info(f"Frontend directory exists: {os.path.exists(frontend_path)}")

if os.path.exists(frontend_path):
    # Check if index.html exists in frontend/build
    index_exists = os.path.exists(os.path.join(frontend_path, 'index.html'))
    logger.info(f"Frontend index.html exists: {index_exists}")
else:
    # Check if index.html exists in static folder
    index_exists = os.path.exists(os.path.join(static_path, 'index.html'))
    logger.info(f"Static index.html exists: {index_exists}")

# Entry point for the application
if __name__ == "__main__":
    # Run the app on the specified port
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting application on port {port}")
    app.run(host="0.0.0.0", port=port) 