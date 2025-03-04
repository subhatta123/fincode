from flask import Flask, render_template_string, redirect, url_for, request, jsonify, send_from_directory, session, flash
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
import uuid
import hashlib
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from reportlab.graphics.shapes import Image
from reportlab.platypus import Spacer
from PIL import Image

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Initialize managers
user_manager = UserManagement()
report_manager = ReportManager()
report_manager.base_url = os.getenv('BASE_URL', 'http://localhost:8501')
data_analyzer = DataAnalyzer()
report_formatter = ReportFormatter()

# Add these configurations at the top of the file after app initialization
UPLOAD_FOLDER = 'static/logos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max upload

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_image(file):
    """
    Validates image file for size and dimensions
    Returns (is_valid, message) tuple
    """
    try:
        # Check file size (max 2MB)
        MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer
        
        if file_size > MAX_FILE_SIZE:
            return False, f"Image is too large. Maximum size is 2MB. Your file is {file_size/1024/1024:.2f}MB."
        
        # Check dimensions
        image = Image.open(file)
        width, height = image.size
        MAX_DIMENSION = 1500  # Maximum width or height
        
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            return False, f"Image dimensions are too large. Maximum is {MAX_DIMENSION}x{MAX_DIMENSION} pixels. Your image is {width}x{height}."
        
        # Reset file pointer after reading
        file.seek(0)
        return True, "Image is valid"
    except Exception as e:
        return False, f"Error validating image: {str(e)}"

# Ensure superadmin user exists with more robust implementation
def ensure_superadmin_exists():
    """Ensure the superadmin user exists in the database"""
    try:
        print("=== ENSURING SUPERADMIN USER EXISTS ===")
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            
            # First, check if the users table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if not cursor.fetchone():
                print("ERROR: users table does not exist in the database")
                return False
            
            # Get the table structure
            cursor.execute("PRAGMA table_info(users)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            print(f"User table columns: {column_names}")
            
            # Find the password column
            password_column = None
            for col in ['password_hash', 'password']:
                if col in column_names:
                    password_column = col
                    break
            
            if not password_column:
                print("ERROR: Could not find password column in users table")
                return False
            
            print(f"Using password column: {password_column}")
            
            # Check if superadmin exists
            # Check if superadmin user exists
            cursor.execute("SELECT rowid FROM users WHERE username = 'superadmin'")
            result = cursor.fetchone()
            
            # Create or update the superadmin user
            if result:
                # Update existing superadmin password
                password_hash = generate_password_hash('superadmin')
                cursor.execute(
                    f"UPDATE users SET {password_column} = ?, role = 'superadmin' WHERE username = 'superadmin'",
                    (password_hash,)
                )
                print("Updated superadmin user with password: superadmin")
            else:
                # Create new superadmin user
                password_hash = generate_password_hash('superadmin')
                cursor.execute(
                    f"INSERT INTO users (username, {password_column}, role, permission_type) VALUES (?, ?, 'superadmin', 'superadmin')",
                    ('superadmin', password_hash)
                )
                print("Created superadmin user with password: superadmin")
            
            conn.commit()
            return True
    except Exception as e:
        print(f"Error ensuring superadmin user: {e}")
        return False

# Call this function when the app starts
ensure_superadmin_exists()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in first')
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
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_dataset_preview_html(dataset_name):
    """Get HTML preview of dataset"""
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            df = pd.read_sql_query(f"SELECT * FROM '{dataset_name}' LIMIT 5", conn)
            return df.to_html(classes='table table-sm', index=False)
    except Exception as e:
        print(f"Error getting dataset preview: {str(e)}")
        return "<div class='alert alert-danger'>Error loading preview</div>"

def get_dataset_row_count(dataset_name):
    """Get row count for dataset"""
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM '{dataset_name}'")
            return cursor.fetchone()[0]
    except Exception as e:
        print(f"Error getting row count: {str(e)}")
        return 0

def get_saved_datasets():
    """Get list of saved datasets"""
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' 
                AND name NOT IN (
                    'users', 
                    'organizations', 
                    'schedules', 
                    'sqlite_sequence', 
                    'schedule_runs',
                    '_internal_tableau_connections'
                )
                AND name NOT LIKE 'sqlite_%'
            """)
            return [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error getting datasets: {str(e)}")
        return []

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Try superadmin verification first
        if username == 'superadmin':
            user = verify_superadmin(username, password)
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
                return redirect(url_for('home'))
        
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
            return redirect(url_for('home'))
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

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([username, email, password, confirm_password]):
            flash('All fields are required')
        elif password != confirm_password:
            flash('Passwords do not match')
        else:
            try:
                if user_manager.add_user_to_org(
                    username=username,
                    password=password,
                    org_id=None,
                    permission_type='normal',
                    email=email
                ):
                    flash('Registration successful! Please login.')
                    return redirect(url_for('login'))
            except ValueError as e:
                flash(str(e))
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Register - Tableau Data Reporter</title>
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
                            <input type="email" class="form-control" name="email" placeholder="Email" required>
                            <label>Email</label>
                        </div>
                        <div class="form-floating mb-3">
                            <input type="password" class="form-control" name="password" placeholder="Password" required>
                            <label>Password</label>
                        </div>
                        <div class="form-floating mb-3">
                            <input type="password" class="form-control" name="confirm_password" placeholder="Confirm Password" required>
                            <label>Confirm Password</label>
                        </div>
                        <button class="w-100 btn btn-lg btn-primary" type="submit">Register</button>
                        <p class="mt-3">
                            <a href="{{ url_for('login') }}">Back to login</a>
                        </p>
                    </form>
                </div>
            </div>
        </body>
        </html>
    ''')

@app.route('/')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    user_role = session['user'].get('role')
    if user_role == 'superadmin':
        return redirect(url_for('admin_dashboard'))
    elif user_role == 'power':
        return redirect(url_for('power_user_dashboard'))
    else:
        return redirect(url_for('normal_user_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully')
    return redirect(url_for('login'))

@app.route('/normal-user')
@login_required
@role_required(['normal'])
def normal_user_dashboard():
    datasets = get_saved_datasets()
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dashboard - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
            <style>
                .sidebar {
                    position: fixed;
                    top: 0;
                    bottom: 0;
                    left: 0;
                    z-index: 100;
                    padding: 48px 0 0;
                    box-shadow: inset -1px 0 0 rgba(0, 0, 0, .1);
                }
                .main {
                    margin-left: 240px;
                    padding: 20px;
                }
                .nav-link {
                    padding: 0.5rem 1rem;
                    font-size: 0.9rem;
                }
                .nav-link i {
                    margin-right: 8px;
                    width: 20px;
                    text-align: center;
                }
                .nav-link.active {
                    font-weight: bold;
                    background-color: rgba(0, 123, 255, 0.1);
                }
                .card-actions {
                    display: flex;
                    justify-content: space-between;
                    margin-top: 15px;
                }
                .delete-btn {
                    color: #dc3545;
                }
                .delete-btn:hover {
                    color: #bd2130;
                }
            </style>
        </head>
        <body>
            <nav class="col-md-3 col-lg-2 d-md-block bg-light sidebar">
                <div class="position-sticky pt-3">
                    <div class="px-3">
                        <h5>👤 User Profile</h5>
                        <p><strong>Username:</strong> {{ session.user.username }}</p>
                        <p><strong>Role:</strong> {{ session.user.role }}</p>
                    </div>
                    <hr>
                    <ul class="nav flex-column">
                        <li class="nav-item">
                            <a class="nav-link active" href="{{ url_for('normal_user_dashboard') }}">
                                <i class="bi bi-house"></i> Dashboard
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('tableau_connect') }}">
                                <i class="bi bi-box-arrow-in-right"></i> Connect to Tableau
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('schedule_reports') }}">
                                <i class="bi bi-calendar-plus"></i> Create Schedule
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('manage_schedules') }}">
                                <i class="bi bi-calendar-check"></i> Manage Schedules
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('logout') }}">
                                <i class="bi bi-box-arrow-right"></i> Logout
                            </a>
                        </li>
                    </ul>
                </div>
            </nav>

            <main class="main">
                <div class="container">
                    {% with messages = get_flashed_messages() %}
                        {% if messages %}
                            {% for message in messages %}
                                <div class="alert alert-info">{{ message }}</div>
                            {% endfor %}
                        {% endif %}
                    {% endwith %}

                    <h1 class="mb-4">Your Datasets</h1>
                    
                    {% if datasets %}
                        <div class="row">
                            {% for dataset in datasets %}
                                <div class="col-md-4 mb-4">
                                    <div class="card">
                                        <div class="card-body">
                                            <h5 class="card-title">{{ dataset }}</h5>
                                            <h6 class="card-subtitle mb-2 text-muted">
                                                <small>{{ get_dataset_row_count(dataset) }} rows</small>
                                            </h6>
                                            <div class="card-actions">
                                                <div>
                                            <a href="#" class="card-link" 
                                               onclick="viewDatasetPreview('{{ dataset }}')">View Preview</a>
                                            <a href="{{ url_for('schedule_dataset', dataset=dataset) }}" 
                                               class="card-link">Create Schedule</a>
                                                </div>
                                                <div>
                                                    <a href="#" class="delete-btn" onclick="confirmDelete('{{ dataset }}')">
                                                        <i class="bi bi-trash"></i>
                                                    </a>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            {% endfor %}
                        </div>
                    {% else %}
                        <div class="alert alert-info">
                            <p>No datasets available. Please connect to Tableau and download data first.</p>
                            <a href="{{ url_for('tableau_connect') }}" class="btn btn-primary">
                                <i class="bi bi-box-arrow-in-right"></i> Connect to Tableau
                            </a>
                        </div>
                    {% endif %}
                    
                    <!-- Dataset Preview Modal -->
                    <div class="modal fade" id="datasetPreviewModal" tabindex="-1">
                        <div class="modal-dialog modal-xl">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h5 class="modal-title">Dataset Preview: <span id="datasetName"></span></h5>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <div class="modal-body">
                                    <div id="datasetPreview"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Delete Confirmation Modal -->
                    <div class="modal fade" id="deleteConfirmModal" tabindex="-1">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h5 class="modal-title">Confirm Delete</h5>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <div class="modal-body">
                                    <p>Are you sure you want to delete the dataset: <strong id="deleteDatasetName"></strong>?</p>
                                    <p class="text-danger">This action cannot be undone.</p>
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                                    <button type="button" class="btn btn-danger" id="confirmDeleteBtn">Delete Dataset</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                function viewDatasetPreview(dataset) {
                    document.getElementById('datasetName').textContent = dataset;
                    const previewDiv = document.getElementById('datasetPreview');
                    previewDiv.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div><p>Loading preview...</p></div>';
                    
                    // Show modal
                    const modal = new bootstrap.Modal(document.getElementById('datasetPreviewModal'));
                    modal.show();
                    
                    // Fetch preview
                    fetch(`/api/datasets/${dataset}/preview`)
                        .then(response => response.text())
                        .then(html => {
                            previewDiv.innerHTML = html;
                        })
                        .catch(error => {
                            previewDiv.innerHTML = `<div class="alert alert-danger">Failed to load preview: ${error}</div>`;
                        });
                }
                
                function confirmDelete(dataset) {
                    // Set the dataset name in the modal
                    document.getElementById('deleteDatasetName').textContent = dataset;
                    
                    // Show confirmation modal
                    const modal = new bootstrap.Modal(document.getElementById('deleteConfirmModal'));
                    modal.show();
                    
                    // Setup confirm button action
                    const confirmBtn = document.getElementById('confirmDeleteBtn');
                    
                    // Remove any existing event listeners
                    const newConfirmBtn = confirmBtn.cloneNode(true);
                    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
                    
                    // Add new event listener
                    newConfirmBtn.addEventListener('click', function() {
                        deleteDataset(dataset, modal);
                    });
                }
                
                function deleteDataset(dataset, modal) {
                    // Show loading state
                    const confirmBtn = document.getElementById('confirmDeleteBtn');
                    confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Deleting...';
                    confirmBtn.disabled = true;
                    
                    // Delete the dataset
                    fetch(`/api/datasets/${dataset}`, {
                        method: 'DELETE'
                    })
                    .then(response => response.json())
                    .then(data => {
                        // Hide modal
                        modal.hide();
                        
                        if (data.success) {
                            // Show success message
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-success alert-dismissible fade show';
                            alertDiv.innerHTML = `
                                Dataset <strong>${dataset}</strong> has been deleted successfully.
                                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                            `;
                            document.querySelector('.container').prepend(alertDiv);
                            
                            // Remove dataset card from page
                            setTimeout(() => {
                                window.location.reload();
                            }, 1000);
                        } else {
                            // Show error message
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-danger alert-dismissible fade show';
                            alertDiv.innerHTML = `
                                Failed to delete dataset: ${data.error || 'Unknown error'}
                                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                            `;
                            document.querySelector('.container').prepend(alertDiv);
                        }
                    })
                    .catch(error => {
                        // Hide modal
                        modal.hide();
                        
                        // Show error message
                        const alertDiv = document.createElement('div');
                        alertDiv.className = 'alert alert-danger alert-dismissible fade show';
                        alertDiv.innerHTML = `
                            Failed to delete dataset: ${error.message}
                            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                        `;
                        document.querySelector('.container').prepend(alertDiv);
                        });
                }
            </script>
        </body>
        </html>
    ''', datasets=datasets)

@app.route('/power-user')
@login_required
@role_required(['power'])
def power_user_dashboard():
    datasets = get_saved_datasets()
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Power User Dashboard - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
            <style>
                .sidebar {
                    position: fixed;
                    top: 0;
                    bottom: 0;
                    left: 0;
                    z-index: 100;
                    padding: 48px 0 0;
                    box-shadow: inset -1px 0 0 rgba(0, 0, 0, .1);
                }
                .main {
                    margin-left: 240px;
                    padding: 20px;
                }
                .nav-link {
                    padding: 0.5rem 1rem;
                    font-size: 0.9rem;
                }
                .nav-link i {
                    margin-right: 8px;
                    width: 20px;
                    text-align: center;
                }
                .nav-link.active {
                    font-weight: bold;
                    background-color: rgba(0, 123, 255, 0.1);
                }
                .card-actions {
                    display: flex;
                    justify-content: space-between;
                    margin-top: 15px;
                }
                .delete-btn {
                    color: #dc3545;
                }
                .delete-btn:hover {
                    color: #bd2130;
                }
            </style>
        </head>
        <body>
            <nav class="col-md-3 col-lg-2 d-md-block bg-light sidebar">
                <div class="position-sticky pt-3">
                    <div class="px-3">
                        <h5>👤 User Profile</h5>
                        <p><strong>Username:</strong> {{ session.user.username }}</p>
                        <p><strong>Role:</strong> {{ session.user.role }}</p>
                    </div>
                    <hr>
                    <ul class="nav flex-column">
                        <li class="nav-item">
                            <a class="nav-link active" href="{{ url_for('power_user_dashboard') }}">
                                <i class="bi bi-house"></i> Dashboard
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('tableau_connect') }}">
                                <i class="bi bi-box-arrow-in-right"></i> Connect to Tableau
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('qa_page') }}">
                                <i class="bi bi-question-circle"></i> Ask Questions
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('schedule_reports') }}">
                                <i class="bi bi-calendar-plus"></i> Create Schedule
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('manage_schedules') }}">
                                <i class="bi bi-calendar-check"></i> Manage Schedules
                            </a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('logout') }}">
                                <i class="bi bi-box-arrow-right"></i> Logout
                            </a>
                        </li>
                    </ul>
                </div>
            </nav>

            <main class="main">
                <div class="container">
                    {% with messages = get_flashed_messages() %}
                        {% if messages %}
                            {% for message in messages %}
                                <div class="alert alert-info">{{ message }}</div>
                            {% endfor %}
                        {% endif %}
                    {% endwith %}

                    <h1 class="mb-4">Your Datasets</h1>
                    
                    {% if datasets %}
                        <div class="row">
                            {% for dataset in datasets %}
                                <div class="col-md-4 mb-4">
                                    <div class="card">
                                        <div class="card-body">
                                            <h5 class="card-title">{{ dataset }}</h5>
                                            <h6 class="card-subtitle mb-2 text-muted">
                                                <small>{{ get_dataset_row_count(dataset) }} rows</small>
                                            </h6>
                                            <div class="card-actions">
                                            <div class="btn-group">
                                                <a href="#" class="btn btn-sm btn-outline-primary" 
                                                onclick="viewDatasetPreview('{{ dataset }}')">
                                                    <i class="bi bi-table"></i> View Preview
                                                </a>
                                                <a href="{{ url_for('qa_page') }}?dataset={{ dataset }}" 
                                                class="btn btn-sm btn-outline-success">
                                                    <i class="bi bi-question-circle"></i> Ask Questions
                                                </a>
                                                <a href="{{ url_for('schedule_dataset', dataset=dataset) }}" 
                                                class="btn btn-sm btn-outline-info">
                                                    <i class="bi bi-calendar-plus"></i> Schedule
                                                </a>
                                                </div>
                                                <div>
                                                    <a href="#" class="delete-btn" onclick="confirmDelete('{{ dataset }}')">
                                                        <i class="bi bi-trash"></i>
                                                    </a>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            {% endfor %}
                        </div>
                    {% else %}
                        <div class="alert alert-info">
                            <p>No datasets available. Please connect to Tableau and download data first.</p>
                            <a href="{{ url_for('tableau_connect') }}" class="btn btn-primary">
                                <i class="bi bi-box-arrow-in-right"></i> Connect to Tableau
                            </a>
                        </div>
                    {% endif %}
                    
                    <!-- Dataset Preview Modal -->
                    <div class="modal fade" id="datasetPreviewModal" tabindex="-1">
                        <div class="modal-dialog modal-xl">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h5 class="modal-title">Dataset Preview: <span id="datasetName"></span></h5>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <div class="modal-body">
                                    <div id="datasetPreview"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Delete Confirmation Modal -->
                    <div class="modal fade" id="deleteConfirmModal" tabindex="-1">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h5 class="modal-title">Confirm Delete</h5>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <div class="modal-body">
                                    <p>Are you sure you want to delete the dataset: <strong id="deleteDatasetName"></strong>?</p>
                                    <p class="text-danger">This action cannot be undone.</p>
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                                    <button type="button" class="btn btn-danger" id="confirmDeleteBtn">Delete Dataset</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </main>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                function viewDatasetPreview(dataset) {
                    document.getElementById('datasetName').textContent = dataset;
                    const previewDiv = document.getElementById('datasetPreview');
                    previewDiv.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"></div><p>Loading preview...</p></div>';
                    
                    // Show modal
                    const modal = new bootstrap.Modal(document.getElementById('datasetPreviewModal'));
                    modal.show();
                    
                    // Fetch preview
                    fetch(`/api/datasets/${dataset}/preview`)
                        .then(response => response.text())
                        .then(html => {
                            previewDiv.innerHTML = html;
                        })
                        .catch(error => {
                            previewDiv.innerHTML = `<div class="alert alert-danger">Failed to load preview: ${error}</div>`;
                        });
                }
                
                function confirmDelete(dataset) {
                    // Set the dataset name in the modal
                    document.getElementById('deleteDatasetName').textContent = dataset;
                    
                    // Show confirmation modal
                    const modal = new bootstrap.Modal(document.getElementById('deleteConfirmModal'));
                    modal.show();
                    
                    // Setup confirm button action
                    const confirmBtn = document.getElementById('confirmDeleteBtn');
                    
                    // Remove any existing event listeners
                    const newConfirmBtn = confirmBtn.cloneNode(true);
                    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
                    
                    // Add new event listener
                    newConfirmBtn.addEventListener('click', function() {
                        deleteDataset(dataset, modal);
                    });
                }
                
                function deleteDataset(dataset, modal) {
                    // Show loading state
                    const confirmBtn = document.getElementById('confirmDeleteBtn');
                    confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Deleting...';
                    confirmBtn.disabled = true;
                    
                    // Delete the dataset
                    fetch(`/api/datasets/${dataset}`, {
                        method: 'DELETE'
                    })
                    .then(response => response.json())
                    .then(data => {
                        // Hide modal
                        modal.hide();
                        
                        if (data.success) {
                            // Show success message
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-success alert-dismissible fade show';
                            alertDiv.innerHTML = `
                                Dataset <strong>${dataset}</strong> has been deleted successfully.
                                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                            `;
                            document.querySelector('.container').prepend(alertDiv);
                            
                            // Remove dataset card from page
                            setTimeout(() => {
                                window.location.reload();
                            }, 1000);
                        } else {
                            // Show error message
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-danger alert-dismissible fade show';
                            alertDiv.innerHTML = `
                                Failed to delete dataset: ${data.error || 'Unknown error'}
                                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                            `;
                            document.querySelector('.container').prepend(alertDiv);
                        }
                    })
                    .catch(error => {
                        // Hide modal
                        modal.hide();
                        
                        // Show error message
                        const alertDiv = document.createElement('div');
                        alertDiv.className = 'alert alert-danger alert-dismissible fade show';
                        alertDiv.innerHTML = `
                            Failed to delete dataset: ${error.message}
                            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                        `;
                        document.querySelector('.container').prepend(alertDiv);
                        });
                }
            </script>
        </body>
        </html>
    ''', datasets=datasets, get_dataset_row_count=get_dataset_row_count)

@app.route('/qa-page')
@login_required
@role_required(['power', 'superadmin'])
def qa_page():
    dataset = request.args.get('dataset')
    datasets = get_saved_datasets()
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Ask Questions - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
                .chat-container {
                    height: 400px;
                    overflow-y: auto;
                    border: 1px solid #dee2e6;
                    border-radius: 0.25rem;
                    padding: 1rem;
                    margin-bottom: 1rem;
                }
                .chat-message {
                    margin-bottom: 1rem;
                    padding: 0.5rem;
                    border-radius: 0.25rem;
                }
                .user-message {
                    background-color: #e9ecef;
                    margin-left: 20%;
                }
                .assistant-message {
                    background-color: #f8f9fa;
                    margin-right: 20%;
                }
                #visualization {
                    width: 100%;
                    height: 400px;
                    margin-top: 1rem;
                    border: 1px solid #dee2e6;
                    border-radius: 0.25rem;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .vis-placeholder {
                    color: #6c757d;
                    text-align: center;
                    font-style: italic;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="row justify-content-center">
                    <div class="col-md-10">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h1>❓ Ask Questions About Your Data</h1>
                            <a href="{{ url_for('home') }}" class="btn btn-outline-primary">← Back</a>
                        </div>
                        
                        <div class="card mb-4">
                            <div class="card-body">
                                <form id="questionForm">
                                    <div class="mb-3">
                                        <label class="form-label">Select Dataset</label>
                                        <select class="form-select" name="dataset" required>
                                            <option value="">Choose a dataset...</option>
                                            {% for ds in datasets %}
                                                <option value="{{ ds }}"
                                                        {% if ds == dataset %}selected{% endif %}>
                                                    {{ ds }}
                                                </option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Your Question</label>
                                        <div class="input-group">
                                            <input type="text" class="form-control" name="question"
                                                   placeholder="Ask a question about your data..."
                                                   required>
                                            <button type="submit" class="btn btn-primary">
                                                Ask Question
                                            </button>
                                        </div>
                                    </div>
                                </form>
                            </div>
                        </div>
                        
                        <div class="row">
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-body">
                                        <h5 class="card-title">Conversation</h5>
                                        <div id="chatContainer" class="chat-container"></div>
                                    </div>
                                </div>
                            </div>
                            <div class="col-md-6">
                                <div class="card">
                                    <div class="card-body">
                                        <h5 class="card-title">Visualization</h5>
                                        <div id="visualization">
                                            <div class="vis-placeholder">Ask a question to see visualization</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.plot.ly/plotly-2.20.0.min.js"></script>
            <script>
                const questionForm = document.getElementById('questionForm');
                const chatContainer = document.getElementById('chatContainer');
                const visualizationDiv = document.getElementById('visualization');
                
                // Initialize visualization area
                visualizationDiv.innerHTML = '<div class="vis-placeholder">Ask a question to see visualization</div>';
                
                questionForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    
                    const formData = new FormData(questionForm);
                    const dataset = formData.get('dataset');
                    const question = formData.get('question');
                    
                    // Clear previous visualization
                    visualizationDiv.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Loading...</span></div>';
                    
                    // Add user message to chat
                    addMessage(question, 'user');
                    
                    try {
                        // Show loading message in assistant chat
                        const loadingMsgId = 'loading-' + Date.now();
                        addMessage('Analyzing data...', 'assistant', loadingMsgId);
                        
                        const response = await fetch('/api/ask-question', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                dataset: dataset,
                                question: question
                            })
                        });
                        
                        const data = await response.json();
                        
                        // Remove loading message
                        const loadingMsg = document.getElementById(loadingMsgId);
                        if (loadingMsg) loadingMsg.remove();
                        
                        if (data.success) {
                            // Add assistant's response to chat
                            addMessage(data.answer, 'assistant');
                            
                            // Update visualization if provided
                            if (data.visualization) {
                                console.log('Received visualization data:', data.visualization);
                                try {
                                    // Clear the visualization div
                                    visualizationDiv.innerHTML = '';
                                    
                                    // Create new Plotly chart
                                    Plotly.newPlot(visualizationDiv, data.visualization.data, data.visualization.layout);
                                } catch (visError) {
                                    console.error('Error displaying visualization:', visError);
                                    visualizationDiv.innerHTML = '<div class="alert alert-warning">Failed to display visualization: ' + visError.message + '</div>';
                                }
                            } else {
                                visualizationDiv.innerHTML = '<div class="vis-placeholder">No visualization available for this query</div>';
                            }
                        } else {
                            addMessage('Error: ' + data.error, 'assistant');
                            visualizationDiv.innerHTML = '<div class="alert alert-danger">Error: ' + data.error + '</div>';
                        }
                    } catch (error) {
                        console.error('API request error:', error);
                        addMessage('Error: Failed to get response. Check console for details.', 'assistant');
                        visualizationDiv.innerHTML = '<div class="alert alert-danger">Request failed: ' + error.message + '</div>';
                    }
                    
                    // Clear question input
                    questionForm.querySelector('input[name="question"]').value = '';
                });
                
                function addMessage(message, type, id = null) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `chat-message ${type}-message`;
                    if (id) messageDiv.id = id;
                    messageDiv.textContent = message;
                    chatContainer.appendChild(messageDiv);
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
                
                // If dataset is provided in URL, simulate click on Ask Questions button
                const urlParams = new URLSearchParams(window.location.search);
                const datasetParam = urlParams.get('dataset');
                if (datasetParam) {
                    const datasetSelect = questionForm.querySelector('select[name="dataset"]');
                    if (datasetSelect) {
                        datasetSelect.value = datasetParam;
                    }
                }
            </script>
        </body>
        </html>
    ''', datasets=datasets, dataset=dataset)

# Add this helper function for converting any visualization to Plotly format
def ensure_plotly_visualization(df, visualization, question=None):
    """Ensure the visualization is a Plotly figure, converting if necessary"""
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    # If it's already a Plotly figure, return it
    if hasattr(visualization, 'data') and hasattr(visualization, 'layout') and hasattr(visualization, 'to_dict'):
        return visualization
        
    # Check if this is a Streamlit object by the type name
    vis_type = str(type(visualization).__name__)
    if "streamlit" in vis_type.lower() or (hasattr(visualization, 'st') and visualization.st):
        print(f"Converting Streamlit visualization ({vis_type}) to Plotly")
        # Create a new Plotly visualization based on the dataframe
        
        # Default fallback: if we don't know what else to do, create a simple table
        try:
            # Try to infer what kind of visualization to create based on the question
            if question:
                question = question.lower()
                
                # First, let's check for sum queries which should have highest priority
                if 'sum of' in question or 'total of' in question:
                    # Extract the field name they want to sum
                    field_parts = question.split('sum of ')
                    if len(field_parts) > 1:
                        field_name = field_parts[1].strip().split()[0]  # Get first word after "sum of"
                    else:
                        field_parts = question.split('total of ')
                        if len(field_parts) > 1:
                            field_name = field_parts[1].strip().split()[0]
                        else:
                            field_name = None
                    
                    # Find the closest matching column name
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    if len(numeric_cols) > 0:
                        if field_name:
                            # Find the best matching column
                            best_match = None
                            for col in numeric_cols:
                                if field_name in col.lower():
                                    best_match = col
                                    break
                            
                            if not best_match:
                                best_match = numeric_cols[0]
                        else:
                            best_match = numeric_cols[0]
                        
                        # Create a simple bar chart for the sum value
                        sum_value = df[best_match].sum()
                        
                        # Create a dataframe with just the summary data
                        import pandas as pd
                        summary_df = pd.DataFrame({
                            'Metric': [f'Sum of {best_match}'],
                            'Value': [sum_value]
                        })
                        
                        fig = px.bar(summary_df, x='Metric', y='Value', 
                                    title=f"Sum of {best_match}: {sum_value:,.2f}",
                                    text_auto='.2s')
                        fig.update_traces(textfont_size=12, textangle=0, textposition="outside", cliponaxis=False)
                        return fig
                
                # Check for other query types
                elif any(word in question for word in ['distribution', 'histogram', 'frequency']):
                    # Create a histogram of the first numeric column
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    if len(numeric_cols) > 0:
                        # Try to identify which column to use based on the question
                        col_name = next((col for col in numeric_cols if col.lower() in question), numeric_cols[0])
                        return px.histogram(df, x=col_name, title=f"Distribution of {col_name}")
                        
                elif any(word in question for word in ['correlation', 'scatter', 'relationship']):
                    # Create a scatter plot of the first two numeric columns
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    if len(numeric_cols) >= 2:
                        # Try to identify columns from the question
                        x_col = numeric_cols[0]
                        y_col = numeric_cols[1]
                        
                        # Look for column names in the question
                        for col in numeric_cols:
                            if col.lower() in question:
                                if x_col == numeric_cols[0]:  # If first column not assigned yet
                                    x_col = col
                                else:
                                    y_col = col
                                    break
                        
                        return px.scatter(df, x=x_col, y=y_col,
                                         title=f"{x_col} vs. {y_col}")
                                         
                elif any(word in question for word in ['time', 'trend', 'over time']):
                    # Look for date columns
                    date_cols = df.select_dtypes(include=['datetime']).columns
                    if len(date_cols) > 0 and len(df.select_dtypes(include=['number']).columns) > 0:
                        date_col = date_cols[0]
                        # Try to find which numeric column to use
                        numeric_cols = df.select_dtypes(include=['number']).columns
                        numeric_col = next((col for col in numeric_cols if col.lower() in question), numeric_cols[0])
                        return px.line(df, x=date_col, y=numeric_col, title=f"{numeric_col} over time")
                        
                elif any(word in question for word in ['comparison', 'compare', 'bar']):
                    # Create a bar chart
                    if len(df.columns) >= 2:
                        # Try to find categorical and numeric columns
                        numeric_cols = df.select_dtypes(include=['number']).columns
                        categorical_cols = df.select_dtypes(include=['object']).columns
                        
                        if len(categorical_cols) > 0 and len(numeric_cols) > 0:
                            # Try to identify which columns to use based on the question
                            cat_col = next((col for col in categorical_cols if col.lower() in question), categorical_cols[0])
                            num_col = next((col for col in numeric_cols if col.lower() in question), numeric_cols[0])
                            
                            return px.bar(df, x=cat_col, y=num_col,
                                         title=f"{num_col} by {cat_col}")
                        elif len(numeric_cols) >= 1:
                            # Just use the first 10 rows and first numeric column
                            num_col = next((col for col in numeric_cols if col.lower() in question), numeric_cols[0])
                            return px.bar(df.head(10), y=num_col, title=f"Top 10 {num_col} values")
            
            # Default fallback - show a table view
            fig = make_subplots(rows=1, cols=1)
            
            # Create a table with the first few rows
            df_subset = df.head(10)
            fig.add_trace(
                go.Table(
                    header=dict(values=list(df_subset.columns),
                               fill_color='paleturquoise',
                               align='left'),
                    cells=dict(values=[df_subset[col] for col in df_subset.columns],
                              fill_color='lavender',
                              align='left')
                )
            )
            fig.update_layout(title_text="Data Preview")
            return fig
            
        except Exception as e:
            print(f"Error creating Plotly visualization: {str(e)}")
            # Return a simple Plotly figure with error message
            fig = go.Figure()
            fig.add_annotation(text=f"Could not create visualization: {str(e)}",
                              xref="paper", yref="paper",
                              x=0.5, y=0.5, showarrow=False)
            return fig
    
    # Handle pandas visualization
    if hasattr(visualization, 'plot'):
        print("Converting pandas visualization to Plotly")
        try:
            # Try to create a Plotly Express figure
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                return px.line(df, y=numeric_cols[0], title=f"{numeric_cols[0]} values")
            else:
                # Create a table view
                return px.bar(df.head(10), title="Data Preview")
        except Exception as e:
            print(f"Error converting pandas visualization: {str(e)}")
            # Return an empty Plotly figure
            return go.Figure()
            
    # For any other type, return a simple visualization
    print(f"Unknown visualization type {type(visualization).__name__}, creating default Plotly figure")
    try:
        # Create a basic bar chart of the first numeric column
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            return px.bar(df, y=numeric_cols[0], title=f"{numeric_cols[0]} values")
        else:
            # Just visualize the first column
            return px.bar(df.value_counts(df.columns[0]).reset_index(), 
                         x='index', y=df.columns[0], 
                         title=f"Counts of {df.columns[0]}")
    except Exception as e:
        print(f"Error creating default visualization: {str(e)}")
        # Return an empty Plotly figure
        return go.Figure()

@app.route('/api/ask-question', methods=['POST'])
@login_required
@role_required(['power', 'superadmin'])
def ask_question_api():
    try:
        data = request.json
        dataset = data.get('dataset')
        question = data.get('question')
        
        if not dataset or not question:
            return jsonify({
                'success': False,
                'error': 'Dataset and question are required'
            })
        
        # Load dataset
        with sqlite3.connect('data/tableau_data.db') as conn:
            df = pd.read_sql_query(f"SELECT * FROM '{dataset}'", conn)
        
        # Get answer and visualization
        try:
            answer, visualization = data_analyzer.ask_question(df, question)
            print(f"Visualization type: {type(visualization)}")
            
            # Ensure we have a Plotly visualization
            visualization = ensure_plotly_visualization(df, visualization, question)
            
        except Exception as viz_error:
            print(f"Error generating visualization: {str(viz_error)}")
            # If visualization fails, still return the answer if possible
            try:
                # Try to get just the answer
                answer = data_analyzer.analyze_data(df, question)
                # Create a simple Plotly visualization
                import plotly.express as px
                
                # Create a simple visualization based on the dataframe
                numeric_cols = df.select_dtypes(include=['number']).columns
                if len(numeric_cols) > 0:
                    # Use the first numeric column for a basic chart
                    visualization = px.bar(df.head(10), y=numeric_cols[0], 
                                         title=f"{numeric_cols[0]} values")
                else:
                    # Create an empty figure
                    import plotly.graph_objects as go
                    visualization = go.Figure()
                    
            except Exception as analyze_error:
                print(f"Error analyzing data: {str(analyze_error)}")
                return jsonify({
                    'success': False,
                    'error': f'Error analyzing data: {str(analyze_error)}'
                })
        
        # Convert visualization to a format the frontend can use
        try:
            # Create a JSON-serializable structure for Plotly
            vis_data = {
                'data': [],
                'layout': {}
            }
            
            # Process visualization data
            if hasattr(visualization, 'data') and hasattr(visualization, 'layout'):
                # Process each trace carefully
                for trace in visualization.data:
                    try:
                        # Convert to a simple dict with only essential properties
                        trace_dict = {
                            'type': trace.type,
                            'mode': getattr(trace, 'mode', None)
                        }
                        
                        # Add basic properties based on the trace type
                        for prop in ['x', 'y', 'z', 'text', 'name', 'hovertext']:
                            if hasattr(trace, prop) and getattr(trace, prop) is not None:
                                # Convert numpy arrays to lists
                                value = getattr(trace, prop)
                                if hasattr(value, 'tolist'):
                                    trace_dict[prop] = value.tolist()
                                else:
                                    trace_dict[prop] = value
                        
                        # Add marker properties if they exist
                        if hasattr(trace, 'marker'):
                            marker = {}
                            for m_prop in ['color', 'size', 'symbol', 'opacity']:
                                if hasattr(trace.marker, m_prop):
                                    marker[m_prop] = getattr(trace.marker, m_prop)
                            if marker:
                                trace_dict['marker'] = marker
                        
                        # Add the trace if it has content
                        if trace_dict:
                            vis_data['data'].append(trace_dict)
                    except Exception as trace_error:
                        print(f"Error processing trace: {str(trace_error)}")
                
                # Process layout carefully - only include essential properties
                try:
                    layout = visualization.layout
                    layout_dict = {}
                    
                    # Add common layout properties
                    for prop in ['width', 'height', 'showlegend']:
                        if hasattr(layout, prop) and getattr(layout, prop) is not None:
                            layout_dict[prop] = getattr(layout, prop)
                    
                    # Handle title specially since it can be an object
                    if hasattr(layout, 'title'):
                        title = layout.title
                        if isinstance(title, dict):
                            layout_dict['title'] = {'text': title.get('text', '')}
                        elif hasattr(title, 'text'):
                            layout_dict['title'] = {'text': title.text}
                        else:
                            layout_dict['title'] = {'text': str(title)}
                    
                    # Handle axes specially
                    for axis in ['xaxis', 'yaxis']:
                        if hasattr(layout, axis):
                            axis_obj = getattr(layout, axis)
                            if axis_obj:
                                axis_dict = {}
                                for a_prop in ['title', 'type', 'range', 'visible']:
                                    if hasattr(axis_obj, a_prop):
                                        # Handle title specially
                                        if a_prop == 'title':
                                            title_obj = getattr(axis_obj, a_prop)
                                            if hasattr(title_obj, 'text'):
                                                axis_dict[a_prop] = {'text': title_obj.text}
                                            elif isinstance(title_obj, dict):
                                                axis_dict[a_prop] = {'text': title_obj.get('text', '')}
                                            else:
                                                axis_dict[a_prop] = {'text': str(title_obj)}
                                        else:
                                            axis_dict[a_prop] = getattr(axis_obj, a_prop)
                                if axis_dict:
                                    layout_dict[axis] = axis_dict
                    
                    vis_data['layout'] = layout_dict
                except Exception as layout_error:
                    print(f"Error processing layout: {str(layout_error)}")
                    # Provide a minimal layout
                    vis_data['layout'] = {
                        'title': {'text': 'Visualization'},
                        'showlegend': True
                    }
                
                # Verify that it's JSON serializable
                try:
                    json.dumps(vis_data)
                    print("Visualization is JSON serializable")
                except TypeError as json_error:
                    print(f"JSON serialization error: {str(json_error)}")
                    # Create a minimal representation
                    vis_data = {
                        'data': [],
                        'layout': {'title': {'text': 'Visualization'}}
                    }
            else:
                print("Visualization doesn't have expected Plotly structure")
                vis_data = None
                
        except Exception as e:
            print(f"Error converting visualization to JSON: {str(e)}")
            vis_data = None
        
        return jsonify({
            'success': True,
            'answer': answer,
            'visualization': vis_data
        })
    except Exception as e:
        print(f"Error in ask_question_api: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        return jsonify({
            'success': False,
            'error': f'Failed to process question: {str(e)}'
        })

@app.route('/create_schedule', methods=['POST'])
def process_schedule_form():
    try:
        # Create upload directory if it doesn't exist
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Get form data
        dataset_name = request.form.get('dataset_name')
        if not dataset_name:
            flash('Dataset name is required', 'error')
            return redirect(url_for('manage_schedules'))
        
        # Debug: Print all form data to see what's being submitted
        print("Form data received:")
        for key, values in request.form.items():
            print(f"  {key}: {values}")
            
        # Get timezone from form or default to UTC
        timezone_str = request.form.get('timezone', 'UTC')
        print(f"Selected timezone: {timezone_str}")
            
        # Schedule type and time - explicitly convert to int with proper error handling
        schedule_type = request.form.get('schedule_type')
        
        # For hour and minute, check raw form values first
        try:
            raw_hour = request.form.get('hour')
            raw_minute = request.form.get('minute')
            print(f"Raw hour value from form: '{raw_hour}'")
            print(f"Raw minute value from form: '{raw_minute}'")
            
            # Try to convert to integer
            hour = int(raw_hour) if raw_hour else 0
            minute = int(raw_minute) if raw_minute else 0
        except (ValueError, TypeError) as e:
            print(f"Error parsing hour/minute: {str(e)}")
            # Fallback to default
            hour = 0
            minute = 0
            
        print(f"Submitted time: {hour:02d}:{minute:02d}")
        print(f"Parsed hour: {hour}, minute: {minute}")
        
        # Create schedule configuration
        schedule_config = {
            'type': schedule_type,
            'hour': hour,
            'minute': minute,
            'timezone': timezone_str,
            'time_str': f"{hour:02d}:{minute:02d} ({timezone_str})" # For display
        }
        
        # Add schedule-specific parameters
        if schedule_type == 'one-time':
            date = request.form.get('date')
            print(f"Date from form: '{date}'")
            if not date:
                flash('Date is required for one-time schedules', 'error')
                return redirect(url_for('manage_schedules'))
            schedule_config['date'] = date
            
            # Add local and UTC datetimes for reference
            try:
                # Use pytz to create timezone-aware datetime
                dt_str = f"{date} {hour:02d}:{minute:02d}:00"
                print(f"Creating datetime from: '{dt_str}'")
                timezone = pytz.timezone(timezone_str)
                local_dt = timezone.localize(datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S'))
                utc_dt = local_dt.astimezone(pytz.UTC)
                schedule_config['local_datetime'] = local_dt.isoformat()
                schedule_config['utc_datetime'] = utc_dt.isoformat()
                print(f"Parsed datetime: {local_dt.isoformat()} (local), {utc_dt.isoformat()} (UTC)")
            except Exception as e:
                print(f"Error parsing datetime: {str(e)}")
                # Continue without the parsed datetime - not critical
        
        elif schedule_type == 'daily':
            # For daily schedules, we only need the time which is already handled above
            pass
            
        elif schedule_type == 'weekly':
            days = request.form.getlist('days')
            if not days:
                flash('At least one day must be selected for weekly schedules', 'error')
                return redirect(url_for('manage_schedules'))
            schedule_config['days'] = days
            
        elif schedule_type == 'monthly':
            day_option = request.form.get('day_option', 'Specific Day')
            schedule_config['day_option'] = day_option
            
            if day_option == 'Specific Day':
                day = request.form.get('day')
                if not day:
                    flash('Day is required for monthly schedules with specific day', 'error')
                    return redirect(url_for('manage_schedules'))
                schedule_config['day'] = int(day)
                
        # Check if email delivery is enabled
        enable_email = request.form.get('enable_email') == 'on'
        
        # Email configuration - only if email is enabled
        email_config = {}
        if enable_email:
            # Get recipients from form
            recipients = request.form.getlist('recipients')
            if not recipients:
                # Try getting as a single comma-separated string
                recipients_str = request.form.get('recipients', '').strip()
                recipients = [r.strip() for r in recipients_str.split(',') if r.strip()]
            
            print(f"Recipients from form: {recipients}")
            
            # Get CC recipients
            cc = request.form.getlist('cc')
            if not cc:
                # Try getting as a single comma-separated string
                cc_str = request.form.get('cc', '').strip()
                cc = [c.strip() for c in cc_str.split(',') if c.strip()]
            
            # Create email config
        email_config = {
                'recipients': recipients,
                'cc': cc,
            'subject': request.form.get('subject', f'Report for {dataset_name}'),
            'body': request.form.get('body', 'Please find the attached report.')
        }
        print(f"Email config created: {email_config}")
        
        # Check if WhatsApp delivery is enabled
        enable_whatsapp = request.form.get('enable_whatsapp') == 'on'
        
        # Add WhatsApp config if enabled
        if enable_whatsapp:
            # Get WhatsApp recipients
            whatsapp_recipients = request.form.getlist('whatsapp_recipients')
            if not whatsapp_recipients:
                # Try getting as a single comma-separated string
                whatsapp_str = request.form.get('whatsapp_recipients', '').strip()
                whatsapp_recipients = [w.strip() for w in whatsapp_str.split(',') if w.strip()]
            
            if whatsapp_recipients:
                email_config['whatsapp_recipients'] = whatsapp_recipients
                
            # Add custom WhatsApp message if provided
            whatsapp_message = request.form.get('whatsapp_message')
            if whatsapp_message:
                email_config['whatsapp_message'] = whatsapp_message
        
        # Ensure at least one delivery method is enabled and configured
        if not enable_email and not enable_whatsapp:
            flash('Please enable at least one delivery method (Email or WhatsApp)', 'error')
            return redirect(url_for('manage_schedules'))
            
        if enable_email and not email_config.get('recipients'):
            flash('At least one email recipient is required when email delivery is enabled', 'error')
            return redirect(url_for('manage_schedules'))
            
        if enable_whatsapp and not email_config.get('whatsapp_recipients'):
            flash('At least one WhatsApp recipient is required when WhatsApp delivery is enabled', 'error')
            return redirect(url_for('manage_schedules'))
        
        # Format configuration - Only PDF is supported now
        format_config = {'type': 'pdf'}
        
        # Add PDF-specific settings
        format_config['page_size'] = request.form.get('page_size', 'a4')
        format_config['orientation'] = request.form.get('orientation', 'portrait')
        
        # Add font settings
        format_config['font_family'] = request.form.get('font_family', 'Arial, sans-serif')
        format_config['font_size'] = int(request.form.get('font_size', '12'))
        format_config['line_height'] = float(request.form.get('line_height', '1.5'))
        
        # Add header settings
        include_header = request.form.get('include_header') == 'on'
        format_config['include_header'] = include_header
        
        if include_header:
            format_config['header_title'] = request.form.get('header_title', f'Report for {dataset_name}')
            
            # Handle logo file upload
            if 'header_logo' in request.files:
                logo_file = request.files['header_logo']
                if logo_file and logo_file.filename != '':
                    # First check if it's an allowed file type
                    if not allowed_file(logo_file.filename):
                        flash('Invalid file format. Only PNG and JPEG images are allowed.', 'error')
                        return redirect(url_for('manage_schedules'))
                    
                    # Then validate image size and dimensions
                    is_valid, validation_message = validate_image(logo_file)
                    if not is_valid:
                        flash(validation_message, 'error')
                        return redirect(url_for('manage_schedules'))
                    
                    # Now we can save the file
                    filename = secure_filename(logo_file.filename)
                    # Add timestamp to filename to make it unique
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    
                    # Create directory if it doesn't exist - use a single, simple path
                    logos_dir = 'static/logos'
                    os.makedirs(logos_dir, exist_ok=True)
                    
                    # No longer needed - using only one location
                    # uploads_logos_dir = os.path.join('uploads', 'logos')
                    # os.makedirs(uploads_logos_dir, exist_ok=True)
                    
                    filepath = os.path.join(logos_dir, filename)
                    logo_file.save(filepath)
                    
                    # Store the relative path to the logo - simpler path
                    format_config['header_logo'] = 'static/logos/' + filename
                else:
                    format_config['header_logo'] = ''
            else:
                format_config['header_logo'] = ''
                
            format_config['header_color'] = request.form.get('header_color', '#0d6efd')
            format_config['header_alignment'] = request.form.get('header_alignment', 'center')
        
        # Add content settings
        format_config['include_summary'] = request.form.get('include_summary') == 'on'
        format_config['include_visualization'] = request.form.get('include_visualization') == 'on'
        
        # Handle column selection
        if request.form.get('select_columns') == 'on':
            selected_columns = request.form.getlist('selected_columns')
            if selected_columns:
                format_config['selected_columns'] = selected_columns
                print(f"Selected columns: {selected_columns}")
        
        # Row limiting
        if request.form.get('limit_rows') == 'on':
            try:
                max_rows = int(request.form.get('max_rows', 1000))
                format_config['max_rows'] = max_rows
            except ValueError:
                format_config['max_rows'] = 1000
        
        # Schedule the report
        print("Scheduling report with config:")
        print(f"Dataset: {dataset_name}")
        print(f"Schedule config: {schedule_config}")
        print(f"Email config: {email_config}")
        print(f"Format config: {format_config}")
        
        job_id = report_manager.schedule_report(
            dataset_name=dataset_name,
            schedule_config=schedule_config,
            email_config=email_config,
            format_config=format_config
        )
        
        if job_id:
            flash(f"Schedule created successfully. Next run at: {report_manager.get_next_run_time(job_id)}", 'success')
        else:
            flash("Failed to create schedule. Check logs for details.", 'error')
            
        return redirect(url_for('manage_schedules'))
        
    except Exception as e:
        print(f"Error in process_schedule_form: {str(e)}")
        flash(f"Error creating schedule: {str(e)}", 'error')
        return redirect(url_for('manage_schedules'))

@app.route('/admin_users')
@login_required
@role_required(['superadmin'])
def admin_users():
    # Redirect to admin dashboard since it already has the user management UI
    return redirect(url_for('admin_dashboard'))

@app.route('/admin_organizations')
@login_required
@role_required(['superadmin'])
def admin_organizations():
    # Get organizations from database
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT rowid, name FROM organizations")
            organizations = []
            for row in cursor.fetchall():
                organizations.append({
                    'id': row[0],
                    'name': row[1]
                })
        
        # Organizations management page
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
                <title>Organizations - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                    .sidebar {
                        position: fixed;
                        top: 0;
                        bottom: 0;
                        left: 0;
                        z-index: 100;
                        padding: 48px 0 0;
                        box-shadow: inset -1px 0 0 rgba(0, 0, 0, .1);
                    }
                    .main {
                        margin-left: 240px;
                        padding: 20px;
                    }
            </style>
        </head>
        <body>
                <nav class="col-md-3 col-lg-2 d-md-block bg-light sidebar">
                    <div class="position-sticky pt-3">
                        <div class="px-3">
                            <h5>👤 Admin Profile</h5>
                            <p><strong>Username:</strong> {{ session.user.username }}</p>
                            <p><strong>Role:</strong> {{ session.user.role }}</p>
                        </div>
                        <hr>
                        <div class="px-3">
                            <a href="{{ url_for('admin_users') }}" class="btn btn-primary w-100 mb-2">👥 Users</a>
                            <a href="{{ url_for('admin_organizations') }}" class="btn btn-primary w-100 mb-2">🏢 Organizations</a>
                            <a href="{{ url_for('admin_system') }}" class="btn btn-primary w-100 mb-2">⚙️ System</a>
                            <hr>
                            <a href="{{ url_for('logout') }}" class="btn btn-secondary w-100">🚪 Logout</a>
                        </div>
                    </div>
                </nav>
                
                <main class="main">
                    <h1>🏢 Organizations Management</h1>
                    
                    <div class="card mb-4">
                        <div class="card-body">
                            <h5>Add New Organization</h5>
                            <form id="addOrgForm" onsubmit="return addOrganization(event)">
                                        <div class="row">
                                            <div class="col-md-6">
                                                <div class="mb-3">
                                            <label class="form-label">Organization Name</label>
                                            <input type="text" class="form-control" name="name" required>
                                                </div>
                                            </div>
                                            <div class="col-md-6">
                                                <div class="mb-3">
                                            <label class="form-label">&nbsp;</label>
                                            <button type="submit" class="btn btn-primary w-100">Create Organization</button>
                                                </div>
                                            </div>
                                        </div>
                            </form>
                                        </div>
                                    </div>
                                    
                    <div class="card">
                        <div class="card-body">
                            <h5>Existing Organizations</h5>
                            <div class="table-responsive">
                                <table class="table table-hover">
                                    <thead>
                                        <tr>
                                            <th>ID</th>
                                            <th>Name</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for org in organizations %}
                                            <tr>
                                                <td>{{ org.id }}</td>
                                                <td>{{ org.name }}</td>
                                                <td>
                                                    <div class="btn-group btn-group-sm">
                                                        <button class="btn btn-outline-primary"
                                                                onclick="editOrg('{{ org.id }}')">
                                                            ✏️ Edit
                                                        </button>
                                                        <button class="btn btn-outline-danger"
                                                                onclick="deleteOrg('{{ org.id }}')">
                                                            🗑️ Delete
                                                        </button>
                            </div>
                                                </td>
                                            </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                        </div>
                    </div>
                </div>
                </main>
            
                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                    function addOrganization(event) {
                        event.preventDefault();
                        // Implement add organization functionality
                        alert('Add organization functionality not implemented yet');
                        return false;
                    }
                    
                    function editOrg(orgId) {
                        // Implement edit organization functionality
                        alert('Edit organization functionality not implemented yet');
                    }
                    
                    function deleteOrg(orgId) {
                        // Implement delete organization functionality
                        alert('Delete organization functionality not implemented yet');
                    }
            </script>
        </body>
        </html>
        ''', organizations=organizations)
    except Exception as e:
        print(f"Error in admin_organizations function: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        flash(f'Error loading organizations page: {str(e)}')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin_system')
@login_required
@role_required(['superadmin'])
def admin_system():
    try:
        import sys
        import flask
        import time
        from datetime import datetime
    
        template = '''
        <!DOCTYPE html>
        <html>
        <head>
                <title>System Settings - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                    .sidebar {
                        position: fixed;
                        top: 0;
                        bottom: 0;
                        left: 0;
                        z-index: 100;
                        padding: 48px 0 0;
                        box-shadow: inset -1px 0 0 rgba(0, 0, 0, .1);
                    }
                    .main {
                        margin-left: 240px;
                        padding: 20px;
                }
            </style>
        </head>
        <body>
                <nav class="col-md-3 col-lg-2 d-md-block bg-light sidebar">
                    <div class="position-sticky pt-3">
                        <div class="px-3">
                            <h5>👤 Admin Profile</h5>
                            <p><strong>Username:</strong> {{ session.user.username }}</p>
                            <p><strong>Role:</strong> {{ session.user.role }}</p>
                            </div>
                        <hr>
                        <div class="px-3">
                        <a href="{{ url_for('admin_dashboard') }}" class="btn btn-primary w-100 mb-2">👥 Users</a>
                            <a href="{{ url_for('admin_organizations') }}" class="btn btn-primary w-100 mb-2">🏢 Organizations</a>
                            <a href="{{ url_for('admin_system') }}" class="btn btn-primary w-100 mb-2">⚙️ System</a>
                            <hr>
                            <a href="{{ url_for('logout') }}" class="btn btn-secondary w-100">🚪 Logout</a>
                        </div>
                    </div>
                </nav>
                
                <main class="main">
                <div class="container-fluid">
                    <h1>⚙️ System Settings</h1>
                    
                    <div class="card mb-4">
                                        <div class="card-body">
                            <h5>Email Configuration</h5>
                            <form id="emailConfigForm">
                                <div class="mb-3">
                                    <label class="form-label">SMTP Server</label>
                                    <input type="text" class="form-control" name="smtp_server" 
                                           value="{{ os.getenv('SMTP_SERVER', '') }}" required>
                                        </div>
                                <div class="mb-3">
                                    <label class="form-label">SMTP Port</label>
                                    <input type="number" class="form-control" name="smtp_port" 
                                           value="{{ os.getenv('SMTP_PORT', '587') }}" required>
                                    </div>
                                <div class="mb-3">
                                    <label class="form-label">Sender Email</label>
                                    <input type="email" class="form-control" name="sender_email" 
                                           value="{{ os.getenv('SENDER_EMAIL', '') }}" required>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Sender Password</label>
                                    <input type="password" class="form-control" name="sender_password" 
                                           value="{{ os.getenv('SENDER_PASSWORD', '') }}" required>
                        </div>
                                <button type="submit" class="btn btn-primary">Save Settings</button>
                            </form>
                            </div>
                        </div>
                        
                        <div class="card mb-4">
                            <div class="card-body">
                            <h5>Database Management</h5>
                            <div class="row">
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">Backup Database</label>
                                        <button class="btn btn-primary w-100" onclick="backupDatabase()">
                                            Create Backup
                                        </button>
                            </div>
                        </div>
                                <div class="col-md-6">
                                    <div class="mb-3">
                                        <label class="form-label">Restore Database</label>
                                        <input type="file" class="form-control" id="restoreFile" accept=".db">
                                        <button class="btn btn-warning w-100 mt-2" onclick="restoreDatabase()">
                                            Restore from Backup
                                        </button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                            </div>
                            
                    <div class="card">
                        <div class="card-body">
                            <h5>System Information</h5>
                            <div class="table-responsive">
                                <table class="table">
                                    <tbody>
                                        <tr>
                                            <th>Python Version</th>
                                            <td>{{ sys.version.split()[0] }}</td>
                                        </tr>
                                        <tr>
                                            <th>Flask Version</th>
                                            <td>{{ flask.__version__ }}</td>
                                        </tr>
                                        <tr>
                                            <th>Server Time</th>
                                            <td>{{ datetime.now().strftime('%Y-%m-%d %H:%M:%S') }}</td>
                                        </tr>
                                        <tr>
                                            <th>Server Timezone</th>
                                            <td>{{ time.tzname[0] }}</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                            </div>
                    </div>
                </div>
                </main>
            
                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                document.getElementById('emailConfigForm').addEventListener('submit', async function(e) {
                        e.preventDefault();
                    
                    // Get form data
                    const formData = new FormData(this);
                    const data = {
                        smtp_server: formData.get('smtp_server'),
                        smtp_port: parseInt(formData.get('smtp_port')),
                        sender_email: formData.get('sender_email'),
                        sender_password: formData.get('sender_password')
                    };
                    
                    try {
                        // Show loading state
                        const submitBtn = this.querySelector('button[type="submit"]');
                        const originalText = submitBtn.innerHTML;
                        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Saving...';
                        submitBtn.disabled = true;
                        
                        // Send request to save settings
                        const response = await fetch('/api/system/email-settings', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(data)
                        });
                        
                        const result = await response.json();
                        
                        if (result.success) {
                            // Show success message
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-success alert-dismissible fade show';
                            alertDiv.innerHTML = `
                                ${result.message}
                                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                            `;
                            document.querySelector('.container-fluid').prepend(alertDiv);
                        } else {
                            throw new Error(result.error || 'Failed to save settings');
                        }
                    } catch (error) {
                        // Show error message
                        const alertDiv = document.createElement('div');
                        alertDiv.className = 'alert alert-danger alert-dismissible fade show';
                        alertDiv.innerHTML = `
                            Error saving settings: ${error.message}
                            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                        `;
                        document.querySelector('.container-fluid').prepend(alertDiv);
                    } finally {
                        // Reset button state
                        const submitBtn = this.querySelector('button[type="submit"]');
                        submitBtn.innerHTML = 'Save Settings';
                        submitBtn.disabled = false;
                    }
                    });
                    
                    function backupDatabase() {
                        alert('Backup database functionality not implemented yet');
                    }
                    
                    function restoreDatabase() {
                        alert('Restore database functionality not implemented yet');
                }
            </script>
        </body>
        </html>
        '''
        
        return render_template_string(template, os=os, sys=sys, flask=flask, time=time, datetime=datetime)
    except Exception as e:
        print(f"Error in admin_system function: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        flash(f'Error loading system settings page: {str(e)}')
        return redirect(url_for('admin_dashboard'))

@app.route('/api/users/<user_id>', methods=['GET'])
@login_required
@role_required(['superadmin'])
def get_user_api(user_id):
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.rowid, u.username, u.email, u.role, u.organization_id
                FROM users u
                WHERE u.rowid = ?
            """, (user_id,))
            user_data = cursor.fetchone()
            
            if not user_data:
                return jsonify({'success': False, 'error': 'User not found'})
                
            user = {
                'id': user_data[0],
                'username': user_data[1],
                'email': user_data[2],
                'role': user_data[3],
                'organization_id': user_data[4] or ''
            }
            
            return jsonify({'success': True, 'user': user})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/users/<user_id>', methods=['PUT'])
@login_required
@role_required(['superadmin'])
def update_user_api(user_id):
    try:
        data = request.json
        
        # Prepare the update data
        update_data = {
            'username': data.get('username'),
            'email': data.get('email'),
            'role': data.get('permission_type'),  # Map permission_type to role
            'organization_id': data.get('organization_id') or None
        }
        
        # Only include password if it was provided and not empty
        if data.get('password') and data.get('password').strip():
            update_data['password_hash'] = generate_password_hash(data['password'])
        
        # Update the user in the database
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            
            # Construct the SET clause dynamically based on what fields are provided
            set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])
            values = list(update_data.values())
            values.append(user_id)  # For the WHERE clause
            
            query = f"UPDATE users SET {set_clause} WHERE rowid = ?"
            cursor.execute(query, values)
            conn.commit()
            
            if cursor.rowcount == 0:
                return jsonify({'success': False, 'error': 'User not found or no changes made'})
            
            return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/tableau-connect', endpoint='tableau_connect')
@login_required
def tableau_connect():
    """Page to connect to Tableau Server and download data"""
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Connect to Tableau - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
                .form-container {
                    max-width: 800px;
                    margin: 0 auto;
                }
                .card {
                    margin-bottom: 20px;
                }
                .loading {
                    display: none;
                    text-align: center;
                    padding: 20px;
                }
                .loading-spinner {
                    width: 3rem;
                    height: 3rem;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="form-container">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                        <h1>Connect to Tableau Server</h1>
                        <a href="{{ url_for('home') }}" class="btn btn-outline-primary">← Back to Dashboard</a>
                        </div>
                        
                    {% with messages = get_flashed_messages() %}
                        {% if messages %}
                            {% for message in messages %}
                                <div class="alert alert-info">{{ message }}</div>
                            {% endfor %}
                        {% endif %}
                    {% endwith %}
                    
                                    <div class="card">
                                        <div class="card-body">
                            <h5 class="card-title">Connection Details</h5>
                            <form id="connectionForm" method="post" action="{{ url_for('process_tableau_connection') }}">
                                            <div class="mb-3">
                                    <label class="form-label">Tableau Server URL</label>
                                    <input type="text" class="form-control" name="server_url" 
                                           placeholder="https://your-server.tableau.com" required>
                                    <div class="form-text">Include https:// and don't include a trailing slash</div>
                                            </div>
                                            
                                                <div class="mb-3">
                                    <label class="form-label">Site Name (leave empty for Default)</label>
                                    <input type="text" class="form-control" name="site_name" 
                                           placeholder="Site name (not URL)">
                                    <div class="form-text">For default site, leave this blank</div>
                                            </div>
                                            
                                                <div class="mb-3">
                                    <label class="form-label">Authentication Method</label>
                                    <select class="form-select" name="auth_method" id="authMethod" required>
                                        <option value="password">Username / Password</option>
                                        <option value="token">Personal Access Token</option>
                                                    </select>
                                            </div>
                                            
                                <!-- Username/Password Auth Fields -->
                                <div id="userPassAuth">
                                                    <div class="mb-3">
                                        <label class="form-label">Username</label>
                                        <input type="text" class="form-control" name="username">
                                            </div>
                                            
                                            <div class="mb-3">
                                        <label class="form-label">Password</label>
                                        <input type="password" class="form-control" name="password">
                                    </div>
                                </div>
                                
                                <!-- Token Auth Fields -->
                                <div id="tokenAuth" style="display: none;">
                                                            <div class="mb-3">
                                        <label class="form-label">Personal Access Token Name</label>
                                        <input type="text" class="form-control" name="token_name">
                                                    </div>
                                                    
                                                            <div class="mb-3">
                                        <label class="form-label">Personal Access Token Value</label>
                                        <input type="password" class="form-control" name="token_value">
                                                    </div>
                                                </div>
                                                
                                <button type="submit" class="btn btn-primary" id="connectButton">
                                    Connect to Tableau
                                </button>
                            </form>
                            
                            <div id="loadingIndicator" class="loading">
                                <div class="spinner-border loading-spinner text-primary" role="status">
                                    <span class="visually-hidden">Loading...</span>
                                                    </div>
                                <p class="mt-3">Connecting to Tableau and retrieving workbooks... This may take a minute.</p>
                                                            </div>
                                                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                // Toggle auth method fields
                document.getElementById('authMethod').addEventListener('change', function() {
                    const authMethod = this.value;
                    if (authMethod === 'password') {
                        document.getElementById('userPassAuth').style.display = 'block';
                        document.getElementById('tokenAuth').style.display = 'none';
                        } else {
                        document.getElementById('userPassAuth').style.display = 'none';
                        document.getElementById('tokenAuth').style.display = 'block';
                    }
                });
                
                // Show loading indicator on form submit
                document.getElementById('connectionForm').addEventListener('submit', function() {
                    document.getElementById('connectButton').disabled = true;
                    document.getElementById('loadingIndicator').style.display = 'block';
                });
            </script>
        </body>
        </html>
    ''')

@app.route('/process-tableau-connection', methods=['POST'], endpoint='process_tableau_connection')
@login_required
def process_tableau_connection():
    """Process the Tableau Server connection form"""
    try:
        # Get form data
        server_url = request.form.get('server_url')
        site_name = request.form.get('site_name')
        auth_method = request.form.get('auth_method')
        
        if not server_url:
            flash('Server URL is required')
            return redirect(url_for('tableau_connect'))
        
        # Process auth credentials based on method
        credentials = {}
        if auth_method == 'password':
            username = request.form.get('username')
            password = request.form.get('password')
            if not username or not password:
                flash('Username and password are required for password authentication')
                return redirect(url_for('tableau_connect'))
            credentials = {'username': username, 'password': password}
        else:  # token auth
            token_name = request.form.get('token_name')
            token_value = request.form.get('token_value')
            if not token_name or not token_value:
                flash('Token name and value are required for token authentication')
                return redirect(url_for('tableau_connect'))
            credentials = {'token_name': token_name, 'token': token_value}
        
        # Authenticate with Tableau
        try:
            print(f"Connecting to Tableau Server: {server_url}")
            server = authenticate(server_url, auth_method, credentials, site_name)
            if not server:
                flash('Authentication failed. Please check your credentials and try again.')
                return redirect(url_for('tableau_connect'))
            
            # Get workbooks
            workbooks = get_workbooks(server)
            if not workbooks:
                flash('No workbooks found or failed to retrieve workbooks')
                return redirect(url_for('tableau_connect'))
            
            # Store in session for next step
            session['tableau_server'] = {
                'server_url': server_url,
                'site_name': site_name,
                'auth_method': auth_method,
                'credentials': credentials  # Note: In production, consider more secure storage
            }
            session['tableau_workbooks'] = workbooks
            
            # Redirect to select workbook page
            return redirect(url_for('select_tableau_workbook'))
            
        except Exception as e:
            flash(f'Error connecting to Tableau: {str(e)}')
            return redirect(url_for('tableau_connect'))
        
    except Exception as e:
        flash(f'Error processing form: {str(e)}')
        return redirect(url_for('tableau_connect'))

@app.route('/select-tableau-workbook', endpoint='select_tableau_workbook')
@login_required
def select_tableau_workbook():
    """Page to select a workbook and views to download"""
    # Check if we have workbooks in session
    if 'tableau_workbooks' not in session:
        flash('Please connect to Tableau first')
        return redirect(url_for('tableau_connect'))
    
    workbooks = session['tableau_workbooks']
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Select Workbook - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
                .form-container {
                    max-width: 800px;
                    margin: 0 auto;
                }
                .card {
                    margin-bottom: 20px;
                }
                .loading {
                    display: none;
                    text-align: center;
                    padding: 20px;
                }
                .loading-spinner {
                    width: 3rem;
                    height: 3rem;
                }
                .workbook-card {
                    cursor: pointer;
                }
                .workbook-card:hover {
                    border-color: #0d6efd;
                }
                .workbook-card.selected {
                    border-color: #0d6efd;
                    background-color: rgba(13, 110, 253, 0.1);
                }
                .form-check, .btn {
                    position: relative;
                    z-index: 10;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="form-container">
                <div class="d-flex justify-content-between align-items-center mb-4">
                        <h1>Select Tableau Workbook</h1>
                        <a href="{{ url_for('tableau_connect') }}" class="btn btn-outline-primary">← Back</a>
                </div>
                
                    {% with messages = get_flashed_messages() %}
                        {% if messages %}
                            {% for message in messages %}
                                <div class="alert alert-info">{{ message }}</div>
                            {% endfor %}
                        {% endif %}
                    {% endwith %}
                    
                    <div class="card mb-4">
                        <div class="card-body">
                            <h5 class="card-title">Available Workbooks</h5>
                            
                            {% if workbooks %}
                                <form id="workbookForm" method="post" action="{{ url_for('process_workbook_selection') }}">
                <div class="row">
                                        {% for workbook in workbooks %}
                                            <div class="col-md-6 mb-3">
                                                <div class="card workbook-card h-100" data-workbook-id="{{ workbook.id }}">
                                                    <div class="card-body">
                                                        <h5 class="card-title">{{ workbook.name }}</h5>
                                                        <p class="card-text text-muted">Project: {{ workbook.project_name }}</p>
                                                        
                                                        {% if workbook.views %}
                                                            <div class="form-check form-switch mb-2" onclick="event.stopPropagation();">
                                                                <input class="form-check-input workbook-selector" 
                                                                       type="checkbox" 
                                                                       id="workbook-{{ workbook.id }}" 
                                                                       name="workbook" 
                                                                       value="{{ workbook.id }}"
                                                                       data-name="{{ workbook.name }}">
                                                                <label class="form-check-label" for="workbook-{{ workbook.id }}">
                                                                    Select this workbook
                                                                </label>
                                                            </div>
                                                            
                                                            <div class="views-container" style="display: none;" id="views-{{ workbook.id }}">
                                                                <hr>
                                                                <h6>Available Views:</h6>
                                                                <div class="mb-2">
                                                                    <button type="button" class="btn btn-sm btn-outline-secondary mb-2"
                                                                            onclick="selectAllViews('{{ workbook.id }}', event)">
                                                                        Select All
                                    </button>
                                                                    <button type="button" class="btn btn-sm btn-outline-secondary mb-2"
                                                                            onclick="deselectAllViews('{{ workbook.id }}', event)">
                                                                        Deselect All
                                    </button>
                                </div>
                                                                
                                                                {% for view in workbook.views %}
                                                                    <div class="form-check" onclick="event.stopPropagation();">
                                                                        <input class="form-check-input view-selector-{{ workbook.id }}" 
                                                                               type="checkbox" 
                                                                               id="view-{{ view.id }}" 
                                                                               name="views-{{ workbook.id }}" 
                                                                               value="{{ view.id }}"
                                                                               data-name="{{ view.name }}">
                                                                        <label class="form-check-label" for="view-{{ view.id }}">
                                                                            {{ view.name }}
                                                                        </label>
                            </div>
                                                                {% endfor %}
                                </div>
                                                        {% else %}
                                                            <p class="text-muted">No views available</p>
                                    {% endif %}
                            </div>
                        </div>
                    </div>
                    {% endfor %}
                </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Dataset Name (will be used in the database)</label>
                                        <input type="text" class="form-control" name="dataset_name" id="datasetName" required>
                                        <div class="form-text">This name will be used to identify the dataset in the database</div>
            </div>
            
                                    <button type="submit" class="btn btn-primary" id="downloadButton">
                                        Download Selected Views
                                    </button>
                                </form>
                                
                                <div id="loadingIndicator" class="loading">
                                    <div class="spinner-border loading-spinner text-primary" role="status">
                                        <span class="visually-hidden">Loading...</span>
                        </div>
                                    <p class="mt-3">Downloading data from Tableau... This may take a few minutes for large datasets.</p>
                        </div>
                            {% else %}
                                <div class="alert alert-info">
                                    No workbooks found. Please check your permissions or try a different site.
                                </div>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                // Initialize the page
                document.addEventListener('DOMContentLoaded', function() {
                    // Add click listeners to all workbook cards
                    document.querySelectorAll('.workbook-card').forEach(card => {
                        card.addEventListener('click', function() {
                            const workbookId = this.dataset.workbookId;
                            toggleWorkbookSelection(workbookId);
                        });
                    });
                    
                    // Add change listeners to all workbook checkboxes
                    document.querySelectorAll('.workbook-selector').forEach(checkbox => {
                        checkbox.addEventListener('change', function() {
                            const workbookId = this.value;
                            updateViewsVisibility(workbookId);
                            updateDatasetName();
                        });
                    });
                });
                
                // Toggle workbook selection when card is clicked
                function toggleWorkbookSelection(workbookId) {
                    const checkbox = document.getElementById('workbook-' + workbookId);
                    checkbox.checked = !checkbox.checked;
                    
                    // Trigger the change event manually
                    const event = new Event('change');
                    checkbox.dispatchEvent(event);
                }
                
                // Show/hide views based on workbook selection
                function updateViewsVisibility(workbookId) {
                    const checkbox = document.getElementById('workbook-' + workbookId);
                    const viewsContainer = document.getElementById('views-' + workbookId);
                    const workbookCard = checkbox.closest('.workbook-card');
                    
                    if (checkbox.checked) {
                        viewsContainer.style.display = 'block';
                        workbookCard.classList.add('selected');
                    } else {
                        viewsContainer.style.display = 'none';
                        workbookCard.classList.remove('selected');
                        // Uncheck all views
                        document.querySelectorAll('.view-selector-' + workbookId).forEach(view => {
                            view.checked = false;
                        });
                    }
                }
                
                // Select all views for a workbook
                function selectAllViews(workbookId, event) {
                    if (event) {
                        event.stopPropagation();
                    }
                    document.querySelectorAll('.view-selector-' + workbookId).forEach(view => {
                        view.checked = true;
                    });
                }
                
                // Deselect all views for a workbook
                function deselectAllViews(workbookId, event) {
                    if (event) {
                        event.stopPropagation();
                    }
                    document.querySelectorAll('.view-selector-' + workbookId).forEach(view => {
                        view.checked = false;
                    });
                }
                
                // Auto-generate dataset name based on selections
                function updateDatasetName() {
                    const selectedWorkbooks = [];
                    document.querySelectorAll('.workbook-selector:checked').forEach(workbook => {
                        selectedWorkbooks.push(workbook.dataset.name);
                    });
                    
                    if (selectedWorkbooks.length > 0) {
                        document.getElementById('datasetName').value = selectedWorkbooks.join('_').replace(/[^a-zA-Z0-9]/g, '_');
                        } else {
                        document.getElementById('datasetName').value = '';
                    }
                }
                
                // Show loading indicator on form submit
                document.getElementById('workbookForm').addEventListener('submit', function(e) {
                    // Validate that at least one view is selected
                    let hasSelectedView = false;
                    document.querySelectorAll('.workbook-selector:checked').forEach(workbook => {
                        const workbookId = workbook.value;
                        document.querySelectorAll('.view-selector-' + workbookId + ':checked').forEach(() => {
                            hasSelectedView = true;
                        });
                    });
                    
                    if (!hasSelectedView) {
                        e.preventDefault();
                        alert('Please select at least one view to download');
                        return;
                    }
                    
                    document.getElementById('downloadButton').disabled = true;
                    document.getElementById('loadingIndicator').style.display = 'block';
                });
            </script>
        </body>
        </html>
    ''', workbooks=workbooks)

@app.route('/process-workbook-selection', methods=['POST'], endpoint='process_workbook_selection')
@login_required
def process_workbook_selection():
    """Process the workbook and views selection and download data"""
    try:
        # Check if we have server info in session
        if 'tableau_server' not in session or 'tableau_workbooks' not in session:
            flash('Session expired. Please connect to Tableau again.')
            return redirect(url_for('tableau_connect'))
        
        # Get selected workbook and views
        workbook_id = request.form.get('workbook')
        views_key = f'views-{workbook_id}'
        view_ids = request.form.getlist(views_key)
        dataset_name = request.form.get('dataset_name')
        
        if not workbook_id or not view_ids or not dataset_name:
            flash('Please select a workbook, at least one view, and provide a dataset name')
            return redirect(url_for('select_tableau_workbook'))
        
        # Find workbook details in session
        workbooks = session['tableau_workbooks']
        selected_workbook = None
        for wb in workbooks:
            if wb['id'] == workbook_id:
                selected_workbook = wb
                break
        
        if not selected_workbook:
            flash('Selected workbook not found')
            return redirect(url_for('select_tableau_workbook'))
        
        # Get view names for the selected views
        view_names = []
        for view in selected_workbook['views']:
            if view['id'] in view_ids:
                view_names.append(view['name'])
        
        # Re-authenticate with Tableau
        server_info = session['tableau_server']
        try:
            server = authenticate(
                server_info['server_url'], 
                server_info['auth_method'], 
                server_info['credentials'], 
                server_info['site_name']
            )
            
            if not server:
                flash('Re-authentication failed. Please try connecting again.')
                return redirect(url_for('tableau_connect'))
                
            # Generate table name
            table_name = generate_table_name(selected_workbook['name'], view_names)
            if dataset_name:
                # Use dataset_name if provided, but sanitize it for SQLite
                table_name = ''.join(c if c.isalnum() else '_' for c in dataset_name)
                if not table_name[0].isalpha():
                    table_name = 'table_' + table_name
            
            # Download data
            success = download_and_save_data(
                server, 
                view_ids,
                selected_workbook['name'],
                view_names,
                table_name
            )
            
            if success:
                flash(f'Data downloaded successfully and saved as "{table_name}"')
                return redirect(url_for('home'))
            else:
                flash('Failed to download data from Tableau')
                return redirect(url_for('select_tableau_workbook'))
                
        except Exception as e:
            flash(f'Error downloading data: {str(e)}')
            return redirect(url_for('select_tableau_workbook'))
        
    except Exception as e:
        flash(f'Error processing selection: {str(e)}')
        return redirect(url_for('select_tableau_workbook'))

@app.route('/schedule-reports', endpoint='schedule_reports')
@login_required
def schedule_reports():
    """Page to schedule reports"""
    # Get all available datasets
    datasets = get_saved_datasets()
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Schedule Reports - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
                .dataset-card {
                    transition: all 0.3s ease;
                }
                .dataset-card:hover {
                    transform: translateY(-5px);
                    box-shadow: 0 10px 20px rgba(0,0,0,0.1);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h1><i class="bi bi-calendar-plus"></i> Schedule Reports</h1>
                    <a href="{{ url_for('home') }}" class="btn btn-outline-primary">← Back to Dashboard</a>
                </div>
                
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category if category != 'message' else 'info' }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <div class="card mb-4">
                    <div class="card-header">
                        <h5 class="mb-0"><i class="bi bi-table"></i> Available Datasets</h5>
                    </div>
                    <div class="card-body">
                        {% if datasets %}
                            <div class="row">
                                {% for dataset in datasets %}
                                    <div class="col-md-4 mb-4">
                                        <div class="card dataset-card h-100">
                                            <div class="card-body">
                                                <h5 class="card-title">{{ dataset }}</h5>
                                                <h6 class="card-subtitle mb-2 text-muted">{{ get_dataset_row_count(dataset) }} rows</h6>
                                                <p class="card-text">Create a scheduled report for this dataset.</p>
                                            </div>
                                            <div class="card-footer">
                                                <a href="{{ url_for('schedule_dataset', dataset=dataset) }}" class="btn btn-primary">
                                                    <i class="bi bi-calendar-plus"></i> Schedule Report
                                                </a>
                                            </div>
                                        </div>
                                    </div>
                                {% endfor %}
                            </div>
                        {% else %}
                            <div class="alert alert-info">
                                <p>No datasets available for scheduling. Please connect to Tableau and download data first.</p>
                                <a href="{{ url_for('tableau_connect') }}" class="btn btn-primary">
                                    <i class="bi bi-box-arrow-in-right"></i> Connect to Tableau
                                </a>
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
    ''', datasets=datasets, get_dataset_row_count=get_dataset_row_count)

@app.route('/manage-schedules', endpoint='manage_schedules')
@login_required
def manage_schedules():
    """Page to manage existing schedules"""
    
    # Get all schedules from the ReportManager
    try:
        schedules = report_manager.get_schedules()
    except Exception as e:
        print(f"Error getting schedules: {e}")
        schedules = []
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Manage Schedules - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
                .status-active {
                    color: #198754;
                }
                .status-paused {
                    color: #fd7e14;
                }
                .status-error {
                    color: #dc3545;
                }
                .schedule-actions .btn {
                    margin-right: 5px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h1><i class="bi bi-calendar-check"></i> Manage Schedules</h1>
                    <div>
                        <a href="{{ url_for('schedule_reports') }}" class="btn btn-success me-2">
                            <i class="bi bi-plus-circle"></i> New Schedule
                        </a>
                        <a href="{{ url_for('home') }}" class="btn btn-outline-primary">
                            ← Back to Dashboard
                        </a>
                    </div>
                </div>
                
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category if category != 'message' else 'info' }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                {% if schedules %}
                    <div class="card">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="bi bi-list-check"></i> Your Scheduled Reports</h5>
                        </div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-hover">
                                    <thead>
                                        <tr>
                                            <th>Dataset</th>
                                            <th>Schedule Type</th>
                                            <th>Next Run</th>
                                            <th>Recipients</th>
                                            <th>Format</th>
                                            <th>Status</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for schedule in schedules %}
                                            <tr>
                                                <td>{{ schedule.dataset_name }}</td>
                                                <td>
                                                    {% if schedule.schedule_type == 'one-time' %}
                                                        <span class="badge bg-primary">One-time</span>
                                                    {% elif schedule.schedule_type == 'daily' %}
                                                        <span class="badge bg-primary">Daily</span>
                                                    {% elif schedule.schedule_type == 'weekly' %}
                                                        <span class="badge bg-primary">Weekly</span>
                                                        {% if schedule.days %}
                                                            <div class="small text-muted">{{ schedule.days|join(', ') }}</div>
                                                        {% endif %}
                                                    {% elif schedule.schedule_type == 'monthly' %}
                                                        <span class="badge bg-primary">Monthly</span>
                                                        {% if schedule.day_option %}
                                                            <div class="small text-muted">{{ schedule.day_option }}</div>
                                                        {% endif %}
                                                    {% endif %}
                                                </td>
                                                <td>
                                                    {% if schedule.next_run %}
                                                        {{ schedule.next_run }}
                                                    {% else %}
                                                        <span class="text-muted">Not scheduled</span>
                                                    {% endif %}
                                                </td>
                                                <td>
                                                    {% if schedule.email_config and schedule.email_config.recipients %}
                                                        {% for recipient in schedule.email_config.recipients[:2] %}
                                                            <div>{{ recipient }}</div>
                                                        {% endfor %}
                                                        {% if schedule.email_config.recipients|length > 2 %}
                                                            <span class="badge bg-secondary">+{{ schedule.email_config.recipients|length - 2 }} more</span>
                                                        {% endif %}
                                                    {% else %}
                                                        <span class="text-muted">No recipients</span>
                                                    {% endif %}
                                                </td>
                                                <td>
                                                    {% if schedule.format_config %}
                                                        <span class="badge bg-info text-dark">{{ schedule.format_config.type|upper }}</span>
                                                    {% else %}
                                                        <span class="text-muted">Not specified</span>
                                                    {% endif %}
                                                </td>
                                                <td>
                                                    {% if schedule.status == 'active' %}
                                                        <span class="status-active"><i class="bi bi-check-circle-fill"></i> Active</span>
                                                    {% elif schedule.status == 'paused' %}
                                                        <span class="status-paused"><i class="bi bi-pause-circle-fill"></i> Paused</span>
                                                    {% elif schedule.status == 'error' %}
                                                        <span class="status-error"><i class="bi bi-exclamation-circle-fill"></i> Error</span>
                                                    {% else %}
                                                        <span class="text-muted"><i class="bi bi-question-circle-fill"></i> Unknown</span>
                                                    {% endif %}
                                                </td>
                                                <td class="schedule-actions">
                                                    <button type="button" class="btn btn-sm btn-outline-primary" 
                                                            onclick="editSchedule('{{ schedule.id }}')">
                                                        <i class="bi bi-pencil"></i>
                                                    </button>
                                                    <button type="button" class="btn btn-sm btn-outline-danger"
                                                            onclick="deleteSchedule('{{ schedule.id }}')">
                                                        <i class="bi bi-trash"></i>
                                                    </button>
                                                    {% if schedule.status == 'active' %}
                                                        <button type="button" class="btn btn-sm btn-outline-warning"
                                                                onclick="pauseSchedule('{{ schedule.id }}')">
                                                            <i class="bi bi-pause"></i>
                                                        </button>
                                                    {% elif schedule.status == 'paused' %}
                                                        <button type="button" class="btn btn-sm btn-outline-success"
                                                                onclick="resumeSchedule('{{ schedule.id }}')">
                                                            <i class="bi bi-play"></i>
                                                        </button>
                                                    {% endif %}
                                                    <button type="button" class="btn btn-sm btn-outline-secondary"
                                                            onclick="runScheduleNow('{{ schedule.id }}')">
                                                        <i class="bi bi-send"></i> Run Now
                                                    </button>
                                                </td>
                                            </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                {% else %}
                    <div class="alert alert-info">
                        <h4><i class="bi bi-info-circle"></i> No schedules found</h4>
                        <p>You haven't created any report schedules yet. Create your first schedule to get started.</p>
                        <a href="{{ url_for('schedule_reports') }}" class="btn btn-primary">
                            <i class="bi bi-calendar-plus"></i> Create Schedule
                        </a>
                    </div>
                {% endif %}
                
                <!-- Delete Confirmation Modal -->
                <div class="modal fade" id="deleteConfirmModal" tabindex="-1" aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">Confirm Delete</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <p>Are you sure you want to delete this schedule?</p>
                                <p class="text-danger">This action cannot be undone.</p>
                                <input type="hidden" id="deleteScheduleId">
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                                <button type="button" class="btn btn-danger" id="confirmDeleteBtn">Delete Schedule</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                function editSchedule(scheduleId) {
                    if (!scheduleId) {
                        alert('Invalid schedule ID');
                        return;
                    }
                    // Redirect to edit page with proper schedule ID
                    window.location.href = `/edit-schedule/${scheduleId}`;
                }
                
                function deleteSchedule(scheduleId) {
                    if (!scheduleId) {
                        alert('Invalid schedule ID');
                        return;
                    }
                    
                    // Show confirmation modal
                    const modal = new bootstrap.Modal(document.getElementById('deleteConfirmModal'));
                    document.getElementById('deleteScheduleId').value = scheduleId;
                    
                    // Set up the confirm button
                    document.getElementById('confirmDeleteBtn').onclick = function() {
                        // Show loading state
                        const confirmBtn = document.getElementById('confirmDeleteBtn');
                        const originalText = confirmBtn.innerHTML;
                        confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Deleting...';
                        confirmBtn.disabled = true;
                        
                        // Send delete request
                        fetch(`/api/schedules/${scheduleId}`, {
                            method: 'DELETE',
                            headers: {
                                'Content-Type': 'application/json'
                            }
                        })
                        .then(response => {
                            if (response.status === 404) {
                                // Schedule not found, just remove it from UI
                                modal.hide();
                                window.location.reload();
                                return { success: true };
                            }
                            return response.json().then(data => {
                                if (!response.ok) {
                                    throw new Error(data.error || `HTTP error! status: ${response.status}`);
                                }
                                return data;
                            });
                        })
                        .then(data => {
                            if (data.success) {
                                // Show success message and reload
                                const alertDiv = document.createElement('div');
                                alertDiv.className = 'alert alert-success alert-dismissible fade show';
                                alertDiv.innerHTML = `
                                    Schedule deleted successfully.
                                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                                `;
                                document.querySelector('.container').prepend(alertDiv);
                                
                                // Reload page after a short delay
                                setTimeout(() => {
                                window.location.reload();
                                }, 1000);
                            } else {
                                throw new Error(data.error || 'Failed to delete schedule');
                            }
                            modal.hide();
                        })
                        .catch(error => {
                            console.error('Error:', error);
                            
                            // Reset button state
                            confirmBtn.innerHTML = originalText;
                            confirmBtn.disabled = false;
                            
                            // Show error message
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-danger alert-dismissible fade show';
                            alertDiv.innerHTML = `
                                Error deleting schedule: ${error.message}
                                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                            `;
                            document.querySelector('.container').prepend(alertDiv);
                            modal.hide();
                        });
                    };
                    
                    modal.show();
                }
                
                function pauseSchedule(scheduleId) {
                    fetch(`/api/schedules/${scheduleId}/pause`, {
                        method: 'POST'
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            window.location.reload();
                        } else {
                            alert(`Failed to pause schedule: ${data.error}`);
                        }
                    })
                    .catch(error => {
                        alert(`Error: ${error.message}`);
                    });
                }
                
                function resumeSchedule(scheduleId) {
                    fetch(`/api/schedules/${scheduleId}/resume`, {
                        method: 'POST'
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            window.location.reload();
                        } else {
                            alert(`Failed to resume schedule: ${data.error}`);
                        }
                    })
                    .catch(error => {
                        alert(`Error: ${error.message}`);
                    });
                }
                
                function runScheduleNow(scheduleId) {
                    if (confirm('Are you sure you want to run this report now?')) {
                        fetch(`/api/schedules/${scheduleId}/run-now`, {
                            method: 'POST'
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                alert('Report scheduled to run now. Check your email shortly.');
                            } else {
                                alert(`Failed to run report: ${data.error}`);
                            }
                        })
                        .catch(error => {
                            alert(`Error: ${error.message}`);
                        });
                    }
                }
            </script>
        </body>
        </html>
    ''', schedules=schedules)

@app.route('/schedule-dataset/<dataset>', endpoint='schedule_dataset')
@login_required
def schedule_dataset(dataset):
    """Page to schedule a specific dataset"""
    # Get all timezones for the dropdown
    timezones = pytz.all_timezones
    
    # Get dataset columns for column selection
    dataset_columns = []
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            # Get a sample row to extract column names
            cursor.execute(f"SELECT * FROM '{dataset}' LIMIT 1")
            dataset_columns = [description[0] for description in cursor.description]
    except Exception as e:
        print(f"Error getting columns for dataset {dataset}: {str(e)}")
    # Add debugging for dataset columns
    print(f"Dataset: {dataset}")
    print(f"Dataset columns: {dataset_columns}")
    if not dataset_columns:
        print("WARNING: No columns found for dataset")

    
    # Get available email templates
    try:
        report_formatter_instance = ReportFormatter()
        email_template = report_formatter_instance.generate_email_content(report_title=f"Report for {dataset}")
    except Exception as e:
        print(f"Error generating email template: {str(e)}")
        email_template = {
            'subject': f"Report for {dataset}",
            'body': f"Please find the attached report for {dataset}.",
            'include_header': True
        }
    
    # Create a default schedule object with empty format_config
    default_schedule = {
        'format_config': {
            'page_size': 'a4',
            'orientation': 'portrait',
            'font_family': 'Arial, sans-serif',
            'font_size': 12,
            'line_height': 1.5,
            'include_header': True,
            'header_title': f'Report for {dataset}',
            'header_logo': '',
            'header_color': '#0d6efd',
            'header_alignment': 'center',
            'include_summary': True,
            'include_visualization': True,
            'max_rows': 1000
        }
        }
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Schedule Dataset - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
                .form-section {
                    border: 1px solid #ddd;
                    border-radius: 0.25rem;
                    padding: 1.5rem;
                    margin-bottom: 1.5rem;
                }
                .schedule-options {
                    display: none;
                }
                .schedule-options.active {
                    display: block;
                }
                .preview-card {
                    border: 1px solid #ddd;
                    border-radius: 0.25rem;
                    padding: 1rem;
                    background-color: #f8f9fa;
                }
                .recipient-tag {
                    display: inline-block;
                    background-color: #e9ecef;
                    padding: 0.25rem 0.5rem;
                    margin: 0.25rem;
                    border-radius: 0.25rem;
                }
                .recipient-tag .remove-btn {
                    margin-left: 0.5rem;
                    cursor: pointer;
                    color: #dc3545;
                }
                #emailPreview {
                    white-space: pre-wrap;
                    font-family: monospace;
                    background-color: #f8f9fa;
                    padding: 1rem;
                    border: 1px solid #ddd;
                    border-radius: 0.25rem;
                }
                .font-preview {
                    padding: 10px;
                    margin-bottom: 10px;
                    border: 1px solid #dee2e6;
                    border-radius: 4px;
                }
                .font-arial { font-family: Arial, sans-serif; }
                .font-times { font-family: 'Times New Roman', Times, serif; }
                .font-calibri { font-family: Calibri, 'Segoe UI', sans-serif; }
                .font-georgia { font-family: Georgia, serif; }
                .font-verdana { font-family: Verdana, Geneva, sans-serif; }
                .color-sample {
                    display: inline-block;
                    width: 20px;
                    height: 20px;
                    margin-right: 5px;
                    vertical-align: middle;
                    border: 1px solid #dee2e6;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h1><i class="bi bi-calendar-plus"></i> Schedule Dataset: {{ dataset }}</h1>
                    <a href="{{ url_for('home') }}" class="btn btn-outline-primary">← Back to Dashboard</a>
                </div>
                
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="alert alert-{{ category if category != 'message' else 'info' }}">{{ message }}</div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
                
                <form id="scheduleForm" method="post" action="{{ url_for('process_schedule_form') }}" enctype="multipart/form-data">
                    <input type="hidden" name="dataset_name" value="{{ dataset }}">
                    <input type="hidden" name="format_type" value="pdf">
                    
                    <div class="card mb-4">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="bi bi-clock"></i> Schedule Configuration</h5>
                        </div>
                        <div class="card-body">
                            <div class="mb-3">
                                <label for="scheduleType" class="form-label">Schedule Type</label>
                                <select class="form-select" id="scheduleType" name="schedule_type" required>
                                    <option value="one-time">One-time</option>
                                    <option value="daily">Daily</option>
                                    <option value="weekly">Weekly</option>
                                    <option value="monthly">Monthly</option>
                                </select>
                            </div>
                            
                            <!-- One-time schedule options -->
                            <div id="oneTimeOptions" class="schedule-options active">
                                <div class="mb-3">
                                    <label for="date" class="form-label">Date</label>
                                    <input type="date" class="form-control" id="date" name="date" data-required="one-time">
                                </div>
                            </div>
                            
                            <!-- Daily schedule options -->
                            <div id="dailyOptions" class="schedule-options">
                                <div class="mb-3">
                                    <p class="text-muted">Daily reports will be sent at the specified time every day.</p>
                                </div>
                            </div>
                            
                            <!-- Weekly schedule options -->
                            <div id="weeklyOptions" class="schedule-options">
                                <div class="mb-3">
                                    <label class="form-label">Days of Week</label>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" name="days" value="monday" id="monday">
                                        <label class="form-check-label" for="monday">Monday</label>
                                    </div>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" name="days" value="tuesday" id="tuesday">
                                        <label class="form-check-label" for="tuesday">Tuesday</label>
                                    </div>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" name="days" value="wednesday" id="wednesday">
                                        <label class="form-check-label" for="wednesday">Wednesday</label>
                                    </div>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" name="days" value="thursday" id="thursday">
                                        <label class="form-check-label" for="thursday">Thursday</label>
                                    </div>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" name="days" value="friday" id="friday">
                                        <label class="form-check-label" for="friday">Friday</label>
                                    </div>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" name="days" value="saturday" id="saturday">
                                        <label class="form-check-label" for="saturday">Saturday</label>
                                    </div>
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" name="days" value="sunday" id="sunday">
                                        <label class="form-check-label" for="sunday">Sunday</label>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- Monthly schedule options -->
                            <div id="monthlyOptions" class="schedule-options">
                                <div class="mb-3">
                                    <label class="form-label">Day of Month</label>
                                    <select class="form-select" name="day_option">
                                        <option value="Specific Day">Specific Day</option>
                                        <option value="First">First day of month</option>
                                        <option value="Last">Last day of month</option>
                                    </select>
                                </div>
                                <div class="mb-3" id="specificDayDiv">
                                    <label for="day" class="form-label">Day</label>
                                    <select class="form-select" id="day" name="day">
                                        {% for i in range(1, 32) %}
                                            <option value="{{ i }}">{{ i }}</option>
                                        {% endfor %}
                                    </select>
                                </div>
                            </div>
                            
                            <!-- Common time settings -->
                            <div class="row">
                                <div class="col-md-4">
                                    <div class="mb-3">
                                        <label for="hour" class="form-label">Hour</label>
                                        <select class="form-select" id="hour" name="hour" required>
                                            {% for i in range(24) %}
                                                <option value="{{ i }}">{{ '%02d'|format(i) }}</option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="mb-3">
                                        <label for="minute" class="form-label">Minute</label>
                                        <select class="form-select" id="minute" name="minute" required>
                                            {% for i in range(0, 60, 5) %}
                                                <option value="{{ i }}">{{ '%02d'|format(i) }}</option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                </div>
                                <div class="col-md-4">
                                    <div class="mb-3">
                                        <label for="timezone" class="form-label">Timezone</label>
                                        <select class="form-select" id="timezone" name="timezone" required>
                                            {% for tz in timezones %}
                                                <option value="{{ tz }}" {% if tz == 'UTC' %}selected{% endif %}>{{ tz }}</option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card mb-4">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="bi bi-file-earmark-pdf"></i> PDF Format Settings</h5>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-6">
                            <div class="mb-3">
                                        <label for="pageSize" class="form-label">Page Size</label>
                                        <select class="form-select" id="pageSize" name="page_size">
                                            <option value="a4" {% if default_schedule.format_config.page_size == 'a4' %}selected{% endif %}>A4</option>
                                            <option value="letter" {% if default_schedule.format_config.page_size == 'letter' %}selected{% endif %}>Letter</option>
                                            <option value="legal" {% if default_schedule.format_config.page_size == 'legal' %}selected{% endif %}>Legal</option>
                                            <option value="a3" {% if default_schedule.format_config.page_size == 'a3' %}selected{% endif %}>A3</option>
                                        </select>
                                </div>
                            </div>
                                <div class="col-md-6">
                            <div class="mb-3">
                                        <label for="orientation" class="form-label">Orientation</label>
                                        <select class="form-select" id="orientation" name="orientation">
                                            <option value="portrait" {% if default_schedule.format_config.orientation == 'portrait' %}selected{% endif %}>Portrait</option>
                                            <option value="landscape" {% if default_schedule.format_config.orientation == 'landscape' %}selected{% endif %}>Landscape</option>
                                        </select>
                                </div>
                            </div>
                            </div>
                            
                            <h6 class="mt-4 mb-3">Font Settings</h6>
                            <div class="row">
                                <div class="col-md-6">
                            <div class="mb-3">
                                        <label for="font_family" class="form-label">Font Family</label>
                                        <select class="form-select" id="font_family" name="font_family" onchange="updateFontPreview()">
                                            <option value="Arial, sans-serif" {% if default_schedule.format_config.font_family == 'Arial, sans-serif' %}selected{% endif %}>Arial</option>
                                            <option value="'Times New Roman', Times, serif" {% if default_schedule.format_config.font_family == "'Times New Roman', Times, serif" %}selected{% endif %}>Times New Roman</option>
                                            <option value="Calibri, 'Segoe UI', sans-serif" {% if default_schedule.format_config.font_family == "Calibri, 'Segoe UI', sans-serif" %}selected{% endif %}>Calibri</option>
                                            <option value="Georgia, serif" {% if default_schedule.format_config.font_family == 'Georgia, serif' %}selected{% endif %}>Georgia</option>
                                            <option value="Verdana, Geneva, sans-serif" {% if default_schedule.format_config.font_family == 'Verdana, Geneva, sans-serif' %}selected{% endif %}>Verdana</option>
                                        </select>
                            </div>
                            </div>
                                <div class="col-md-3">
                            <div class="mb-3">
                                        <label for="font_size" class="form-label">Font Size</label>
                                        <select class="form-select" id="font_size" name="font_size" onchange="updateFontPreview()">
                                            <option value="10" {% if default_schedule.format_config.font_size == 10 %}selected{% endif %}>10pt</option>
                                            <option value="11" {% if default_schedule.format_config.font_size == 11 %}selected{% endif %}>11pt</option>
                                            <option value="12" {% if default_schedule.format_config.font_size == 12 %}selected{% endif %}>12pt</option>
                                            <option value="14" {% if default_schedule.format_config.font_size == 14 %}selected{% endif %}>14pt</option>
                                            <option value="16" {% if default_schedule.format_config.font_size == 16 %}selected{% endif %}>16pt</option>
                                </select>
                            </div>
                                </div>
                                <div class="col-md-3">
                                <div class="mb-3">
                                        <label for="line_height" class="form-label">Line Height</label>
                                        <select class="form-select" id="line_height" name="line_height" onchange="updateFontPreview()">
                                            <option value="1.2" {% if default_schedule.format_config.line_height == 1.2 %}selected{% endif %}>Compact (1.2)</option>
                                            <option value="1.5" {% if default_schedule.format_config.line_height == 1.5 %}selected{% endif %}>Normal (1.5)</option>
                                            <option value="2.0" {% if default_schedule.format_config.line_height == 2.0 %}selected{% endif %}>Spacious (2.0)</option>
                                    </select>
                                </div>
                                </div>
                            </div>
                            
                                <div class="mb-3">
                                <label class="form-label">Font Preview</label>
                                <div id="fontPreview" class="font-preview">
                                    This is a preview of the selected font. The quick brown fox jumps over the lazy dog.
                                </div>
                            </div>
                            
                            <h6 class="mt-4 mb-3">Header Settings</h6>
                                <div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="include_header" name="include_header" {% if default_schedule.format_config.include_header %}checked{% endif %}>
                                <label class="form-check-label" for="include_header">
                                    Include Custom Header
                                    </label>
                            </div>
                            
                            <div id="headerSettings" style="{% if not default_schedule.format_config.include_header %}display: none;{% endif %}">
                                <div class="row">
                                    <div class="col-md-6">
                                <div class="mb-3">
                                            <label for="header_title" class="form-label">Header Title</label>
                                            <input type="text" class="form-control" id="header_title" name="header_title" value="{{ default_schedule.format_config.header_title }}">
                                </div>
                                    </div>
                                    <div class="col-md-6">
                                <div class="mb-3">
                                            <label for="header_logo" class="form-label">Logo (optional)</label>
                                            <input type="file" class="form-control" id="header_logo" name="header_logo" accept="image/png,image/jpeg">
                                            <div class="form-text">Supported formats: PNG, JPG (max 2MB, max dimensions 1500x1500px). Large images may cause PDF generation to fail.</div>
                                            {% if default_schedule.format_config.header_logo %}
                                                <div class="mt-2">
                                                    <small>Current logo: {{ default_schedule.format_config.header_logo }}</small>
                                                </div>
                                            {% endif %}
                                        </div>
                                </div>
                            </div>
                            
                                <div class="row">
                                    <div class="col-md-6">
                                <div class="mb-3">
                                            <label for="header_color" class="form-label">Header Color</label>
                                            <div class="input-group">
                                                <span class="input-group-text p-0">
                                                    <input type="color" class="form-control form-control-color" id="header_color" name="header_color" value="{{ default_schedule.format_config.header_color }}">
                                                </span>
                                                <select class="form-select" id="predefined_colors" onchange="updateHeaderColor(this.value)">
                                                    <option value="">Custom</option>
                                                    <option value="#0d6efd" {% if default_schedule.format_config.header_color == '#0d6efd' %}selected{% endif %}>Blue</option>
                                                    <option value="#198754" {% if default_schedule.format_config.header_color == '#198754' %}selected{% endif %}>Green</option>
                                                    <option value="#dc3545" {% if default_schedule.format_config.header_color == '#dc3545' %}selected{% endif %}>Red</option>
                                                    <option value="#6f42c1" {% if default_schedule.format_config.header_color == '#6f42c1' %}selected{% endif %}>Purple</option>
                                                    <option value="#fd7e14" {% if default_schedule.format_config.header_color == '#fd7e14' %}selected{% endif %}>Orange</option>
                                                    <option value="#212529" {% if default_schedule.format_config.header_color == '#212529' %}selected{% endif %}>Black</option>
                                                </select>
                                </div>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                <div class="mb-3">
                                            <label for="header_alignment" class="form-label">Header Alignment</label>
                                            <select class="form-select" id="header_alignment" name="header_alignment">
                                                <option value="left" {% if default_schedule.format_config.header_alignment == 'left' %}selected{% endif %}>Left</option>
                                                <option value="center" {% if default_schedule.format_config.header_alignment == 'center' %}selected{% endif %}>Center</option>
                                                <option value="right" {% if default_schedule.format_config.header_alignment == 'right' %}selected{% endif %}>Right</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    </div>
                            </div>
                            
                            <h6 class="mt-4 mb-3">Content Settings</h6>
                            <div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="includeSummary" name="include_summary" {% if default_schedule.format_config.include_summary %}checked{% endif %}>
                                <label class="form-check-label" for="includeSummary">
                                    Include Data Summary
                                </label>
                            </div>
                            
                            <div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="includeVisualization" name="include_visualization" {% if default_schedule.format_config.include_visualization %}checked{% endif %}>
                                <label class="form-check-label" for="includeVisualization">
                                    Include Visualization
                                </label>
                            </div>
                            
                            <div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="limitRows" name="limit_rows" {% if default_schedule.format_config.max_rows %}checked{% endif %}>
                                <label class="form-check-label" for="limitRows">
                                    Limit Number of Rows
                                </label>
                            </div>
                            
                            <div class="mb-3">
                                <label for="maxRows" class="form-label">Maximum Rows</label>
                                <input type="number" class="form-control" id="maxRows" name="max_rows" value="{{ default_schedule.format_config.max_rows if default_schedule.format_config.max_rows else 1000 }}" min="1">
                            </div>
                            
                            
                            
                            <!-- Column Selection -->
                            <div class="mb-3">
                                <label class="form-label">Column Selection</label>
                                <div class="form-check">
                                    <input class="form-check-input" type="checkbox" id="select_columns" name="select_columns">
                                    <label class="form-check-label" for="select_columns">
                                        Customize columns to include in report
                                    </label>
                                </div>
                                <div id="columnSelectionDiv" class="mt-2">
                                    <select class="form-select" id="selected_columns" name="selected_columns" multiple size="5">
                                        <!-- Directly show columns for Superstore dataset as fallback -->
                                        {% if dataset_columns %}
                                            {% for column in dataset_columns %}
                                                <option value="{{ column }}">{{ column }}</option>
                                            {% endfor %}
                                        {% else %}
                                            <!-- Fallback options for Superstore -->
                                            <option value="Measure Names">Measure Names</option>
                                            <option value="Region">Region</option>
                                            <option value="Profit Ratio">Profit Ratio</option>
                                            <option value="Sales per Customer">Sales per Customer</option>
                                            <option value="Distinct count of Customer Name">Distinct count of Customer Name</option>
                                            <option value="Measure Values">Measure Values</option>
                                            <option value="Profit">Profit</option>
                                            <option value="Quantity">Quantity</option>
                                            <option value="Sales">Sales</option>
                                        {% endif %}
                                    </select>
                                    <small class="form-text text-muted">
                                        Hold Ctrl (or Cmd on Mac) to select multiple columns. If none selected, all columns will be included.
                                    </small>
                                </div>
                            </div>
                            
                            <div class="form-check mb-3">
                                <input class="form-check-input" type="checkbox" id="limitRows" name="limit_rows" {% if default_schedule.format_config.max_rows %}checked{% endif %}>
                                <label class="form-check-label" for="limitRows">
                                    Limit Number of Rows
                                </label>
                            </div>
                            
                            <div class="mb-3">
                                <label for="maxRows" class="form-label">Maximum Rows</label>
                                <input type="number" class="form-control" id="maxRows" name="max_rows" value="{{ default_schedule.format_config.max_rows if default_schedule.format_config.max_rows else 1000 }}" min="1">
                            </div>
                        </div>
                    </div>
                    
                    <div class="card mb-4">
                        <div class="card-header">
                            <h5 class="mb-0"><i class="bi bi-send"></i> Delivery Options</h5>
                        </div>
                        <div class="card-body">
                            <!-- Email Delivery Tab -->
                            <div class="mb-4">
                                <h6><i class="bi bi-envelope"></i> Email Delivery</h6>
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="enable_email" name="enable_email" checked>
                                    <label class="form-check-label" for="enable_email">
                                        Send Report via Email
                                    </label>
                                </div>
                                
                                <div id="emailSettings">
                                    <div class="mb-3">
                                        <label for="recipients" class="form-label">Recipients (comma-separated)</label>
                                        <input type="text" class="form-control" name="recipients" placeholder="email1@example.com, email2@example.com">
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label for="cc" class="form-label">CC (comma-separated)</label>
                                        <input type="text" class="form-control" name="cc" placeholder="cc1@example.com, cc2@example.com">
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label for="subject" class="form-label">Subject</label>
                                        <input type="text" class="form-control" id="subject" name="subject" value="{{ email_template.subject }}">
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label for="body" class="form-label">Email Body</label>
                                        <textarea class="form-control" id="body" name="body" rows="6">{{ email_template.body }}</textarea>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- WhatsApp Delivery Tab -->
                            <div class="mt-4">
                                <h6><i class="bi bi-chat"></i> WhatsApp Delivery</h6>
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="enable_whatsapp" name="enable_whatsapp">
                                    <label class="form-check-label" for="enable_whatsapp">
                                        Send Report via WhatsApp
                                    </label>
                                </div>
                                
                                <div id="whatsappSettings" style="display: none;">
                                    <div class="alert alert-info">
                                        <i class="bi bi-info-circle"></i> Enter WhatsApp numbers with country code (e.g., +1234567890).
                                        Recipients must opt-in to receive messages. Separate multiple numbers with commas.
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label for="whatsapp_recipients" class="form-label">WhatsApp Recipients</label>
                                        <input type="text" class="form-control" name="whatsapp_recipients" placeholder="+1234567890, +0987654321">
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label for="whatsapp_message" class="form-label">Custom Message (optional)</label>
                                        <textarea class="form-control" id="whatsapp_message" name="whatsapp_message" rows="3" 
                                          placeholder="Optional custom message to include with the WhatsApp notification"></textarea>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="d-grid">
                        <button type="submit" class="btn btn-primary btn-lg">
                            <i class="bi bi-calendar-plus"></i> Create Schedule
                        </button>
                    </div>
                </form>
                
                <!-- Email Preview Modal -->
                <div class="modal fade" id="emailPreviewModal" tabindex="-1" aria-labelledby="emailPreviewModalLabel" aria-hidden="true">
                    <div class="modal-dialog modal-lg">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title" id="emailPreviewModalLabel">Email Preview</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <div class="mb-3">
                                    <strong>Subject:</strong> <span id="previewSubject">{{ email_template.subject }}</span>
                                </div>
                                <div class="mb-3">
                                    <strong>To:</strong> <span id="previewTo"></span>
                                </div>
                                <div class="mb-3">
                                    <strong>CC:</strong> <span id="previewCc"></span>
                                </div>
                                <hr>
                                <div id="emailPreview">{{ email_template.body }}</div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                document.addEventListener('DOMContentLoaded', function() {
                    // Schedule type selection
                    const scheduleType = document.getElementById('scheduleType');
                    const scheduleOptions = document.querySelectorAll('.schedule-options');
                    
                    scheduleType.addEventListener('change', function() {
                        scheduleOptions.forEach(option => option.classList.remove('active'));
                        
                        switch(this.value) {
                            case 'one-time':
                                document.getElementById('oneTimeOptions').classList.add('active');
                                break;
                            case 'daily':
                                document.getElementById('dailyOptions').classList.add('active');
                                break;
                            case 'weekly':
                                document.getElementById('weeklyOptions').classList.add('active');
                                break;
                            case 'monthly':
                                document.getElementById('monthlyOptions').classList.add('active');
                                break;
                        }
                    });
                    
                    // Monthly day option
                    const dayOption = document.querySelector('select[name="day_option"]');
                    const specificDayDiv = document.getElementById('specificDayDiv');
                    
                    dayOption.addEventListener('change', function() {
                        if (this.value === 'Specific Day') {
                            specificDayDiv.style.display = 'block';
                        } else {
                            specificDayDiv.style.display = 'none';
                        }
                    });
                    
                    // Email enable/disable
                    const enableEmail = document.getElementById('enable_email');
                    const emailSettings = document.getElementById('emailSettings');
                    
                    enableEmail.addEventListener('change', function() {
                        emailSettings.style.display = this.checked ? 'block' : 'none';
                    });
                    
                    // WhatsApp enable/disable
                    const enableWhatsapp = document.getElementById('enable_whatsapp');
                    const whatsappSettings = document.getElementById('whatsappSettings');
                    
                    enableWhatsapp.addEventListener('change', function() {
                        whatsappSettings.style.display = this.checked ? 'block' : 'none';
                    });
                    
                    // Recipients handling for email
                    const recipientInput = document.getElementById('recipientInput');
                    const addRecipientBtn = document.getElementById('addRecipientBtn');
                    const recipientTags = document.getElementById('recipientTags');
                    const recipientsContainer = document.getElementById('recipientsContainer');
                    
                    function addRecipients(input, tagsContainer, hiddenContainer, fieldName) {
                        const emails = input.value.split(',').map(email => email.trim()).filter(email => email);
                        
                        emails.forEach(email => {
                            if (!email) return;
                            
                            // Create tag
                            const tag = document.createElement('span');
                            tag.className = 'recipient-tag';
                            tag.innerHTML = `${email} <span class="remove-btn" data-email="${email}">&times;</span>`;
                            tagsContainer.appendChild(tag);
                            
                            // Create hidden input
                            const hiddenInput = document.createElement('input');
                            hiddenInput.type = 'hidden';
                            hiddenInput.name = fieldName;
                            hiddenInput.value = email;
                            hiddenContainer.appendChild(hiddenInput);
                            
                            // Add event listener to remove button
                            tag.querySelector('.remove-btn').addEventListener('click', function() {
                                const email = this.getAttribute('data-email');
                                this.parentNode.remove();
                                hiddenContainer.querySelectorAll(`input[value="${email}"]`).forEach(input => input.remove());
                                updateEmailPreview();
                            });
                        });
                        
                        input.value = '';
                        updateEmailPreview();
                    }
                    
                    addRecipientBtn.addEventListener('click', function() {
                        addRecipients(recipientInput, recipientTags, recipientsContainer, 'recipients');
                    });
                    
                    recipientInput.addEventListener('keydown', function(e) {
                        if (e.key === 'Enter' || e.key === 'Tab') {
                            e.preventDefault();
                            addRecipients(recipientInput, recipientTags, recipientsContainer, 'recipients');
                        }
                    });
                    
                    // CC handling for email
                    const ccInput = document.getElementById('ccInput');
                    const addCcBtn = document.getElementById('addCcBtn');
                    const ccTags = document.getElementById('ccTags');
                    const ccContainer = document.getElementById('ccContainer');
                    
                    addCcBtn.addEventListener('click', function() {
                        addRecipients(ccInput, ccTags, ccContainer, 'cc');
                    });
                    
                    ccInput.addEventListener('keydown', function(e) {
                        if (e.key === 'Enter' || e.key === 'Tab') {
                            e.preventDefault();
                            addRecipients(ccInput, ccTags, ccContainer, 'cc');
                        }
                    });
                    
                    // WhatsApp recipients handling
                    const whatsappInput = document.getElementById('whatsappInput');
                    const addWhatsappBtn = document.getElementById('addWhatsappBtn');
                    const whatsappTags = document.getElementById('whatsappTags');
                    const whatsappContainer = document.getElementById('whatsappContainer');
                    
                    addWhatsappBtn.addEventListener('click', function() {
                        addRecipients(whatsappInput, whatsappTags, whatsappContainer, 'whatsapp_recipients');
                    });
                    
                    whatsappInput.addEventListener('keydown', function(e) {
                        if (e.key === 'Enter' || e.key === 'Tab') {
                            e.preventDefault();
                            addRecipients(whatsappInput, whatsappTags, whatsappContainer, 'whatsapp_recipients');
                        }
                    });
                    
                    // Email preview
                    const subject = document.getElementById('subject');
                    const body = document.getElementById('body');
                    const previewSubject = document.getElementById('previewSubject');
                    const previewTo = document.getElementById('previewTo');
                    const previewCc = document.getElementById('previewCc');
                    const emailPreview = document.getElementById('emailPreview');
                    
                    function updateEmailPreview() {
                        previewSubject.textContent = subject.value;
                        
                        // Get recipients
                        const recipients = Array.from(recipientsContainer.querySelectorAll('input'))
                            .map(input => input.value);
                        previewTo.textContent = recipients.join(', ') || 'No recipients added';
                        
                        // Get CCs
                        const ccs = Array.from(ccContainer.querySelectorAll('input'))
                            .map(input => input.value);
                        previewCc.textContent = ccs.join(', ') || 'None';
                        
                        // Set body
                        emailPreview.textContent = body.value;
                    }
                    
                    subject.addEventListener('input', updateEmailPreview);
                    body.addEventListener('input', updateEmailPreview);
                    
                    // Font preview
                    updateFontPreview();
                    
                    // Include header toggle
                    const includeHeader = document.getElementById('include_header');
                    const headerSettings = document.getElementById('headerSettings');
                    
                    includeHeader.addEventListener('change', function() {
                        headerSettings.style.display = this.checked ? 'block' : 'none';
                    });
                    
                    // Initialize the preview
                    updateEmailPreview();
                    
                    // Form validation
                    document.getElementById('scheduleForm').addEventListener('submit', function(e) {
                        const enableEmail = document.getElementById('enable_email').checked;
                        const enableWhatsapp = document.getElementById('enable_whatsapp').checked;
                        
                        // Validate that at least one delivery method is enabled
                        if (!enableEmail && !enableWhatsapp) {
                            e.preventDefault();
                            alert('Please enable at least one delivery method (Email or WhatsApp)');
                            return false;
                        }
                        
                        // Validate email recipients if email is enabled
                        if (enableEmail) {
                        const recipients = recipientsContainer.querySelectorAll('input');
                        if (recipients.length === 0) {
                            e.preventDefault();
                                alert('Please add at least one email recipient');
                            return false;
                            }
                        }
                        
                        // Validate WhatsApp recipients if WhatsApp is enabled
                        if (enableWhatsapp) {
                            const whatsappRecipients = whatsappContainer.querySelectorAll('input');
                            if (whatsappRecipients.length === 0) {
                                e.preventDefault();
                                alert('Please add at least one WhatsApp recipient');
                                return false;
                            }
                        }
                        
                        // Validate based on schedule type
                        const scheduleTypeValue = scheduleType.value;
                        
                        // For one-time schedules, validate date
                        if (scheduleTypeValue === 'one-time') {
                            const dateField = document.getElementById('date');
                            if (!dateField.value) {
                                e.preventDefault();
                                alert('Please select a date for the one-time schedule');
                                return false;
                            }
                        }
                        
                        // For weekly schedules, validate days
                        if (scheduleTypeValue === 'weekly') {
                            const days = document.querySelectorAll('input[name="days"]:checked');
                            if (days.length === 0) {
                                e.preventDefault();
                                alert('Please select at least one day of the week');
                                return false;
                            }
                        }
                        
                        // For monthly schedules, validate day selection
                        if (scheduleTypeValue === 'monthly') {
                            const dayOption = document.querySelector('select[name="day_option"]');
                            if (dayOption.value === 'Specific Day') {
                                const day = document.getElementById('day');
                                if (!day.value) {
                                    e.preventDefault();
                                    alert('Please select a specific day of the month');
                                    return false;
                                }
                            }
                        }
                        
                        return true;
                    });
                });
                
                // Font preview function
                function updateFontPreview() {
                    const fontFamily = document.getElementById('font_family').value;
                    const fontSize = document.getElementById('font_size').value;
                    const lineHeight = document.getElementById('line_height').value;
                    
                    const fontPreview = document.getElementById('fontPreview');
                    fontPreview.style.fontFamily = fontFamily;
                    fontPreview.style.fontSize = fontSize + 'pt';
                    fontPreview.style.lineHeight = lineHeight;
                }
                
                // Update header color from predefined colors
                function updateHeaderColor(color) {
                    if (color) {
                        document.getElementById('header_color').value = color;
                    }
                }
                
                // Handle header checkbox
                const includeHeader = document.getElementById('include_header');
                const headerSettings = document.getElementById('headerSettings');
                
                includeHeader.addEventListener('change', function() {
                    headerSettings.style.display = this.checked ? 'block' : 'none';
                });
                
                // Handle column selection checkbox
                const selectColumns = document.getElementById('select_columns');
                const columnSelectionDiv = document.getElementById('columnSelectionDiv');
                
                selectColumns.addEventListener('change', function() {
                    columnSelectionDiv.style.display = this.checked ? 'block' : 'none';
                });
                
                // Initialize the preview
                updateEmailPreview();
            </script>
        </body>
        </html>
    ''', dataset=dataset, timezones=timezones, email_template=email_template, default_schedule=default_schedule)

# Helper function to convert numpy types to Python standard types
def convert_numpy_types(obj, depth=0, max_depth=20):
    """Convert numpy types to Python standard types with recursion protection"""
    import numpy as np
    
    # Guard against excessive recursion
    if depth > max_depth:
        return str(obj)
    
    # Handle None values explicitly
    if obj is None:
        return None
        
    # Handle basic types
    if isinstance(obj, (str, int, float, bool)):
        return obj
    
    # Handle numpy types
    try:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
    except Exception as numpy_error:
        print(f"Error converting NumPy type: {str(numpy_error)}")
        return str(obj)
    
    # Handle container types
    if isinstance(obj, dict):
        try:
            return {str(key): convert_numpy_types(value, depth + 1, max_depth) 
                    for key, value in obj.items() 
                    if not str(key).startswith('_') and value is not None}
        except Exception as dict_error:
            print(f"Error converting dict: {str(dict_error)}")
            return str(obj)
            
    if isinstance(obj, (list, tuple)):
        try:
            return [convert_numpy_types(item, depth + 1, max_depth) 
                    for item in obj if item is not None]
        except Exception as list_error:
            print(f"Error converting list/tuple: {str(list_error)}")
            return str(obj)
    
    # Handle objects with conversion methods
    if hasattr(obj, 'to_dict') and callable(obj.to_dict):
        try:
            return convert_numpy_types(obj.to_dict(), depth + 1, max_depth)
        except Exception as e:
            print(f"Failed to convert using to_dict: {str(e)}")
    
    # Handle generic objects
    if hasattr(obj, '__dict__'):
        try:
            # Only include non-callable, non-private attributes
            attrs = {k: v for k, v in obj.__dict__.items() 
                    if not k.startswith('_') and not callable(v) and v is not None}
            return {k: convert_numpy_types(v, depth + 1, max_depth) for k, v in attrs.items()}
        except Exception as e:
            print(f"Failed to convert using __dict__: {str(e)}")
    
    # If all else fails, convert to a string
    return str(obj)

# Helper function to convert traces to dictionaries, handling special types like Histogram and Cumulative
def convert_trace_to_dict(trace, depth=0, max_depth=10):
    """Convert trace objects to dictionaries with recursion protection"""
    # Guard against excessive recursion
    if depth > max_depth:
        return {"type": str(type(trace).__name__), "info": "Max recursion depth reached"}
    
    # Handle None values
    if trace is None:
        return None
    
    # Check if it's a streamlit object and skip conversion
    trace_type = str(type(trace).__name__)
    if "streamlit" in trace_type.lower() or "st." in str(trace):
        return {"type": trace_type, "info": "Streamlit object (not convertible)"}
    
    try:
        # If trace is already a dict, use it directly but filter out private members
        if isinstance(trace, dict):
            return {str(k): convert_numpy_types(v, depth + 1, max_depth) 
                    for k, v in trace.items() 
                    if not str(k).startswith('_')}
        
        # Check the type name to handle special cases
        type_name = type(trace).__name__
        
        # Special handling for certain Plotly types
        if type_name in ['Histogram', 'Bar', 'Scatter', 'Line', 'Cumulative', 'Pie', 'Heatmap']:
            # Create a simplified representation for known visualization types
            result = {'type': type_name}
            
            # Add common attributes based on the type
            safe_attrs = ['x', 'y', 'z', 'name', 'orientation', 'direction', 'enabled', 
                          'visible', 'showlegend', 'mode', 'marker', 'line']
            
            for attr in safe_attrs:
                if hasattr(trace, attr):
                    try:
                        val = getattr(trace, attr)
                        if val is not None:  # Explicitly check for None
                            result[attr] = convert_numpy_types(val, depth + 1, max_depth)
                    except Exception as attr_error:
                        print(f"Error getting attr {attr}: {str(attr_error)}")
            
            return result
        
        # For all other traces, try standard conversion methods
        if hasattr(trace, 'to_dict') and callable(trace.to_dict):
            try:
                trace_dict = trace.to_dict()
                if isinstance(trace_dict, dict):  # Ensure it's a dictionary
                    return {str(k): convert_numpy_types(v, depth + 1, max_depth) 
                            for k, v in trace_dict.items() 
                            if not str(k).startswith('_') and v is not None}
                else:
                    return {"type": type_name, "data": str(trace_dict)}
            except Exception as e:
                print(f"Failed to use to_dict method: {str(e)}")
        
        # If to_dict fails, try extracting attributes directly
        attrs = {}
        for attr in dir(trace):
            if not attr.startswith('_') and not callable(getattr(trace, attr, None)):
                try:
                    value = getattr(trace, attr)
                    # Skip problematic properties
                    if (not callable(value) and 
                        attr not in ['layout', 'figure', 'parent', '_grid_str', 'st'] and
                        value is not None):
                        attrs[attr] = convert_numpy_types(value, depth + 1, max_depth)
                except Exception as e:
                    # Skip attributes that cannot be accessed
                    pass
        
        # If we got attributes, return them, otherwise return a simple type indicator
        if attrs:
            return attrs
        else:
            return {"type": type_name}
        
    except Exception as e:
        print(f"Error converting trace to dict: {str(e)}")
        # Return a minimal representation if conversion fails
        return {"type": str(type(trace).__name__)}

@app.route('/api/datasets/<dataset>/preview', methods=['GET'])
@login_required
def get_dataset_preview_api(dataset):
    """API endpoint to get HTML preview of a dataset"""
    try:
        preview_html = get_dataset_preview_html(dataset)
        return preview_html
    except Exception as e:
        print(f"Error getting dataset preview: {str(e)}")
        return "<div class='alert alert-danger'>Error loading preview: " + str(e) + "</div>"

@app.route('/api/datasets/<dataset>', methods=['DELETE'])
@login_required
def delete_dataset_api(dataset):
    """API endpoint to delete a dataset"""
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            
            # Verify the table exists before trying to delete
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name=?
            """, (dataset,))
            
            if not cursor.fetchone():
                return jsonify({'success': False, 'error': 'Dataset not found'})
            
            # Delete the table
            cursor.execute(f"DROP TABLE '{dataset}'")
            
            # Also remove from internal tracking table if it exists
            try:
                cursor.execute("""
                    DELETE FROM _internal_tableau_connections 
                    WHERE dataset_name=?
                """, (dataset,))
            except sqlite3.OperationalError:
                # Table might not exist
                pass
                
            conn.commit()
            
            return jsonify({'success': True})
    except Exception as e:
        print(f"Error deleting dataset: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# Define a function to verify superadmin directly from the database
def verify_superadmin(username, password):
    """Directly verify superadmin credentials from the database"""
    if username != 'superadmin':
        return None
    
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            
            # Check if superadmin exists
            cursor.execute("SELECT rowid, username, role, permission_type, organization_id FROM users WHERE username = 'superadmin'")
            user_data = cursor.fetchone()
            
            if not user_data:
                print("Superadmin user not found in database")
                return None
            
            # Get password column name
            cursor.execute("PRAGMA table_info(users)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            password_column = None
            for col in ['password_hash', 'password']:
                if col in column_names:
                    password_column = col
                    break
            
            if not password_column:
                print("Could not find password column in users table")
                return None
            
            # Get password hash
            cursor.execute(f"SELECT {password_column} FROM users WHERE username = 'superadmin'")
            password_hash = cursor.fetchone()[0]
            
            # Verify password
            if check_password_hash(password_hash, password):
                print("Superadmin password verified successfully")
                # Create a user object that's compatible with the session expectations
                return (
                    user_data[0],  # id
                    user_data[1],  # username
                    user_data[2],  # role
                    user_data[3],  # permission_type
                    user_data[4],  # organization_id
                    None           # organization_name
                )
            else:
                print("Superadmin password verification failed")
                return None
    except Exception as e:
        print(f"Error during direct superadmin verification: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

@app.route('/admin-dashboard')
@login_required
@role_required(['superadmin'])
def admin_dashboard():
    # Admin dashboard page with user management
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            # Get all users
            cursor.execute("""
                SELECT u.rowid, u.username, u.email, u.role, u.permission_type, 
                       o.name as organization_name
                FROM users u
                LEFT JOIN organizations o ON u.organization_id = o.rowid
            """)
            users = []
            for row in cursor.fetchall():
                users.append({
                    'id': row[0],
                    'username': row[1],
                    'email': row[2] or '',
                    'role': row[3],
                    'permission_type': row[4],
                    'organization_name': row[5] or 'None'
                })
            
            # Get organizations for dropdown
            cursor.execute("SELECT rowid, name FROM organizations")
            organizations = []
            for row in cursor.fetchall():
                organizations.append({
                    'id': row[0],
                    'name': row[1]
                })
        
        # Simplified admin dashboard template
        admin_template = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Dashboard - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                .sidebar {
                    position: fixed;
                    top: 0;
                    bottom: 0;
                    left: 0;
                    z-index: 100;
                    padding: 48px 0 0;
                    box-shadow: inset -1px 0 0 rgba(0, 0, 0, .1);
                }
                .main {
                    margin-left: 240px;
                    padding: 20px;
                }
            </style>
        </head>
        <body>
            <nav class="col-md-3 col-lg-2 d-md-block bg-light sidebar">
                <div class="position-sticky pt-3">
                    <div class="px-3">
                        <h5>👤 Admin Profile</h5>
                        <p><strong>Username:</strong> {{ session.user.username }}</p>
                        <p><strong>Role:</strong> {{ session.user.role }}</p>
                    </div>
                    <hr>
                    <div class="px-3">
                        <a href="{{ url_for('admin_dashboard') }}" class="btn btn-primary w-100 mb-2">👥 Users</a>
                        <a href="{{ url_for('admin_organizations') }}" class="btn btn-primary w-100 mb-2">🏢 Organizations</a>
                        <a href="{{ url_for('admin_system') }}" class="btn btn-primary w-100 mb-2">⚙️ System</a>
                        <hr>
                        <a href="{{ url_for('logout') }}" class="btn btn-secondary w-100">🚪 Logout</a>
                    </div>
                </div>
            </nav>
            
            <main class="main">
                <div class="container-fluid">
                    {% with messages = get_flashed_messages() %}
                        {% if messages %}
                            {% for message in messages %}
                                <div class="alert alert-info">{{ message }}</div>
                            {% endfor %}
                        {% endif %}
                    {% endwith %}
                
                    <h1>👥 User Management</h1>
                    
                    <div class="card mb-4">
                        <div class="card-body">
                            <h5>Add New User</h5>
                            <form id="addUserForm">
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Username</label>
                                            <input type="text" class="form-control" name="username" required>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Email</label>
                                            <input type="email" class="form-control" name="email" required>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Password</label>
                                            <input type="password" class="form-control" name="password" required>
                                        </div>
                                    </div>
                                </div>
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Permission Type</label>
                                            <select class="form-select" name="permission_type" required>
                                                <option value="normal">Normal User</option>
                                                <option value="power">Power User</option>
                                                <option value="superadmin">Superadmin</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Organization</label>
                                            <select class="form-select" name="organization_id">
                                                <option value="">None</option>
                                                {% for org in organizations %}
                                                    <option value="{{ org.id }}">{{ org.name }}</option>
                                                {% endfor %}
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">&nbsp;</label>
                                            <button type="submit" class="btn btn-primary w-100">Create User</button>
                                        </div>
                                    </div>
                                </div>
                            </form>
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="card-body">
                            <h5>Existing Users</h5>
                            <div class="table-responsive">
                                <table class="table table-hover">
                                    <thead>
                                        <tr>
                                            <th>ID</th>
                                            <th>Username</th>
                                            <th>Email</th>
                                            <th>Role</th>
                                            <th>Permission Type</th>
                                            <th>Organization</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for user in users %}
                                            <tr>
                                                <td>{{ user.id }}</td>
                                                <td>{{ user.username }}</td>
                                                <td>{{ user.email }}</td>
                                                <td>{{ user.role }}</td>
                                                <td>{{ user.permission_type }}</td>
                                                <td>{{ user.organization_name }}</td>
                                                <td>
                                                    <div class="btn-group btn-group-sm">
                                                        <button class="btn btn-outline-primary"
                                                                onclick="editUser('{{ user.id }}')">
                                                            ✏️ Edit
                                                        </button>
                                                        <button class="btn btn-outline-danger"
                                                                onclick="deleteUser('{{ user.id }}')">
                                                            🗑️ Delete
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        {% endfor %}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            </main>

            <!-- Edit User Modal -->
            <div class="modal fade" id="editUserModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Edit User</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="editUserForm">
                                <input type="hidden" id="editUserId" name="id">
                                <div class="mb-3">
                                    <label class="form-label">Username</label>
                                    <input type="text" class="form-control" id="editUsername" name="username" required>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Email</label>
                                    <input type="email" class="form-control" id="editEmail" name="email" required>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">New Password (leave blank to keep current)</label>
                                    <input type="password" class="form-control" id="editPassword" name="password">
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Permission Type</label>
                                    <select class="form-select" id="editPermissionType" name="permission_type" required>
                                        <option value="normal">Normal User</option>
                                        <option value="power">Power User</option>
                                        <option value="superadmin">Superadmin</option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Organization</label>
                                    <select class="form-select" id="editOrganizationId" name="organization_id">
                                        <option value="">None</option>
                                        {% for org in organizations %}
                                            <option value="{{ org.id }}">{{ org.name }}</option>
                                        {% endfor %}
                                    </select>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-primary" onclick="saveUserChanges()">Save Changes</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Delete User Modal -->
            <div class="modal fade" id="deleteUserModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Delete User</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <p>Are you sure you want to delete this user? This action cannot be undone.</p>
                            <input type="hidden" id="deleteUserId">
                            <p><strong>Username: </strong><span id="deleteUsername"></span></p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-danger" onclick="confirmDeleteUser()">Delete User</button>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <script>
                // Add User Form Submit
                document.getElementById('addUserForm').addEventListener('submit', function(e) {
                    e.preventDefault();
                    alert('User management functionality is not implemented in this demo');
                });
                
                // Edit User Modal
                async function editUser(userId) {
                    try {
                        // Fetch user details
                        const response = await fetch(`/api/users/${userId}`);
                        const data = await response.json();
                        
                        if (data.success) {
                            const user = data.user;
                            
                            // Populate the edit form
                            document.getElementById('editUserId').value = user.id;
                            document.getElementById('editUsername').value = user.username;
                            document.getElementById('editEmail').value = user.email;
                            document.getElementById('editPassword').value = ''; // Clear password field
                            document.getElementById('editPermissionType').value = user.role;
                            document.getElementById('editOrganizationId').value = user.organization_id || '';
                            
                            // Show the modal
                            const modal = new bootstrap.Modal(document.getElementById('editUserModal'));
                            modal.show();
                        } else {
                            alert('Failed to load user details: ' + data.error);
                        }
                    } catch (error) {
                        console.error('Error:', error);
                        alert('Failed to load user details');
                    }
                }
                
                // Save User Changes
                async function saveUserChanges() {
                    const userId = document.getElementById('editUserId').value;
                    const formData = {
                        username: document.getElementById('editUsername').value,
                        email: document.getElementById('editEmail').value,
                        password: document.getElementById('editPassword').value,
                        permission_type: document.getElementById('editPermissionType').value,
                        organization_id: document.getElementById('editOrganizationId').value
                    };
                    
                    try {
                        const response = await fetch(`/api/users/${userId}`, {
                            method: 'PUT',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(formData)
                        });
                        
                        const data = await response.json();
                        
                        if (data.success) {
                            // Hide modal
                            bootstrap.Modal.getInstance(document.getElementById('editUserModal')).hide();
                            
                            // Show success message and reload page
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-success alert-dismissible fade show';
                            alertDiv.innerHTML = `
                                User updated successfully.
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            `;
                            document.querySelector('.container-fluid').prepend(alertDiv);
                            
                            // Reload page after a short delay
                            setTimeout(() => {
                                window.location.reload();
                            }, 1000);
                        } else {
                            alert('Failed to update user: ' + data.error);
                        }
                    } catch (error) {
                        console.error('Error:', error);
                        alert('Failed to update user');
                    }
                }
                
                // Delete User
                function deleteUser(userId) {
                    // Get user details from the table row
                    const row = document.querySelector(`tr td:first-child:contains('${userId}')`).parentElement;
                    const username = row.cells[1].textContent;
                    
                    // Set values in the delete modal
                    document.getElementById('deleteUserId').value = userId;
                    document.getElementById('deleteUsername').textContent = username;
                    
                    // Show the modal
                    const modal = new bootstrap.Modal(document.getElementById('deleteUserModal'));
                    modal.show();
                }
                
                // Confirm Delete User
                async function confirmDeleteUser() {
                    const userId = document.getElementById('deleteUserId').value;
                    
                    try {
                        const response = await fetch(`/api/users/${userId}`, {
                            method: 'DELETE'
                        });
                        
                        const data = await response.json();
                        
                        if (data.success) {
                            // Hide modal
                            bootstrap.Modal.getInstance(document.getElementById('deleteUserModal')).hide();
                            
                            // Show success message and reload page
                            const alertDiv = document.createElement('div');
                            alertDiv.className = 'alert alert-success alert-dismissible fade show';
                            alertDiv.innerHTML = `
                                User deleted successfully.
                                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                            `;
                            document.querySelector('.container-fluid').prepend(alertDiv);
                            
                            // Reload page after a short delay
                            setTimeout(() => {
                                window.location.reload();
                            }, 1000);
                        } else {
                            alert('Failed to delete user: ' + data.error);
                        }
                    } catch (error) {
                        console.error('Error:', error);
                        alert('Failed to delete user');
                    }
                }
            </script>
        </body>
        </html>
        '''
        
        return render_template_string(admin_template, users=users, organizations=organizations)
        
    except Exception as e:
        print(f"Error in admin_dashboard function: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        flash(f'Error loading admin dashboard: {str(e)}')
        return render_template_string('''
            <div class="alert alert-danger">
                <h4>Error loading admin dashboard</h4>
                <p>{{ error }}</p>
                <a href="{{ url_for('home') }}" class="btn btn-primary">Return to Home</a>
            </div>
        ''', error=str(e))

# Schedule management API endpoints
@app.route('/api/schedules/<schedule_id>', methods=['DELETE'])
@login_required
def delete_schedule_api(schedule_id):
    """Delete a schedule"""
    try:
        report_manager = ReportManager()
        # First check if schedule exists
        schedule = report_manager.get_schedule(schedule_id)
        if not schedule:
            return jsonify({
                'success': False,
                'error': 'Schedule not found'
            }), 404
            
        # Try to remove the schedule
        if report_manager.remove_schedule(schedule_id):
            return jsonify({
                'success': True,
                'message': 'Schedule deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete schedule. Please try again.'
            }), 500
    except Exception as e:
        print(f"Error deleting schedule: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/api/schedules/<schedule_id>/pause', methods=['POST'])
@login_required
def pause_schedule_api(schedule_id):
    """API endpoint to pause a schedule"""
    try:
        success = report_manager.pause_schedule(schedule_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to pause schedule'})
    except Exception as e:
        print(f"Error pausing schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/schedules/<schedule_id>/resume', methods=['POST'])
@login_required
def resume_schedule_api(schedule_id):
    """API endpoint to resume a schedule"""
    try:
        success = report_manager.resume_schedule(schedule_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to resume schedule'})
    except Exception as e:
        print(f"Error resuming schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/schedules/<schedule_id>/run-now', methods=['POST'])
@login_required
def run_schedule_now_api(schedule_id):
    """API endpoint to run a schedule immediately"""
    try:
        job_id = report_manager.run_schedule_now(schedule_id)
        if job_id:
            return jsonify({'success': True, 'job_id': job_id})
        else:
            return jsonify({'success': False, 'error': 'Failed to run schedule'})
    except Exception as e:
        print(f"Error running schedule: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/edit-schedule/<schedule_id>', methods=['GET'])
@login_required
def edit_schedule(schedule_id):
    """Page to edit an existing schedule"""
    try:
        if not schedule_id:
            flash('Schedule ID is required', 'error')
            return redirect(url_for('manage_schedules'))
            
        # First check if schedule exists in database
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM schedules WHERE id = ? AND status != 'deleted'", (schedule_id,))
            if not cursor.fetchone():
                flash(f'Schedule with ID {schedule_id} not found', 'error')
                return redirect(url_for('manage_schedules'))
            
        # Get the schedule from the report manager
        schedule = report_manager.get_schedule(schedule_id)
        
        if not schedule:
            flash('Schedule not found or has been deleted', 'error')
            return redirect(url_for('manage_schedules'))
        
        # Get all timezones for the dropdown
        timezones = pytz.all_timezones
        
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Edit Schedule - Tableau Data Reporter</title>
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
                <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css" rel="stylesheet">
                <style>
                    body { padding: 20px; }
                    .schedule-options {
                        display: none;
                    }
                    .schedule-options.active {
                        display: block;
                    }
                    .format-options {
                        display: none;
                    }
                    .format-options.active {
                        display: block;
                    }
                    .recipient-tag {
                        display: inline-block;
                        background-color: #e9ecef;
                        padding: 0.25rem 0.5rem;
                        margin: 0.25rem;
                        border-radius: 0.25rem;
                    }
                    .recipient-tag .remove-btn {
                        margin-left: 0.5rem;
                        cursor: pointer;
                        color: #dc3545;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="d-flex justify-content-between align-items-center mb-4">
                        <h1><i class="bi bi-calendar-check"></i> Edit Schedule</h1>
                        <a href="{{ url_for('manage_schedules') }}" class="btn btn-outline-primary">← Back to Schedules</a>
                    </div>
                    
                    <form id="editScheduleForm" method="post" action="{{ url_for('update_schedule', schedule_id=schedule.id) }}">
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="bi bi-info-circle"></i> Schedule Details</h5>
                            </div>
                            <div class="card-body">
                                <div class="mb-3">
                                    <label class="form-label">Dataset</label>
                                    <input type="text" class="form-control" value="{{ schedule.dataset_name }}" readonly>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="scheduleType" class="form-label">Schedule Type</label>
                                    <select class="form-select" id="scheduleType" name="schedule_type" required>
                                        <option value="one-time" {% if schedule.schedule_type == 'one-time' %}selected{% endif %}>One-time</option>
                                        <option value="daily" {% if schedule.schedule_type == 'daily' %}selected{% endif %}>Daily</option>
                                        <option value="weekly" {% if schedule.schedule_type == 'weekly' %}selected{% endif %}>Weekly</option>
                                        <option value="monthly" {% if schedule.schedule_type == 'monthly' %}selected{% endif %}>Monthly</option>
                                    </select>
                                </div>
                                
                                <!-- Schedule type options -->
                                <!-- One-time schedule options -->
                                <div id="oneTimeOptions" class="schedule-options {% if schedule.schedule_type == 'one-time' %}active{% endif %}">
                                    <div class="mb-3">
                                        <label for="date" class="form-label">Date</label>
                                        <input type="date" class="form-control" id="date" name="date" 
                                               value="{{ schedule.date if schedule.date else '' }}">
                                    </div>
                                </div>
                                
                                <!-- Weekly schedule options -->
                                <div id="weeklyOptions" class="schedule-options {% if schedule.schedule_type == 'weekly' %}active{% endif %}">
                                    <div class="mb-3">
                                        <label class="form-label">Days of Week</label>
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="days" value="monday" id="monday"
                                                   {% if schedule.days and 'monday' in schedule.days %}checked{% endif %}>
                                            <label class="form-check-label" for="monday">Monday</label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="days" value="tuesday" id="tuesday"
                                                   {% if schedule.days and 'tuesday' in schedule.days %}checked{% endif %}>
                                            <label class="form-check-label" for="tuesday">Tuesday</label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="days" value="wednesday" id="wednesday"
                                                   {% if schedule.days and 'wednesday' in schedule.days %}checked{% endif %}>
                                            <label class="form-check-label" for="wednesday">Wednesday</label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="days" value="thursday" id="thursday"
                                                   {% if schedule.days and 'thursday' in schedule.days %}checked{% endif %}>
                                            <label class="form-check-label" for="thursday">Thursday</label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="days" value="friday" id="friday"
                                                   {% if schedule.days and 'friday' in schedule.days %}checked{% endif %}>
                                            <label class="form-check-label" for="friday">Friday</label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="days" value="saturday" id="saturday"
                                                   {% if schedule.days and 'saturday' in schedule.days %}checked{% endif %}>
                                            <label class="form-check-label" for="saturday">Saturday</label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="checkbox" name="days" value="sunday" id="sunday"
                                                   {% if schedule.days and 'sunday' in schedule.days %}checked{% endif %}>
                                            <label class="form-check-label" for="sunday">Sunday</label>
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- Monthly schedule options -->
                                <div id="monthlyOptions" class="schedule-options {% if schedule.schedule_type == 'monthly' %}active{% endif %}">
                                    <div class="mb-3">
                                        <label class="form-label">Day of Month</label>
                                        <select class="form-select" name="day_option" id="dayOption">
                                            <option value="Specific Day" {% if schedule.day_option == 'Specific Day' %}selected{% endif %}>Specific Day</option>
                                            <option value="First" {% if schedule.day_option == 'First' %}selected{% endif %}>First day of month</option>
                                            <option value="Last" {% if schedule.day_option == 'Last' %}selected{% endif %}>Last day of month</option>
                                        </select>
                                    </div>
                                    <div class="mb-3" id="specificDayDiv" style="{% if schedule.day_option != 'Specific Day' %}display: none;{% endif %}">
                                        <label for="day" class="form-label">Day</label>
                                        <select class="form-select" id="day" name="day">
                                            {% for i in range(1, 32) %}
                                                <option value="{{ i }}" {% if schedule.day == i %}selected{% endif %}>{{ i }}</option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                </div>
                                
                                <!-- Common time settings -->
                                <div class="row">
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label for="hour" class="form-label">Hour</label>
                                            <select class="form-select" id="hour" name="hour" required>
                                                {% for i in range(24) %}
                                                    <option value="{{ i }}" {% if schedule.hour == i %}selected{% endif %}>{{ '%02d'|format(i) }}</option>
                                                {% endfor %}
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label for="minute" class="form-label">Minute</label>
                                            <select class="form-select" id="minute" name="minute" required>
                                                {% for i in range(0, 60, 5) %}
                                                    <option value="{{ i }}" {% if schedule.minute == i %}selected{% endif %}>{{ '%02d'|format(i) }}</option>
                                                {% endfor %}
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label for="timezone" class="form-label">Timezone</label>
                                            <select class="form-select" id="timezone" name="timezone" required>
                                                {% for tz in timezones %}
                                                    <option value="{{ tz }}" {% if schedule.timezone == tz %}selected{% endif %}>{{ tz }}</option>
                                                {% endfor %}
                                            </select>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="bi bi-file-earmark-pdf"></i> PDF Format Settings</h5>
                            </div>
                            <div class="card-body">
                                <div class="row">
                                    <div class="col-md-6">
                                <div class="mb-3">
                                            <label for="pageSize" class="form-label">Page Size</label>
                                            <select class="form-select" id="pageSize" name="page_size">
                                                <option value="a4" {% if schedule.format_config.page_size == 'a4' %}selected{% endif %}>A4</option>
                                                <option value="letter" {% if schedule.format_config.page_size == 'letter' %}selected{% endif %}>Letter</option>
                                                <option value="legal" {% if schedule.format_config.page_size == 'legal' %}selected{% endif %}>Legal</option>
                                                <option value="a3" {% if schedule.format_config.page_size == 'a3' %}selected{% endif %}>A3</option>
                                            </select>
                                    </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="mb-3">
                                            <label for="orientation" class="form-label">Orientation</label>
                                            <select class="form-select" id="orientation" name="orientation">
                                                <option value="portrait" {% if schedule.format_config.orientation == 'portrait' %}selected{% endif %}>Portrait</option>
                                                <option value="landscape" {% if schedule.format_config.orientation == 'landscape' %}selected{% endif %}>Landscape</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <h6 class="mt-4 mb-3">Font Settings</h6>
                                <div class="row">
                                    <div class="col-md-6">
                                <div class="mb-3">
                                            <label for="font_family" class="form-label">Font Family</label>
                                            <select class="form-select" id="font_family" name="font_family" onchange="updateFontPreview()">
                                                <option value="Arial, sans-serif" {% if schedule.format_config.font_family == 'Arial, sans-serif' %}selected{% endif %}>Arial</option>
                                                <option value="'Times New Roman', Times, serif" {% if schedule.format_config.font_family == "'Times New Roman', Times, serif" %}selected{% endif %}>Times New Roman</option>
                                                <option value="Calibri, 'Segoe UI', sans-serif" {% if schedule.format_config.font_family == "Calibri, 'Segoe UI', sans-serif" %}selected{% endif %}>Calibri</option>
                                                <option value="Georgia, serif" {% if schedule.format_config.font_family == 'Georgia, serif' %}selected{% endif %}>Georgia</option>
                                                <option value="Verdana, Geneva, sans-serif" {% if schedule.format_config.font_family == 'Verdana, Geneva, sans-serif' %}selected{% endif %}>Verdana</option>
                                            </select>
                                    </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="mb-3">
                                            <label for="font_size" class="form-label">Font Size</label>
                                            <select class="form-select" id="font_size" name="font_size" onchange="updateFontPreview()">
                                                <option value="10" {% if schedule.format_config.font_size == 10 %}selected{% endif %}>10pt</option>
                                                <option value="11" {% if schedule.format_config.font_size == 11 %}selected{% endif %}>11pt</option>
                                                <option value="12" {% if schedule.format_config.font_size == 12 %}selected{% endif %}>12pt</option>
                                                <option value="14" {% if schedule.format_config.font_size == 14 %}selected{% endif %}>14pt</option>
                                                <option value="16" {% if schedule.format_config.font_size == 16 %}selected{% endif %}>16pt</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="mb-3">
                                            <label for="line_height" class="form-label">Line Height</label>
                                            <select class="form-select" id="line_height" name="line_height" onchange="updateFontPreview()">
                                                <option value="1.2" {% if schedule.format_config.line_height == 1.2 %}selected{% endif %}>Compact (1.2)</option>
                                                <option value="1.5" {% if schedule.format_config.line_height == 1.5 %}selected{% endif %}>Normal (1.5)</option>
                                                <option value="2.0" {% if schedule.format_config.line_height == 2.0 %}selected{% endif %}>Spacious (2.0)</option>
                                            </select>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="mb-3">
                                    <label class="form-label">Font Preview</label>
                                    <div id="fontPreview" class="font-preview">
                                        This is a preview of the selected font. The quick brown fox jumps over the lazy dog.
                                    </div>
                                </div>
                                
                                <h6 class="mt-4 mb-3">Header Settings</h6>
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="include_header" name="include_header" {% if schedule.format_config.include_header %}checked{% endif %}>
                                    <label class="form-check-label" for="include_header">
                                        Include Custom Header
                                    </label>
                                </div>
                                
                                <div id="headerSettings" style="{% if not schedule.format_config.include_header %}display: none;{% endif %}">
                                    <div class="row">
                                        <div class="col-md-6">
                                            <div class="mb-3">
                                                <label for="header_title" class="form-label">Header Title</label>
                                                <input type="text" class="form-control" id="header_title" name="header_title" value="{{ schedule.format_config.header_title }}">
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="mb-3">
                                                <label for="header_logo" class="form-label">Logo (optional)</label>
                                                <input type="file" class="form-control" id="header_logo" name="header_logo" accept="image/png,image/jpeg">
                                                <div class="form-text">Supported formats: PNG, JPG (max 2MB, max dimensions 1500x1500px). Large images may cause PDF generation to fail.</div>
                                                {% if schedule.format_config.header_logo %}
                                                    <div class="mt-2">
                                                        <small>Current logo: {{ schedule.format_config.header_logo }}</small>
                                                    </div>
                                        {% endif %}
                                    </div>
                                        </div>
                                </div>
                                
                                    <div class="row">
                                        <div class="col-md-6">
                                <div class="mb-3">
                                                <label for="header_color" class="form-label">Header Color</label>
                                                <div class="input-group">
                                                    <span class="input-group-text p-0">
                                                        <input type="color" class="form-control form-control-color" id="header_color" name="header_color" value="{{ schedule.format_config.header_color }}">
                                                    </span>
                                                    <select class="form-select" id="predefined_colors" onchange="updateHeaderColor(this.value)">
                                                        <option value="">Custom</option>
                                                        <option value="#0d6efd" {% if schedule.format_config.header_color == '#0d6efd' %}selected{% endif %}>Blue</option>
                                                        <option value="#198754" {% if schedule.format_config.header_color == '#198754' %}selected{% endif %}>Green</option>
                                                        <option value="#dc3545" {% if schedule.format_config.header_color == '#dc3545' %}selected{% endif %}>Red</option>
                                                        <option value="#6f42c1" {% if schedule.format_config.header_color == '#6f42c1' %}selected{% endif %}>Purple</option>
                                                        <option value="#fd7e14" {% if schedule.format_config.header_color == '#fd7e14' %}selected{% endif %}>Orange</option>
                                                        <option value="#212529" {% if schedule.format_config.header_color == '#212529' %}selected{% endif %}>Black</option>
                                                    </select>
                                                </div>
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="mb-3">
                                                <label for="header_alignment" class="form-label">Header Alignment</label>
                                                <select class="form-select" id="header_alignment" name="header_alignment">
                                                    <option value="left" {% if schedule.format_config.header_alignment == 'left' %}selected{% endif %}>Left</option>
                                                    <option value="center" {% if schedule.format_config.header_alignment == 'center' %}selected{% endif %}>Center</option>
                                                    <option value="right" {% if schedule.format_config.header_alignment == 'right' %}selected{% endif %}>Right</option>
                                                </select>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <h6 class="mt-4 mb-3">Content Settings</h6>
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="includeSummary" name="include_summary" {% if schedule.format_config.include_summary %}checked{% endif %}>
                                    <label class="form-check-label" for="includeSummary">
                                        Include Data Summary
                                    </label>
                                </div>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="includeVisualization" name="include_visualization" {% if schedule.format_config.include_visualization %}checked{% endif %}>
                                    <label class="form-check-label" for="includeVisualization">
                                        Include Visualization
                                    </label>
                                </div>
                                
                                <div class="form-check mb-3">
                                    <input class="form-check-input" type="checkbox" id="limitRows" name="limit_rows" {% if schedule.format_config.max_rows %}checked{% endif %}>
                                    <label class="form-check-label" for="limitRows">
                                        Limit Number of Rows
                                    </label>
                                </div>
                                
                                <div class="mb-3">
                                    <label for="maxRows" class="form-label">Maximum Rows</label>
                                    <input type="number" class="form-control" id="maxRows" name="max_rows" value="{{ schedule.format_config.max_rows if schedule.format_config.max_rows else 1000 }}" min="1">
                                </div>
                            </div>
                        </div>
                        
                        <div class="card mb-4">
                            <div class="card-header">
                                <h5 class="mb-0"><i class="bi bi-send"></i> Delivery Options</h5>
                            </div>
                            <div class="card-body">
                                <!-- Email Delivery Tab -->
                                <div class="mb-4">
                                    <h6><i class="bi bi-envelope"></i> Email Delivery</h6>
                                    <div class="form-check mb-3">
                                        <input class="form-check-input" type="checkbox" id="enable_email" name="enable_email" {% if schedule.email_config.recipients %}checked{% endif %}>
                                        <label class="form-check-label" for="enable_email">
                                            Send Report via Email
                                        </label>
                                </div>
                                
                                    <div id="emailSettings" style="{% if not schedule.email_config.recipients %}display: none;{% endif %}">
                                    <div class="mb-3">
                                    <label for="recipients" class="form-label">Recipients (comma-separated)</label>
                                    <div class="input-group">
                                        <input type="text" class="form-control" id="recipientInput">
                                        <button class="btn btn-outline-secondary" type="button" id="addRecipientBtn">Add</button>
                                    </div>
                                    <div id="recipientTags" class="mt-2"></div>
                                </div>
                                
                                <script>
                                    function addRecipients(input, tagsContainer, hiddenContainer, fieldName) {
                                        const emails = input.value.split(',').map(email => email.trim()).filter(email => email);
                                        
                                        emails.forEach(email => {
                                            if (!email) return;
                                            
                                            // Check if email already exists
                                            const existingInput = tagsContainer.querySelector(`input[value="${email}"]`);
                                            if (existingInput) return;
                                            
                                            // Create tag
                                            const tag = document.createElement('span');
                                            tag.className = 'recipient-tag';
                                            tag.innerHTML = `${email} <span class="remove-btn" data-email="${email}">&times;</span>`;
                                            
                                            // Create hidden input
                                            const hiddenInput = document.createElement('input');
                                            hiddenInput.type = 'hidden';
                                            hiddenInput.name = fieldName;
                                            hiddenInput.value = email;
                                            
                                            // Add both tag and hidden input to the container
                                            tagsContainer.appendChild(tag);
                                            tagsContainer.appendChild(hiddenInput);
                                            
                                            // Add event listener to remove button
                                            tag.querySelector('.remove-btn').addEventListener('click', function() {
                                                const email = this.getAttribute('data-email');
                                                tag.remove();
                                                tagsContainer.querySelectorAll(`input[value="${email}"]`).forEach(input => input.remove());
                                            });
                                        });
                                        
                                        input.value = '';
                                    }
                                    
                                    // Add recipient when clicking Add button
                                    document.getElementById('addRecipientBtn').addEventListener('click', function() {
                                        addRecipients(
                                            document.getElementById('recipientInput'),
                                            document.getElementById('recipientTags'),
                                            'recipients'
                                        );
                                    });
                                    
                                    // Add recipient when pressing Enter or Tab
                                    document.getElementById('recipientInput').addEventListener('keydown', function(e) {
                                        if (e.key === 'Enter' || e.key === 'Tab') {
                                            e.preventDefault();
                                            addRecipients(
                                                document.getElementById('recipientInput'),
                                                document.getElementById('recipientTags'),
                                                'recipients'
                                            );
                                        }
                                    });
                                </script>
                                
                                    <div class="mb-3">
                                    <label for="cc" class="form-label">CC (comma-separated)</label>
                                    <div class="input-group">
                                        <input type="text" class="form-control" id="ccInput">
                                        <button class="btn btn-outline-secondary" type="button" id="addCcBtn">Add</button>
                                    </div>
                                    <div id="ccTags" class="mt-2"></div>
                                    <div id="ccContainer"></div>
                                </div>
                                
                                    <div class="mb-3">
                                    <label for="subject" class="form-label">Subject</label>
                                    <input type="text" class="form-control" id="subject" name="subject" 
                                           value="{{ schedule.email_config.subject if schedule.email_config else 'Report for ' + schedule.dataset_name }}">
                                </div>
                                
                                <div class="mb-3">
                                    <label for="body" class="form-label">Email Body</label>
                                    <textarea class="form-control" id="body" name="body" rows="6">{{ schedule.email_config.body if schedule.email_config else 'Please find the attached report.' }}</textarea>
                                </div>
                                    </div>
                                </div>
                                
                                <!-- WhatsApp Delivery Tab -->
                                <div class="mt-4">
                                    <h6><i class="bi bi-chat"></i> WhatsApp Delivery</h6>
                                    <div class="form-check mb-3">
                                        <input class="form-check-input" type="checkbox" id="enable_whatsapp" name="enable_whatsapp" {% if schedule.email_config.whatsapp_recipients %}checked{% endif %}>
                                        <label class="form-check-label" for="enable_whatsapp">
                                            Send Report via WhatsApp
                                        </label>
                                </div>
                                
                                    <div id="whatsappSettings" style="{% if not schedule.email_config.whatsapp_recipients %}display: none;{% endif %}">
                                        <div class="alert alert-info">
                                            <i class="bi bi-info-circle"></i> Enter WhatsApp numbers with country code (e.g., +1234567890).
                                            Recipients must opt-in to receive messages.
                                </div>
                                
                                    <div class="mb-3">
                                            <label for="whatsapp_recipients" class="form-label">WhatsApp Recipients</label>
                                            <div class="input-group">
                                                <input type="text" class="form-control" id="whatsappInput" placeholder="+1234567890">
                                                <button class="btn btn-outline-secondary" type="button" id="addWhatsappBtn">Add</button>
                                    </div>
                                            <div id="whatsappTags" class="mt-2">
                                                {% if schedule.email_config and schedule.email_config.whatsapp_recipients %}
                                                    {% for recipient in schedule.email_config.whatsapp_recipients %}
                                                        <span class="recipient-tag">{{ recipient }} <span class="remove-btn" data-email="{{ recipient }}">&times;</span></span>
                                                        <input type="hidden" name="whatsapp_recipients" value="{{ recipient }}">
                                                    {% endfor %}
                                                {% endif %}
                                </div>
                                            <div id="whatsappContainer"></div>
                                </div>
                                
                                    <div class="mb-3">
                                            <label for="whatsapp_message" class="form-label">Custom Message (optional)</label>
                                            <textarea class="form-control" id="whatsapp_message" name="whatsapp_message" rows="3">{{ schedule.email_config.whatsapp_message if schedule.email_config.whatsapp_message else '' }}</textarea>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="d-grid">
                            <button type="submit" class="btn btn-primary btn-lg">
                                <i class="bi bi-save"></i> Save Changes
                            </button>
                        </div>
                    </form>
                </div>
                
                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
                <script>
                    document.addEventListener('DOMContentLoaded', function() {
                        // Schedule type selection
                        const scheduleType = document.getElementById('scheduleType');
                        const scheduleOptions = document.querySelectorAll('.schedule-options');
                        
                        scheduleType.addEventListener('change', function() {
                            scheduleOptions.forEach(option => option.classList.remove('active'));
                            
                            switch(this.value) {
                                case 'one-time':
                                    document.getElementById('oneTimeOptions').classList.add('active');
                                    break;
                                case 'daily':
                                    document.getElementById('dailyOptions').classList.add('active');
                                    break;
                                case 'daily':
                                    document.getElementById('dailyOptions').classList.add('active');
                                    break;
                                case 'weekly':
                                    document.getElementById('weeklyOptions').classList.add('active');
                                    break;
                                case 'monthly':
                                    document.getElementById('monthlyOptions').classList.add('active');
                                    break;
                            }

                    // Add conditional validation for date input based on schedule type
                    const dateInput = document.getElementById('date');
                    scheduleType.addEventListener('change', function() {
                        if (this.value === 'one-time') {
                            dateInput.setAttribute('required', '');
                        } else {
                            dateInput.removeAttribute('required');
                        }
                    });
                        });
                        
                        // Monthly day option
                        const dayOption = document.getElementById('dayOption');
                        const specificDayDiv = document.getElementById('specificDayDiv');
                        
                        dayOption.addEventListener('change', function() {
                            if (this.value === 'Specific Day') {
                                specificDayDiv.style.display = 'block';
                            } else {
                                specificDayDiv.style.display = 'none';
                            }
                        });
                        
                        // Email enable/disable
                        const enableEmail = document.getElementById('enable_email');
                        const emailSettings = document.getElementById('emailSettings');
                        
                        enableEmail.addEventListener('change', function() {
                            emailSettings.style.display = this.checked ? 'block' : 'none';
                        });
                        
                        // WhatsApp enable/disable
                        const enableWhatsapp = document.getElementById('enable_whatsapp');
                        const whatsappSettings = document.getElementById('whatsappSettings');
                        
                        enableWhatsapp.addEventListener('change', function() {
                            whatsappSettings.style.display = this.checked ? 'block' : 'none';
                        });
                        
                        // Recipients handling for email
                        const recipientInput = document.getElementById('recipientInput');
                        const addRecipientBtn = document.getElementById('addRecipientBtn');
                        const recipientTags = document.getElementById('recipientTags');
                        const recipientsContainer = document.getElementById('recipientsContainer');
                        
                        function addRecipients(input, tagsContainer, hiddenContainer, fieldName) {
                            const emails = input.value.split(',').map(email => email.trim()).filter(email => email);
                            
                            emails.forEach(email => {
                                if (!email) return;
                                
                                // Create tag
                                const tag = document.createElement('span');
                                tag.className = 'recipient-tag';
                                tag.innerHTML = `${email} <span class="remove-btn" data-email="${email}">&times;</span>`;
                                tagsContainer.appendChild(tag);
                                
                                // Create hidden input
                                const hiddenInput = document.createElement('input');
                                hiddenInput.type = 'hidden';
                                hiddenInput.name = fieldName;
                                hiddenInput.value = email;
                                tagsContainer.appendChild(hiddenInput);  // Add to tagsContainer instead of a separate container
                                
                                // Add event listener to remove button
                                tag.querySelector('.remove-btn').addEventListener('click', function() {
                                    const email = this.getAttribute('data-email');
                                    // Remove both the tag and its associated hidden input
                                    this.parentNode.remove();
                                    tagsContainer.querySelectorAll(`input[value="${email}"]`).forEach(input => input.remove());
                                });
                            });
                            
                            input.value = '';
                        }
                        
                        addRecipientBtn.addEventListener('click', function() {
                            addRecipients(recipientInput, recipientTags, 'recipients');
                        });
                        
                        recipientInput.addEventListener('keydown', function(e) {
                            if (e.key === 'Enter' || e.key === 'Tab') {
                                e.preventDefault();
                                addRecipients(recipientInput, recipientTags, 'recipients');
                            }
                        });
                        
                        // CC handling for email
                        const ccInput = document.getElementById('ccInput');
                        const addCcBtn = document.getElementById('addCcBtn');
                        const ccTags = document.getElementById('ccTags');
                        
                        addCcBtn.addEventListener('click', function() {
                            addRecipients(ccInput, ccTags, 'cc');
                        });
                        
                        ccInput.addEventListener('keydown', function(e) {
                            if (e.key === 'Enter' || e.key === 'Tab') {
                                e.preventDefault();
                                addRecipients(ccInput, ccTags, 'cc');
                            }
                        });
                        
                        // WhatsApp recipients handling
                        const whatsappInput = document.getElementById('whatsappInput');
                        const addWhatsappBtn = document.getElementById('addWhatsappBtn');
                        const whatsappTags = document.getElementById('whatsappTags');
                        
                        addWhatsappBtn.addEventListener('click', function() {
                            addRecipients(whatsappInput, whatsappTags, 'whatsapp_recipients');
                        });
                        
                        whatsappInput.addEventListener('keydown', function(e) {
                            if (e.key === 'Enter' || e.key === 'Tab') {
                                e.preventDefault();
                                addRecipients(whatsappInput, whatsappTags, 'whatsapp_recipients');
                            }
                        });
                        
                        // Font preview function
                        updateFontPreview();
                        
                        // Include header toggle
                        const includeHeader = document.getElementById('include_header');
                        const headerSettings = document.getElementById('headerSettings');
                        
                        includeHeader.addEventListener('change', function() {
                            headerSettings.style.display = this.checked ? 'block' : 'none';
                        });
                    });
                    
                    // Font preview function
                    function updateFontPreview() {
                        const fontFamily = document.getElementById('font_family').value;
                        const fontSize = document.getElementById('font_size').value;
                        const lineHeight = document.getElementById('line_height').value;
                        
                        const fontPreview = document.getElementById('fontPreview');
                        fontPreview.style.fontFamily = fontFamily;
                        fontPreview.style.fontSize = fontSize + 'pt';
                        fontPreview.style.lineHeight = lineHeight;
                    }
                    
                    // Update header color from predefined colors
                    function updateHeaderColor(color) {
                        if (color) {
                            document.getElementById('header_color').value = color;
                        }
                    }
                </script>
            </body>
            </html>
        ''', schedule=schedule, timezones=timezones)
    except Exception as e:
        print(f"Error in edit_schedule: {str(e)}")
        flash(f'Error loading schedule details: {str(e)}', 'error')
        return redirect(url_for('manage_schedules'))

@app.route('/edit-schedule/<schedule_id>', methods=['POST'], endpoint='update_schedule')
@login_required
def update_schedule(schedule_id):
    """Process the edit schedule form submission"""
    try:
        # Get form data
        data = request.form
        
        # Build schedule configuration
        schedule_type = data.get('schedule_type')
        schedule_config = {
            'type': schedule_type,
            'hour': int(data.get('hour', 0)),
            'minute': int(data.get('minute', 0)),
            'timezone': data.get('timezone', 'UTC'),
        }
        
        # Add type-specific parameters
        if schedule_type == 'one-time':
            schedule_config['date'] = data.get('date')
        elif schedule_type == 'daily':
            # For daily schedules, we only need the time which is already handled above
            pass
            
        elif schedule_type == 'weekly':
            schedule_config['days'] = data.getlist('days')
        elif schedule_type == 'monthly':
            day_option = data.get('day_option')
            schedule_config['day_option'] = day_option
            if day_option == 'Specific Day':
                schedule_config['day'] = int(data.get('day', 1))
        
        # Email configuration
        email_config = {
            'recipients': data.getlist('recipients'),
            'cc': data.getlist('cc'),
            'subject': data.get('subject', f'Report'),
            'body': data.get('body', 'Please find the attached report.')
        }
        
        # Format configuration
        format_type = data.get('format_type')
        format_config = {'type': format_type}
        
        if format_type == 'pdf':
            format_config['page_size'] = data.get('page_size', 'a4')
            format_config['orientation'] = data.get('orientation', 'portrait')
            format_config['font_family'] = data.get('font_family', 'Helvetica')
            format_config['font_size'] = int(data.get('font_size', 10))
            format_config['line_height'] = float(data.get('line_height', 1.5))
            
            # Handle header settings
            format_config['include_header'] = data.get('include_header') == 'on'
            if format_config['include_header']:
                format_config['header_title'] = data.get('header_title', 'Report')
                
                # Handle logo file upload
                logo_file = request.files.get('header_logo')
                if logo_file and logo_file.filename:
                    # Validate the image file
                    is_valid, validation_message = validate_image(logo_file)
                    if not is_valid:
                        flash(validation_message, 'error')
                        return redirect(url_for('edit_schedule', schedule_id=schedule_id))
                    
                    # Save the file
                    filename = secure_filename(logo_file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"{timestamp}_{filename}"
                    
                    # Create directory if it doesn't exist - use a single, simple path
                    logos_dir = 'static/logos'
                    os.makedirs(logos_dir, exist_ok=True)
                    
                    # No longer needed - using only one location
                    # uploads_logos_dir = os.path.join('uploads', 'logos')
                    # os.makedirs(uploads_logos_dir, exist_ok=True)
                    
                    filepath = os.path.join(logos_dir, filename)
                    logo_file.save(filepath)
                    
                    # Store the relative path to the logo - simpler path
                    format_config['header_logo'] = 'static/logos/' + filename
                else:
                    # Keep the existing logo if no new one was uploaded
                    existing_schedule = report_manager.get_schedule(schedule_id)
                    if existing_schedule and existing_schedule.get('format_config', {}).get('header_logo'):
                        format_config['header_logo'] = existing_schedule['format_config']['header_logo']
                    else:
                        format_config['header_logo'] = ''
                
                format_config['header_color'] = data.get('header_color', '#0d6efd')
                format_config['header_alignment'] = data.get('header_alignment', 'center')
                
            # Handle content settings
            format_config['include_summary'] = data.get('include_summary') == 'on'
            format_config['include_visualization'] = data.get('include_visualization') == 'on'
            
            # Handle column selection
            if data.get('select_columns') == 'on':
                selected_columns = data.getlist('selected_columns')
                if selected_columns:
                    format_config['selected_columns'] = selected_columns
            
            # Handle row limit
            if data.get('limit_rows') == 'on':
                format_config['max_rows'] = int(data.get('max_rows', 1000))
        elif format_type == 'excel':
            format_config['sheet_name'] = data.get('sheet_name', 'Sheet1')
        elif format_type == 'csv':
            format_config['delimiter'] = data.get('delimiter', ',')
        elif format_type == 'json':
            format_config['indent'] = int(data.get('indent', 4))
        
        # Update the schedule
        success = report_manager.update_schedule(
            schedule_id, 
            schedule_config=schedule_config,
            email_config=email_config,
            format_config=format_config
        )
        
        if success:
            flash('Schedule updated successfully', 'success')
        else:
            flash('Failed to update schedule', 'error')
            
        return redirect(url_for('manage_schedules'))
        
    except Exception as e:
        print(f"Error in update_schedule: {str(e)}")
        flash(f'Error updating schedule: {str(e)}', 'error')
        return redirect(url_for('edit_schedule', schedule_id=schedule_id))

@app.route('/api/users/<user_id>', methods=['DELETE'])
@login_required
@role_required(['superadmin'])
def delete_user_api(user_id):
    """API endpoint to delete a user"""
    try:
        # Don't allow deleting the superadmin user
        if user_id == 'superadmin':
            return jsonify({
                'success': False,
                'error': 'Cannot delete superadmin user'
            }), 403
            
        # Delete the user from the database
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            
            # First check if user exists
            cursor.execute("SELECT rowid FROM users WHERE rowid = ?", (user_id,))
            if not cursor.fetchone():
                return jsonify({
                    'success': False,
                    'error': 'User not found'
                }), 404
            
            # Delete the user
            cursor.execute("DELETE FROM users WHERE rowid = ?", (user_id,))
            conn.commit()
            
            if cursor.rowcount == 0:
                return jsonify({
                    'success': False,
                    'error': 'Failed to delete user'
                }), 500
            
            return jsonify({'success': True})
            
    except Exception as e:
        print(f"Error deleting user: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/system/email-settings', methods=['POST'])
@login_required
@role_required(['superadmin'])
def save_email_settings_api():
    """API endpoint to save email settings"""
    try:
        data = request.json
        settings = {
            'smtp_server': data.get('smtp_server'),
            'smtp_port': data.get('smtp_port'),
            'sender_email': data.get('sender_email'),
            'sender_password': data.get('sender_password')
        }
        
        # Validate required fields
        if not all([settings['smtp_server'], settings['smtp_port'], 
                   settings['sender_email'], settings['sender_password']]):
            return jsonify({
                'success': False,
                'error': 'All fields are required'
            }), 400
        
        # Save settings using ReportManager
        if report_manager.save_settings(settings):
            return jsonify({
                'success': True,
                'message': 'Email settings saved successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save settings'
            }), 500
            
    except Exception as e:
        print(f"Error saving email settings: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    app.run(host='0.0.0.0', port=port) 