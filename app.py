# This file exists only because Render is hardcoded to use app.py
# It simply imports and exposes the Flask app from our minimal_app.py

# Import directly from minimal_app
from minimal_app import app

# Print a startup message to confirm this file is being used
print("=" * 50)
print("Using app.py wrapper to load minimal_app.py")
print("This confirms that Render is loading app.py")
print("=" * 50)

# No need to modify anything else, as we're just importing the app object
# from minimal_app.py which already has all routes defined

import os
import sys
from flask import Flask, request

# Print debug information for troubleshooting
print("=" * 50)
print("STANDALONE APP.PY RUNNING")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in directory: {', '.join(f for f in os.listdir('.') if os.path.isfile(f))}")
print("=" * 50)

# Create Flask app with explicitly disabled static folder
app = Flask(__name__, static_folder=None)

# Add verbose logging
@app.before_request
def log_request_info():
    app.logger.debug('Headers: %s', request.headers)
    app.logger.debug('Body: %s', request.get_data())

@app.route('/')
def index():
    """Basic home page route"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Render Test App</title>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; max-width: 800px; margin: 0 auto; }
            h1 { color: #2c3e50; }
            .success { color: green; font-weight: bold; }
            a { display: inline-block; margin: 10px 0; padding: 10px 15px; background: #3498db; color: white; text-decoration: none; border-radius: 4px; }
            a:hover { background: #2980b9; }
        </style>
    </head>
    <body>
        <h1>Render Flask Test</h1>
        <p class="success">SUCCESS! If you can see this page, the application is working correctly!</p>
        <p>This is a clean, minimal Flask application designed to work on Render.</p>
        <p><a href="/debug">View Debug Information</a></p>
    </body>
    </html>
    """

@app.route('/debug')
def debug():
    """Debug route to see environment information"""
    import os
    import sys
    
    # Get environment information
    env_info = {k: v for k, v in os.environ.items()}
    
    # Build HTML response with bootstrap styling
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Debug Information</title>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; }
            h1, h2 { color: #2c3e50; }
            pre { background: #f8f9fa; padding: 15px; border-radius: 4px; overflow-x: auto; }
        </style>
    </head>
    <body>
    """
    
    html += "<h1>Debug Information</h1>"
    html += "<h2>Environment Variables</h2>"
    html += "<pre>"
    for key in sorted(env_info.keys()):
        # Redact any sensitive values
        if any(sensitive in key.lower() for sensitive in ['key', 'token', 'password', 'secret']):
            html += f"{key}: [REDACTED]\n"
        else:
            html += f"{key}: {env_info[key]}\n"
    html += "</pre>"
    
    html += "<h2>Python Path</h2>"
    html += "<pre>"
    html += "\n".join(sys.path)
    html += "</pre>"
    
    html += "<h2>Directory Structure</h2>"
    html += "<pre>"
    for root, dirs, files in os.walk('.', topdown=True, followlinks=False):
        level = root.count(os.sep)
        indent = ' ' * 4 * level
        html += f"{indent}{os.path.basename(root)}/\n"
        subindent = ' ' * 4 * (level + 1)
        for file in files:
            html += f"{subindent}{file}\n"
    html += "</pre>"
    
    html += "<h2>Python Modules</h2>"
    html += "<pre>"
    html += "\n".join(sorted(sys.modules.keys()))
    html += "</pre>"
    
    html += """
    </body>
    </html>
    """
    
    return html

@app.route('/health')
def health():
    """Health check endpoint"""
    return {"status": "ok", "version": "1.0.0"}

# Catch-all route to handle any other endpoints
@app.route('/<path:path>')
def catch_all(path):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Page Not Found</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; max-width: 800px; margin: 0 auto; }}
            h1 {{ color: #e74c3c; }}
            a {{ color: #3498db; }}
        </style>
    </head>
    <body>
        <h1>Page Not Found</h1>
        <p>The path <code>/{path}</code> does not exist in this minimal application.</p>
        <p><a href="/">Return to Home</a></p>
    </body>
    </html>
    """

# This will only run when the script is executed directly, not when imported
if __name__ == '__main__':
    # Enable debug mode when running directly
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
