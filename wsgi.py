"""
WSGI entry point for the Tableau Data Reporter application.
"""
import os
import sys
import logging
from app import app

# Set up logging for clearer debug information
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Print debug information
logger.info(f"Python version: {sys.version}")
logger.info(f"Current working directory: {os.getcwd()}")

# Check static folder
static_path = os.path.join(os.getcwd(), 'static')
logger.info(f"Static directory exists: {os.path.exists(static_path)}")

# Check if index.html exists in static folder
index_exists = os.path.exists(os.path.join(static_path, 'index.html'))
logger.info(f"Static index.html exists: {index_exists}")

# Check environment variables
render_vars = [key for key in os.environ.keys() if key.startswith('RENDER_') or key.startswith('FLASK_')]
logger.info(f"Number of Render/Flask environment variables: {len(render_vars)}")
logger.info(f"Running on Render: {os.environ.get('RENDER', 'false')}")

# Entry point for the application
if __name__ == "__main__":
    # Run the app on the specified port
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting application on port {port}")
    app.run(host="0.0.0.0", port=port) 