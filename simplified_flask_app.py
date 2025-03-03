"""
Simplified Flask application with corrected indentation for Render
"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
import pytz
from functools import wraps
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, redirect, url_for, request, jsonify, send_from_directory, session, flash

# Import app-specific modules if available (graceful fallback if not)
try:
    from user_management import UserManagement
    user_manager = UserManagement()
    modules_loaded = True
except Exception as e:
    user_manager = None
    modules_loaded = False
    print(f"Error loading modules: {str(e)}")

def create_app():
    # Initialize Flask app
    app = Flask(__name__)
    
    # Set up static folder and URL path
    static_folder = os.environ.get('STATIC_FOLDER', os.path.join(os.getcwd(), 'frontend', 'build'))
    app.static_folder = static_folder
    app.static_url_path = '/static_files'
    
    # Set secret key
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
    
    # Create necessary directories
    for directory in ['data', 'static/reports', 'static/logos', 'uploads/logos']:
        os.makedirs(directory, exist_ok=True)
    
    # --- Decorators ---
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                flash('Please log in to access this page.')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    
    def role_required(roles):
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if 'user' not in session or session['user'].get('role') not in roles:
                    flash('Access denied')
                    return redirect(url_for('login'))
                return f(*args, **kwargs)
            return decorated_function
        return decorator
    
    # --- Routes ---
    @app.route('/')
    def index():
        # Redirect if user is logged in
        if 'user' in session:
            user_role = session['user'].get('role')
            if user_role == 'superadmin':
                return redirect(url_for('admin_dashboard'))
            elif user_role == 'power':
                return redirect(url_for('power_user_dashboard'))
            else:
                return redirect(url_for('normal_user_dashboard'))
        
        # Serve static index.html
        index_path = os.path.join(app.static_folder, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(app.static_folder, 'index.html')
        
        # Fallback to template
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Tableau Data Reporter</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                    .container { max-width: 800px; margin: 0 auto; }
                    h1 { color: #0066cc; }
                    .btn { display: inline-block; background-color: #0066cc; color: white; padding: 10px 15px; margin: 5px; text-decoration: none; border-radius: 4px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Tableau Data Reporter</h1>
                    <p>API server is running. Please log in to access the application.</p>
                    <div>
                        <a href="/login" class="btn">Login</a>
                        <a href="/register" class="btn" style="background-color: #666;">Register</a>
                    </div>
                </div>
            </body>
            </html>
        ''')
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            # Simple auth for testing
            if username == 'admin' and password == 'password':
                session['user'] = {
                    'id': 1,
                    'username': username,
                    'role': 'admin'
                }
                flash('Login successful!')
                return redirect(url_for('index'))
            
            flash('Invalid credentials')
        
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Login</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
                <style>
                    body { padding-top: 40px; }
                    .form-signin { width: 100%; max-width: 330px; padding: 15px; margin: auto; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="form-signin text-center">
                        <h1 class="h3 mb-3">Login</h1>
                        {% with messages = get_flashed_messages() %}
                            {% if messages %}
                                {% for message in messages %}
                                    <div class="alert alert-info">{{ message }}</div>
                                {% endfor %}
                            {% endif %}
                        {% endwith %}
                        <form method="post">
                            <div class="form-floating mb-3">
                                <input type="text" class="form-control" name="username" placeholder="Username" required>
                                <label>Username</label>
                            </div>
                            <div class="form-floating mb-3">
                                <input type="password" class="form-control" name="password" placeholder="Password" required>
                                <label>Password</label>
                            </div>
                            <button class="w-100 btn btn-lg btn-primary" type="submit">Login</button>
                            <p class="mt-3">
                                <a href="{{ url_for('register') }}">Register new account</a>
                            </p>
                        </form>
                    </div>
                </div>
            </body>
            </html>
        ''')
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            # Simple registration for testing
            flash('Registration successful! (Test mode)')
            return redirect(url_for('login'))
        
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Register</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
                <style>
                    body { padding-top: 40px; }
                    .form-register { width: 100%; max-width: 330px; padding: 15px; margin: auto; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="form-register text-center">
                        <h1 class="h3 mb-3">Register</h1>
                        {% with messages = get_flashed_messages() %}
                            {% if messages %}
                                {% for message in messages %}
                                    <div class="alert alert-info">{{ message }}</div>
                                {% endfor %}
                            {% endif %}
                        {% endwith %}
                        <form method="post">
                            <div class="form-floating mb-3">
                                <input type="text" class="form-control" name="username" placeholder="Username" required>
                                <label>Username</label>
                            </div>
                            <div class="form-floating mb-3">
                                <input type="password" class="form-control" name="password" placeholder="Password" required>
                                <label>Password</label>
                            </div>
                            <button class="w-100 btn btn-lg btn-primary" type="submit">Register</button>
                            <p class="mt-3">
                                <a href="{{ url_for('login') }}">Already have an account? Log in</a>
                            </p>
                        </form>
                    </div>
                </div>
            </body>
            </html>
        ''')
    
    @app.route('/logout')
    def logout():
        session.pop('user', None)
        flash('You have been logged out.')
        return redirect(url_for('login'))
    
    @app.route('/normal-user')
    @login_required
    @role_required(['normal'])
    def normal_user_dashboard():
        return "Normal User Dashboard"
    
    @app.route('/power-user')
    @login_required
    @role_required(['power'])
    def power_user_dashboard():
        return "Power User Dashboard"
    
    @app.route('/admin-dashboard')
    @login_required
    @role_required(['superadmin'])
    def admin_dashboard():
        return "Admin Dashboard"
    
    @app.route('/health')
    def health_check():
        return jsonify({'status': 'ok'})
    
    @app.route('/debug/routes')
    def debug_routes():
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append({
                'endpoint': rule.endpoint,
                'methods': ','.join(sorted(rule.methods)),
                'path': str(rule)
            })
        return jsonify({'total_routes': len(routes), 'routes': routes})
    
    return app

# Create application instance
app = create_app() 