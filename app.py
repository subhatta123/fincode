"""
Simple Flask application that works around problems with static folder references.
This version explicitly avoids any references to static folders or complex imports.
"""
import os
import sys
from flask import Flask, Response

# Print startup message
print("=" * 50)
print("STARTING COMPLETELY STANDALONE FLASK APP")
print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print("=" * 50)

# Create a Flask app with no static folder and no template folder
app = Flask(__name__, static_folder=None, template_folder=None)

# Simple homepage route
@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Simple Flask App</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
            h1 { color: #4CAF50; }
        </style>
    </head>
    <body>
        <h1>Success! The Flask app is running.</h1>
        <p>This is a minimal Flask application with no dependencies on other files.</p>
        <p>If you're seeing this, the deployment was successful!</p>
    </body>
    </html>
    """

# Explicitly handle favicon requests
@app.route('/favicon.ico')
def favicon():
    return Response("", mimetype='image/x-icon')

# Catch-all route to prevent 404s
@app.route('/<path:path>')
def catch_all(path):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Path Info</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
            h1 {{ color: #FF5722; }}
            code {{ background: #f0f0f0; padding: 2px 5px; border-radius: 3px; }}
        </style>
    </head>
    <body>
        <h1>Path Information</h1>
        <p>You requested: <code>/{path}</code></p>
        <p><a href="/">Go back to the homepage</a></p>
    </body>
    </html>
    """

# Route to handle frontend/build/index.html
@app.route('/frontend/build/index.html')
def frontend_index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Frontend Placeholder</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
            h1 { color: #2196F3; }
        </style>
    </head>
    <body>
        <h1>Frontend Placeholder</h1>
        <p>This is a placeholder for the frontend build.</p>
        <p><a href="/">Go to the main application</a></p>
    </body>
    </html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
