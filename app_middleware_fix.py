import os
import logging
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response
from app import app

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# List all routes in the app for debugging
logger.info("===== REGISTERED ROUTES BEFORE MIDDLEWARE =====")
for rule in app.url_map.iter_rules():
    logger.info(f"Route: {rule.rule} -> {rule.endpoint}")
logger.info("===== END ROUTES =====")

# Create a simple app that responds to all routes for testing
def simple_app(environ, start_response):
    path = environ.get('PATH_INFO', '').lstrip('/')
    logger.debug(f"Middleware received request for path: {path}")
    
    # Log all environ variables for debugging
    logger.debug("Request environment:")
    for key, value in sorted(environ.items()):
        logger.debug(f"  {key}: {value}")
    
    # Return a simple response for debugging
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [f"Middleware received request for: {path}".encode()]

# Create a middleware function to log requests
def logging_middleware(wsgi_app):
    def middleware(environ, start_response):
        path = environ.get('PATH_INFO', '')
        logger.debug(f"Request path: {path}")
        return wsgi_app(environ, start_response)
    return middleware

# Apply middleware to log requests
app.wsgi_app = logging_middleware(app.wsgi_app)

# Create a dispatcher middleware that can handle all routes
application = DispatcherMiddleware(app, {
    # Add specific path mappings here if needed
})

# Define a simple file that can be run to test the app
if __name__ == "__main__":
    # Run the app with debugging
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True) 