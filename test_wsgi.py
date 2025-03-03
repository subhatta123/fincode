import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Log environment
logger.info(f"Starting test_wsgi.py")
logger.info(f"Current working directory: {os.getcwd()}")

# Import the app
from render_app import app

# Log available routes
logger.info("Available routes:")
for rule in app.url_map.iter_rules():
    logger.info(f"Route: {rule}, Endpoint: {rule.endpoint}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True) 