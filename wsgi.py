"""
WSGI entry point for the Tableau Data Reporter application.
"""
import os
import sys
import logging
from app import app
from render_config import ensure_directories, setup_render_environment

# Set up logging for clearer debug information
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Render environment if running on Render
if os.environ.get('RENDER', 'false').lower() == 'true':
    logger.info("Running on Render: Setting up environment...")
    setup_render_environment()

# Print debug information
logger.info(f"Python version: {sys.version}")
logger.info(f"Current working directory: {os.getcwd()}")

# Print all registered routes - THIS IS KEY FOR DEBUGGING
logger.info("===== REGISTERED ROUTES =====")
for rule in app.url_map.iter_rules():
    logger.info(f"Route: {rule.rule} -> {rule.endpoint}")
logger.info("===== END ROUTES =====")

# Check for directories
frontend_build_path = os.path.join(os.getcwd(), 'frontend', 'build')
static_path = os.path.join(os.getcwd(), 'static')

logger.info(f"Frontend directory exists: {os.path.exists(frontend_build_path)}")
logger.info(f"Static directory exists: {os.path.exists(static_path)}")

# Check for index.html files
frontend_index_path = os.path.join(frontend_build_path, 'index.html')
static_index_path = os.path.join(static_path, 'index.html')

logger.info(f"Frontend index.html exists: {os.path.exists(frontend_index_path)}")
logger.info(f"Static index.html exists: {os.path.exists(static_index_path)}")

# Check static folder configuration
logger.info(f"Static folder: {app.static_folder}")
logger.info(f"Static URL path: {app.static_url_path}")

# Check for custom test routes
has_test_route = False
has_login_test = False
for rule in app.url_map.iter_rules():
    if rule.endpoint == 'test_route':
        has_test_route = True
    if rule.endpoint == 'login_test':
        has_login_test = True

logger.info(f"Test route registered: {has_test_route}")
logger.info(f"Login test route registered: {has_login_test}")

# Check environment variables
render_vars = [key for key in os.environ.keys() if key.startswith('RENDER_') or key.startswith('FLASK_')]
logger.info(f"Number of Render/Flask environment variables: {len(render_vars)}")
logger.info(f"Running on Render: {os.environ.get('RENDER', 'false')}")

# Application entry point
application = app  # For compatibility with some WSGI servers

# Entry point for the application
if __name__ == "__main__":
    # Run the app on the specified port
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting application on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True) 