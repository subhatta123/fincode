import os
import logging
import json
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response
from app import app
from flask import Flask, jsonify, request

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# List all routes in the app for debugging
logger.info("===== REGISTERED ROUTES BEFORE MIDDLEWARE =====")
for rule in app.url_map.iter_rules():
    logger.info(f"Route: {rule.rule} -> {rule.endpoint}")
logger.info("===== END ROUTES =====")

# Create a simple debug app to check if WSGI is working
debug_app = Flask(__name__)

@debug_app.route('/')
def debug_home():
    return "Debug app is working!"

@debug_app.route('/routes')
def debug_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods))
        routes.append({
            'endpoint': rule.endpoint,
            'methods': methods,
            'path': str(rule)
        })
    
    routes_by_path = sorted(routes, key=lambda x: x['path'])
    return jsonify({
        'total_routes': len(routes),
        'routes': routes_by_path
    })

@debug_app.route('/env')
def debug_env():
    env_vars = {k: v for k, v in os.environ.items() 
               if k.startswith(('FLASK_', 'RENDER_', 'PYTHON'))}
    return jsonify(env_vars)

@debug_app.route('/request')
def debug_request():
    request_info = {
        'path': request.path,
        'full_path': request.full_path,
        'url': request.url,
        'base_url': request.base_url,
        'url_root': request.url_root,
        'method': request.method,
        'headers': dict(request.headers),
        'cookies': request.cookies,
        'is_secure': request.is_secure,
        'host': request.host,
    }
    return jsonify(request_info)

# Create a middleware function to log requests
def logging_middleware(wsgi_app):
    def middleware(environ, start_response):
        path = environ.get('PATH_INFO', '')
        logger.debug(f"Request path: {path}")
        # Add more middleware diagnostics here
        try:
            return wsgi_app(environ, start_response)
        except Exception as e:
            logger.error(f"Error in middleware: {str(e)}")
            start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
            return [f"Server error: {str(e)}".encode()]
    return middleware

# Apply middleware to log requests
app.wsgi_app = logging_middleware(app.wsgi_app)

# Create a dispatcher middleware that can handle all routes
application = DispatcherMiddleware(app, {
    '/debug-info': debug_app
})

# Define a simple file that can be run to test the app
if __name__ == "__main__":
    # Run the app with debugging
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True) 