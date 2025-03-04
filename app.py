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

# Validation helper functions
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_image(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        file_path = os.path.join('uploads/logos', unique_filename)
        file.save(file_path)
        return file_path
    return None

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Role required decorator
def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session or session['user'].get('role') not in roles:
                flash('Access denied')
                return redirect(url_for('serve_index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Ensure superadmin exists
def ensure_superadmin_exists():
    try:
        superadmin = user_manager.get_user_by_username('superadmin')
        if not superadmin:
            # Create default superadmin
            user_manager.create_user(
                username='superadmin',
                password='admin123',
                role='superadmin',
                permission_type='all',
                organization_id=1,
                organization_name='Admin Organization'
            )
            print("Superadmin user created")
    except Exception as e:
        print(f"Error ensuring superadmin exists: {str(e)}")

# Call function to ensure superadmin exists
ensure_superadmin_exists()

# Helper functions for dataset preview
def get_dataset_preview_html(dataset_name):
    # Get dataset file path
    dataset_path = os.path.join('data', f"{dataset_name}.csv")
    
    # Read the dataset
    df = pd.read_csv(dataset_path)
    
    # Return HTML representation
    return df.head(10).to_html(classes='table table-striped table-bordered')

def get_dataset_row_count(dataset_name):
    # Get dataset file path
    dataset_path = os.path.join('data', f"{dataset_name}.csv")
    
    # Read the dataset
    df = pd.read_csv(dataset_path)
    
    # Return row count
    return len(df)

def get_saved_datasets():
    # Get list of CSV files in the data directory
    data_dir = os.path.join(os.getcwd(), 'data')
    datasets = []
    
    if os.path.exists(data_dir):
        for file in os.listdir(data_dir):
            if file.endswith('.csv'):
                dataset_name = file[:-4]  # Remove .csv extension
                datasets.append(dataset_name)
    
    return datasets

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
            .btn { display: inline-block; background-color: #0066cc; color: white; padding: 10px 15px; margin: 5px; text-decoration: none; border-radius: 4px; }
            .test-area { margin-top: 30px; padding: 15px; background-color: #f5f5f5; border-radius: 5px; }
            h2 { font-size: 18px; margin-top: 30px; }
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
            
            <div class="test-area">
                <h2>Test Routes</h2>
                <p>If you're experiencing 404 errors, try these test routes:</p>
                <a href="/test" class="btn">Basic Test</a>
                <a href="/login-test" class="btn">Login Test</a>
                <a href="/register-test" class="btn">Register Test</a>
                <a href="/simple-login" class="btn">Simple Login</a>
                <a href="/simple-register" class="btn">Simple Register</a>
                <a href="/debug/routes" class="btn">View All Routes</a>
            </div>
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

# Health check endpoint for Render
@app.route('/health')
def health_check():
    """Health check endpoint for Render."""
    return jsonify({'status': 'ok'})

# Add test routes for troubleshooting
@app.route('/test')
def test_route():
    """Simple test route to verify routing is working."""
    print("TEST ROUTE ACCESSED")
    return "Test route is working! Your Flask routing system is functioning."

@app.route('/login-test')
def login_test():
    """Simple test route for the login page."""
    print("LOGIN TEST ROUTE ACCESSED")
    return """
    <html>
    <head><title>Login Test</title></head>
    <body>
        <h1>Login Test Page</h1>
        <p>This is a test login page that bypasses the normal Flask login route.</p>
        <form method="post" action="/login">
            <div>
                <label>Username: <input type="text" name="username"></label>
            </div>
            <div>
                <label>Password: <input type="password" name="password"></label>
            </div>
            <button type="submit">Login</button>
        </form>
    </body>
    </html>
    """

@app.route('/register-test')
def register_test():
    """Simple test route for the register page."""
    print("REGISTER TEST ROUTE ACCESSED")
    return """
    <html>
    <head><title>Register Test</title></head>
    <body>
        <h1>Register Test Page</h1>
        <p>This is a test register page that bypasses the normal Flask register route.</p>
        <form method="post" action="/register">
            <div>
                <label>Username: <input type="text" name="username"></label>
            </div>
            <div>
                <label>Password: <input type="password" name="password"></label>
            </div>
            <button type="submit">Register</button>
        </form>
    </body>
    </html>
    """

# Try to import the simple auth blueprint
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location("simple_auth", "simple_auth.py")
    simple_auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(simple_auth)
    has_simple_auth = True
    print("Simple auth module found and loaded")
except Exception as e:
    has_simple_auth = False
    print(f"Simple auth module not available: {str(e)}")

# Register the simple auth blueprint if available
if has_simple_auth:
    app.register_blueprint(simple_auth.auth_bp)
    print("Registered simple auth blueprint with routes /simple-login and /simple-register")

# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Try superadmin verification first
        if username == 'superadmin':
            user = user_manager.verify_user(username, password)
            if user:
                session['user'] = {
                    'id': user[0],
                    'username': user[1],
                    'role': user[2],
                    'permission_type': user[3],
                    'organization_id': user[4],
                    'organization_name': user[5]
                }
                flash('Login successful!')
                return redirect(url_for('serve_index'))
        
        # Regular authentication for other users
        user = user_manager.verify_user(username, password)
        if user:
            session['user'] = {
                'id': user[0],
                'username': user[1],
                'role': user[2],
                'permission_type': user[3],
                'organization_id': user[4],
                'organization_name': user[5]
            }
            flash('Login successful!')
            return redirect(url_for('serve_index'))
        flash('Invalid credentials')
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Login - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding-top: 40px; }
                .form-signin {
                    width: 100%;
                    max-width: 330px;
                    padding: 15px;
                    margin: auto;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="form-signin text-center">
                    <h1 class="h3 mb-3">Tableau Data Reporter</h1>
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

# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'normal')
        organization_id = int(request.form.get('organization_id', 1))
        organization_name = request.form.get('organization_name', 'Default Organization')
        permission_type = request.form.get('permission_type', 'basic')
        
        if not username or not password:
            flash('Username and password are required.')
            return redirect(url_for('register'))
        
        # Password validation
        if len(password) < 6:
            flash('Password must be at least 6 characters long.')
            return redirect(url_for('register'))
        
        # Check if username already exists
        existing_user = user_manager.get_user_by_username(username)
        if existing_user:
            flash('Username already exists.')
            return redirect(url_for('register'))
        
        # Create new user
        user_id = user_manager.create_user(
            username=username,
            password=password,
            role=role,
            permission_type=permission_type,
            organization_id=organization_id,
            organization_name=organization_name
        )
        
        if user_id:
            flash('Registration successful! You can now log in.')
            return redirect(url_for('login'))
        else:
            flash('Error creating user. Please try again.')
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Register - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding-top: 40px; }
                .form-register {
                    width: 100%;
                    max-width: 330px;
                    padding: 15px;
                    margin: auto;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="form-register text-center">
                    <h1 class="h3 mb-3">Register New Account</h1>
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
                        <div class="form-floating mb-3">
                            <select class="form-select" name="role">
                                <option value="normal">Normal User</option>
                                <option value="power">Power User</option>
                            </select>
                            <label>Role</label>
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

# Logout route
@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

# User dashboard routes
@app.route('/normal-user')
@login_required
@role_required(['normal'])
def normal_user_dashboard():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Normal User Dashboard</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <h1>Normal User Dashboard</h1>
                <p>Welcome, {{ session['user']['username'] }}!</p>
                <div class="mt-4">
                    <a href="{{ url_for('logout') }}" class="btn btn-secondary">Logout</a>
                </div>
            </div>
        </body>
        </html>
    ''')

# Additional dashboard routes as needed
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

# Tableau related routes
@app.route('/tableau-connect', endpoint='tableau_connect')
@login_required
def tableau_connect():
    return "Tableau Connect Page - Placeholder"

@app.route('/manage-schedules', endpoint='manage_schedules')
@login_required
def manage_schedules():
    return "Manage Schedules Page - Placeholder"

@app.route('/qa-page', endpoint='qa_page')
@login_required
@role_required(['power', 'superadmin'])
def qa_page():
    return "QA Page - Placeholder"

@app.route('/admin_users', endpoint='admin_users')
@login_required
@role_required(['superadmin'])
def admin_users():
    return "Admin Users Page - Placeholder"

@app.route('/admin_organizations', endpoint='admin_organizations')
@login_required
@role_required(['superadmin'])
def admin_organizations():
    return "Admin Organizations Page - Placeholder"

@app.route('/admin_system', endpoint='admin_system')
@login_required
@role_required(['superadmin'])
def admin_system():
    return "Admin System Page - Placeholder"

# Run app if executed directly
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    app.run(host='0.0.0.0', port=port, debug=True)