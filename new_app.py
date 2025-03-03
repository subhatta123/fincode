from flask import Flask, jsonify
import os
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Print startup diagnostics
logger.info("Starting application...")
logger.info(f"Python version: {sys.version}")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Directory contents: {os.listdir('.')}")
logger.info(f"Environment variables: {os.environ}")

# Create app with explicit static folder
app = Flask(__name__, static_folder=None)

# Log Flask app config
logger.info(f"Flask app created with static_folder={app.static_folder}")

@app.route('/')
def index():
    logger.info("Index route accessed")
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Minimal Flask App on Render</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            h1 { color: #333; }
            p { margin-bottom: 15px; }
            .status { padding: 15px; background-color: #f0f8ff; border-radius: 5px; margin-bottom: 20px; }
            .nav { margin-top: 20px; }
            .nav a { display: inline-block; margin-right: 15px; padding: 8px 15px; background: #0d6efd; color: white; text-decoration: none; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>Minimal Flask App on Render</h1>
        <div class="status">
            <p>This is a complete standalone Flask application with no static folder.</p>
            <p>We're diagnosing why Render is looking for a static folder that our app doesn't use.</p>
        </div>
        <div class="nav">
            <a href="/debug">View Debug Info</a>
            <a href="/health">Health Check</a>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    logger.info("Health route accessed")
    return jsonify({
        "status": "healthy",
        "message": "The application is working correctly"
    })

@app.route('/debug')
def debug():
    logger.info("Debug route accessed")
    
    # Collect debug information
    debug_info = {
        "python_version": sys.version,
        "working_directory": os.getcwd(),
        "directory_contents": os.listdir('.'),
        "static_folder_config": app.static_folder,
        "all_env_vars": {k: v for k, v in os.environ.items()},
        "flask_config": {
            "debug": app.debug,
            "testing": app.testing,
            "secret_key": bool(app.secret_key),
            "url_map_rules": [str(rule) for rule in app.url_map.iter_rules()]
        }
    }
    
    return jsonify(debug_info)

# This is important - the app needs to be available at the module level for gunicorn
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True) 