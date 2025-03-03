"""
WSGI entry point for the Tableau Data Reporter application.
"""
import os
import sys
import logging

# Set up logging for clearer debug information
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Print debug information
logger.info(f"Python version: {sys.version}")
logger.info(f"Current working directory: {os.getcwd()}")

# Import the simplified Flask app
from flask_app import app

# Print all registered routes for debugging
logger.info("===== REGISTERED ROUTES =====")
for rule in app.url_map.iter_rules():
    logger.info(f"Route: {rule.rule} -> {rule.endpoint}")
logger.info("===== END ROUTES =====")

# Print static file configuration
logger.info(f"Static folder: {app.static_folder}")
logger.info(f"Static URL path: {app.static_url_path}")

# Check if static folder and index.html exist
static_folder_exists = os.path.exists(app.static_folder) if app.static_folder else False
index_exists = os.path.exists(os.path.join(app.static_folder, 'index.html')) if app.static_folder else False
logger.info(f"Static folder exists: {static_folder_exists}")
logger.info(f"Index.html exists: {index_exists}")

# Log all environment variables for debugging
env_vars = {k: v for k, v in os.environ.items() if any(k.startswith(prefix) for prefix in ['FLASK_', 'PYTHON_', 'RENDER_'])}
logger.info(f"Environment variables: {env_vars}")

# For WSGI servers
application = app

# Entry point for the application
if __name__ == "__main__":
    # Run the app on the specified port
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting application on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True) 