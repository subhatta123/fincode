import os
from flask import Flask, request

# Create Flask app with explicit static_folder=None to disable static file handling
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
    </head>
    <body>
        <h1>Render Flask Test</h1>
        <p>This is an extremely minimal Flask application to test Render deployment.</p>
        <p>If you can see this page, the application is working correctly!</p>
        <p><a href="/debug">View Debug Info</a></p>
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
    
    # Build HTML response
    html = "<h1>Debug Information</h1>"
    html += "<h2>Environment Variables</h2>"
    html += "<pre>"
    for key in sorted(env_info.keys()):
        html += f"{key}: {env_info[key]}\n"
    html += "</pre>"
    
    html += "<h2>Python Path</h2>"
    html += "<pre>"
    html += "\n".join(sys.path)
    html += "</pre>"
    
    html += "<h2>Directory Contents</h2>"
    html += "<pre>"
    html += "\n".join(os.listdir('.'))
    html += "</pre>"
    
    return html

if __name__ == '__main__':
    # Enable debug mode when running directly
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000))) 