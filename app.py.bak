import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
from user_management import UserManagement
from report_manager_new import ReportManager
from data_analyzer import DataAnalyzer
from report_formatter_new import ReportFormatter
from tableau_utils import authenticate, get_workbooks, download_and_save_data, generate_table_name
import pytz
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from dotenv import load_dotenv
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from werkzeug.utils import secure_filename
from flask import Flask, render_template_string, redirect, url_for, request, jsonify, send_from_directory, session, flash

# Load environment variables
load_dotenv()

# Initialize Flask application
app = Flask(__name__, static_folder=None)  # Initialize Flask without static folder first

# Set up static files with a distinct URL prefix to avoid conflicts with routes
frontend_build_path = os.path.join(os.getcwd(), 'frontend', 'build')
static_path = os.path.join(os.getcwd(), 'static')

# Manually configure static folder AFTER app creation to avoid conflicts
if os.path.exists(frontend_build_path) and os.path.isdir(frontend_build_path):
    print(f"Using frontend/build as static folder: {frontend_build_path}")
    app.static_folder = frontend_build_path
    app.static_url_path = '/static_files'  # Critical: use a non-route path
else:
    print(f"Frontend/build not found. Using static folder as fallback: {static_path}")
    app.static_folder = static_path
    app.static_url_path = '/static_files'  # Critical: use a non-route path

print(f"Static folder is: {app.static_folder}")
print(f"Static URL path is: {app.static_url_path}")

# Load Render config
if os.environ.get('RENDER', 'false').lower() == 'true':
    from render_config import ensure_directories, is_running_on_render, setup_render_environment
    ensure_directories()
    setup_render_environment()

# Continue with the rest of the app setup
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# Get the base URL from environment or config
from render_config import get_base_url
base_url = get_base_url()

# Initialize managers
user_manager = UserManagement()
report_manager = ReportManager()
data_analyzer = DataAnalyzer()
report_formatter = ReportFormatter()

# Make sure necessary directories exist
for directory in ['data', 'static/reports', 'static/logos', 'uploads/logos']:
    os.makedirs(directory, exist_ok=True)

# Route to serve static index.html file (but still keeping it separate from API routes)
@app.route('/')
def serve_index():
    """Serve the index page."""
    # Check if user is logged in
    if 'user' in session:
        user_role = session['user'].get('role')
        if user_role == 'superadmin':
            return redirect(url_for('admin_dashboard'))
        elif user_role == 'power':
            return redirect(url_for('power_user_dashboard'))
        else:
            return redirect(url_for('normal_user_dashboard'))
    
    # Serve index.html from the static folder
    index_path = os.path.join(app.static_folder, 'index.html')
    if os.path.exists(index_path):
        print(f"Serving index.html from {index_path}")
        return send_from_directory(app.static_folder, 'index.html')
    
    # Fallback to a simple HTML page
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tableau Data Reporter</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            h1 { color: #0066cc; }
            .btn { display: inline-block; background-color: #0066cc; color: white; padding: 10px 15px; margin-top: 15px; text-decoration: none; border-radius: 4px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Tableau Data Reporter</h1>
            <p>API server is running. Please log in to access the application.</p>
            <a href="/login" class="btn">Login</a>
            <a href="/register" class="btn" style="background-color: #666;">Register</a>
        </div>
    </body>
    </html>
    """)

# Add a route for debugging what routes are registered
@app.route('/debug/routes')
def debug_routes():
    """Debug endpoint to list all registered routes."""
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

# Ensure the import for user_management is correct
try:
    # Verify user manager is initialized properly
    user_manager.get_all_users()
    print("User management loaded successfully")
except Exception as e:
    print(f"Error with user management: {str(e)}")

    return jsonify({'status': 'ok'})