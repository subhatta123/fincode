from flask import Flask, send_from_directory
import os

# Create the Flask application instance
app = Flask(__name__, 
           static_folder='../frontend/build',  # Adjust path to match your frontend build location
           static_url_path='')

# Configure the application
# app.config.from_object('config.Config')

# Serve the frontend application
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

# Import and register blueprints
from app.routes.scheduler import scheduler_bp
from app.routes.main import main_bp

app.register_blueprint(scheduler_bp, url_prefix='/api')
app.register_blueprint(main_bp)  # No prefix for the main blueprint 