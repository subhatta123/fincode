from flask import Flask, jsonify, render_template_string
import os
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

@app.route('/')
def home():
    logger.info("Home route accessed")
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Flask App on Render</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            h1 { color: #333; }
            .status { padding: 15px; background-color: #f0f8ff; border-radius: 5px; }
            .nav { margin-top: 20px; }
            .nav a { display: inline-block; margin-right: 15px; padding: 8px 15px; background: #0d6efd; color: white; text-decoration: none; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>Flask App on Render</h1>
        <div class="status">
            <p>The application is running correctly on Render!</p>
            <p>This is a simplified version for testing deployment issues.</p>
        </div>
        <div class="nav">
            <a href="/api/status">API Status</a>
        </div>
    </body>
    </html>
    """)

@app.route('/api/status')
def api_status():
    logger.info("API status route accessed")
    return jsonify({
        "status": "ok",
        "message": "API server is running correctly on Render",
        "environment": os.environ.get("FLASK_ENV", "development"),
        "render": os.environ.get("RENDER", "false")
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True) 