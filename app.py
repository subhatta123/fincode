"""
Simple Flask application that works around problems with static folder references.
This version explicitly avoids any references to static folders or complex imports.
"""
import os
import sys
from flask import Flask, redirect

# Print debug info at startup
print("=" * 50)
print("SUPER MINIMAL APP.PY STARTING")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Files: {', '.join(os.listdir('.'))[:200]}...")  # Limit output length
print("=" * 50)

# Create Flask app with NO static folder
app = Flask(__name__, static_folder=None)

@app.route('/')
def index():
    """Simplest possible home page"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Basic Flask App</title>
    </head>
    <body>
        <h1>The Flask App Works!</h1>
        <p>This is the most basic Flask app possible.</p>
    </body>
    </html>
    """

@app.route('/favicon.ico')
def favicon():
    """Handle favicon requests to prevent 404s"""
    return '', 204  # No content response

# Catch-all route to prevent 404s
@app.route('/<path:path>')
def catch_all(path):
    """Handle any other path"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Page Info</title>
    </head>
    <body>
        <h1>Path Info</h1>
        <p>You requested: /{path}</p>
        <p><a href="/">Back to Home</a></p>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
