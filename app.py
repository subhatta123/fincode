from flask import Flask, render_template_string, redirect, url_for, request, jsonify, send_from_directory, session, flash
import os
import json
from pathlib import Path
from datetime import datetime
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
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
                                            <a href="#" class="card-link" 
                                               onclick="viewDatasetPreview('{{ dataset }}')">View Preview</a>
                                            <a href="{{ url_for('schedule_dataset', dataset=dataset) }}" 
                                               class="card-link">Create Schedule</a>
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
                                        <div id="visualization"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
            <script>
                const questionForm = document.getElementById('questionForm');
                const chatContainer = document.getElementById('chatContainer');
                
                questionForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    
                    const formData = new FormData(questionForm);
                    const dataset = formData.get('dataset');
                    const question = formData.get('question');
                    
                    // Add user message to chat
                    addMessage(question, 'user');
                    
                    try {
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
                        
                        if (data.success) {
                            // Add assistant's response to chat
                            addMessage(data.answer, 'assistant');
                            
                            // Update visualization if provided
                            if (data.visualization) {
                                Plotly.newPlot('visualization', data.visualization);
                            }
                        } else {
                            addMessage('Error: ' + data.error, 'assistant');
                        }
                    } catch (error) {
                        addMessage('Error: Failed to get response', 'assistant');
                    }
                    
                    // Clear question input
                    questionForm.querySelector('input[name="question"]').value = '';
                });
                
                function addMessage(message, type) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = `chat-message ${type}-message`;
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
        answer, visualization = data_analyzer.ask_question(df, question)
        
        # Debug: Log the visualization type and structure
        print(f"Visualization type: {type(visualization)}")
        
        # Function to recursively convert NumPy types to Python standard types
        def convert_numpy_types(obj):
            import numpy as np
            
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, dict):
                return {key: convert_numpy_types(value) for key, value in obj.items()}
            elif isinstance(obj, list) or isinstance(obj, tuple):
                return [convert_numpy_types(item) for item in obj]
            else:
                return obj
        
        # Handle JSON serialization
        vis_dict = None
        if visualization is not None:
            try:
                # Try different approaches to convert the visualization
                
                # 1. First try the to_dict method if it exists
                if hasattr(visualization, 'to_dict'):
                    print("Using to_dict() method")
                    vis_dict = visualization.to_dict()
                
                # 2. If that doesn't work, try to manually create a dict if it has .data
                if vis_dict is None and hasattr(visualization, 'data'):
                    print("Using .data attribute")
                    vis_dict = {}
                    for key, value in visualization.data.items():
                        vis_dict[key] = value  # Will be converted later
                
                # 3. If that doesn't work, try to convert to dict using vars() (if object has __dict__)
                if vis_dict is None and hasattr(visualization, '__dict__'):
                    print("Using __dict__ attribute")
                    vis_dict = vars(visualization)
                
                # 4. If it's a Plotly figure, try to extract the data
                if vis_dict is None and hasattr(visualization, 'data') and hasattr(visualization, 'layout'):
                    print("Handling as Plotly figure")
                    vis_dict = {
                        'data': getattr(visualization, 'data', []),
                        'layout': getattr(visualization, 'layout', {})
                    }
                
                # 5. If all else fails, try to convert the entire object directly
                if vis_dict is None:
                    print("Using direct conversion")
                    vis_dict = visualization
                
                # Finally, convert any NumPy types in the structure
                vis_dict = convert_numpy_types(vis_dict)
                
            except Exception as e:
                print(f"Error converting visualization to dict: {str(e)}")
                # Return a message instead of None so the user knows what happened
                vis_dict = None
                # Don't fail silently - send error message to the user
                return jsonify({
                    'success': True,
                    'answer': answer,
                    'visualization': None,
                    'visualization_error': f"Could not display visualization: {str(e)}"
                })
        
        return jsonify({
            'success': True,
            'answer': answer,
            'visualization': vis_dict
        })
        
    except Exception as e:
        print(f"Error in ask_question_api: {str(e)}")
        import traceback
        traceback.print_exc()  # Print full stack trace for debugging
        return jsonify({
            'success': False,
            'error': str(e)
        })

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

# API endpoints for AJAX calls
@app.route('/api/datasets/<dataset>', methods=['DELETE'])
@login_required
def delete_dataset_api(dataset):
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute(f"DROP TABLE IF EXISTS '{dataset}'")
            conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error deleting dataset: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/datasets/<dataset>/preview')
@login_required
def dataset_preview_api(dataset):
    try:
        preview_html = get_dataset_preview_html(dataset)
        return preview_html
    except Exception as e:
        print(f"Error generating preview for {dataset}: {str(e)}")
        return f"<div class='alert alert-danger'>Error: {str(e)}</div>"

@app.route('/admin')
@login_required
@role_required(['superadmin'])
def admin_dashboard():
    # Get users list
    try:
        # Get users from database
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.rowid, u.username, u.email, u.role, u.organization_id, o.name
                FROM users u
                LEFT JOIN organizations o ON u.organization_id = o.rowid
            """)
            users = []
            for row in cursor.fetchall():
                users.append({
                    'id': row[0],
                    'username': row[1],
                    'email': row[2],
                    'role': row[3],
                    'organization_id': row[4],
                    'organization_name': row[5]
                })
                
        # Get organizations
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT rowid, name FROM organizations")
            organizations = []
            for row in cursor.fetchall():
                organizations.append({
                    'id': row[0],
                    'name': row[1]
                })
                
        return render_template_string('''
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
                            <a href="{{ url_for('admin_users') }}" class="btn btn-primary w-100 mb-2">👥 Users</a>
                            <a href="{{ url_for('admin_organizations') }}" class="btn btn-primary w-100 mb-2">🏢 Organizations</a>
                            <a href="{{ url_for('admin_system') }}" class="btn btn-primary w-100 mb-2">⚙️ System</a>
                            <hr>
                            <a href="{{ url_for('logout') }}" class="btn btn-secondary w-100">🚪 Logout</a>
                        </div>
                    </div>
                </nav>
                
                <main class="main">
                    <h1>👥 User Management</h1>
                    
                    <div class="card mb-4">
                        <div class="card-body">
                            <h5>Add New User</h5>
                            <form id="addUserForm" onsubmit="return addUser(event)">
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
                                                <option value="normal">Normal</option>
                                                <option value="power">Power</option>
                                                <option value="superadmin">Superadmin</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="col-md-4">
                                        <div class="mb-3">
                                            <label class="form-label">Organization</label>
                                            <select class="form-select" name="organization_id">
                                                <option value="">No Organization</option>
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
                            <div class="d-flex justify-content-between align-items-center mb-3">
                                <h5 class="mb-0">Existing Users</h5>
                                <div class="d-flex gap-2">
                                    <input type="text" class="form-control" id="searchUser" 
                                        placeholder="Search users..." onkeyup="filterUsers()">
                                    <select class="form-select" id="filterPermission" onchange="filterUsers()">
                                        <option value="">All Permissions</option>
                                        <option value="normal">Normal</option>
                                        <option value="power">Power</option>
                                        <option value="superadmin">Superadmin</option>
                                    </select>
                                </div>
                            </div>
                            
                            <div class="table-responsive">
                                <table class="table table-hover">
                                    <thead>
                                        <tr>
                                            <th>Username</th>
                                            <th>Email</th>
                                            <th>Role</th>
                                            <th>Organization</th>
                                            <th>Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody id="userTableBody">
                                        {% for user in users %}
                                            <tr>
                                                <td>{{ user.username }}</td>
                                                <td>{{ user.email }}</td>
                                                <td>{{ user.role }}</td>
                                                <td>{{ user.organization_name or 'None' }}</td>
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
                </main>
                
                <!-- Edit User Modal -->
                <div class="modal fade" id="editUserModal" tabindex="-1" aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">Edit User</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <form id="editUserForm">
                                    <input type="hidden" id="edit-user-id" name="id">
                                    <div class="mb-3">
                                        <label class="form-label">Username</label>
                                        <input type="text" class="form-control" id="edit-username" name="username" required>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">Email</label>
                                        <input type="email" class="form-control" id="edit-email" name="email" required>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">Password</label>
                                        <input type="password" class="form-control" id="edit-password" name="password" 
                                            placeholder="Leave blank to keep current password">
                                        <div class="form-text">Leave blank to keep the current password</div>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">Permission Type</label>
                                        <select class="form-select" id="edit-permission-type" name="permission_type" required>
                                            <option value="normal">Normal</option>
                                            <option value="power">Power</option>
                                            <option value="superadmin">Superadmin</option>
                                        </select>
                                    </div>
                                    <div class="mb-3">
                                        <label class="form-label">Organization</label>
                                        <select class="form-select" id="edit-organization-id" name="organization_id">
                                            <option value="">No Organization</option>
                                            {% for org in organizations %}
                                                <option value="{{ org.id }}">{{ org.name }}</option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                </form>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                                <button type="button" class="btn btn-primary" onclick="updateUser()">Save Changes</button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
                <script>
                    function addUser(event) {
                        event.preventDefault();
                        const form = event.target;
                        const formData = new FormData(form);
                        
                        fetch('/api/users', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify(Object.fromEntries(formData))
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                location.reload();
                            } else {
                                alert(data.error || 'Failed to create user');
                            }
                        });
                        
                        return false;
                    }
                    
                    function editUser(userId) {
                        console.log('editUser function called with userId:', userId);
                        
                        // Fetch user data
                        fetch(`/api/users/${userId}`)
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    // Populate the form
                                    const user = data.user;
                                    document.getElementById('edit-user-id').value = user.id;
                                    document.getElementById('edit-username').value = user.username;
                                    document.getElementById('edit-email').value = user.email;
                                    document.getElementById('edit-permission-type').value = user.role;
                                    document.getElementById('edit-organization-id').value = user.organization_id;
                                    
                                    // Clear password field
                                    document.getElementById('edit-password').value = '';
                                    
                                    // Try to show the modal using Bootstrap
                                    try {
                                        // Try using Bootstrap 5 approach
                                        const modalElement = document.getElementById('editUserModal');
                                        if (typeof bootstrap !== 'undefined') {
                                            const modal = new bootstrap.Modal(modalElement);
                                            modal.show();
                                        } else {
                                            // Fallback if Bootstrap JS is not loaded
                                            console.log('Bootstrap not loaded, using fallback to show modal');
                                            modalElement.style.display = 'block';
                                            modalElement.classList.add('show');
                                            modalElement.setAttribute('aria-modal', 'true');
                                            document.body.classList.add('modal-open');
                                            
                                            // Add backdrop
                                            const backdrop = document.createElement('div');
                                            backdrop.className = 'modal-backdrop fade show';
                                            document.body.appendChild(backdrop);
                                        }
                                    } catch (e) {
                                        console.error('Error showing modal:', e);
                                        alert('Error showing modal. Try refreshing the page.');
                                    }
                                } else {
                                    alert(data.error || 'Failed to get user data');
                                }
                            })
                            .catch(error => {
                                alert('Error fetching user data: ' + error);
                            });
                    }
                    
                    function updateUser() {
                        console.log('updateUser function called');
                        const userId = document.getElementById('edit-user-id').value;
                        const formData = new FormData(document.getElementById('editUserForm'));
                        
                        fetch(`/api/users/${userId}`, {
                            method: 'PUT',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify(Object.fromEntries(formData))
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                // Try to close the modal
                                try {
                                    const modalElement = document.getElementById('editUserModal');
                                    
                                    if (typeof bootstrap !== 'undefined') {
                                        // Bootstrap 5 approach
                                        const modalInstance = bootstrap.Modal.getInstance(modalElement);
                                        if (modalInstance) {
                                            modalInstance.hide();
                                        }
                                    } else {
                                        // Fallback if Bootstrap JS is not loaded
                                        modalElement.style.display = 'none';
                                        modalElement.classList.remove('show');
                                        modalElement.setAttribute('aria-modal', 'false');
                                        document.body.classList.remove('modal-open');
                                        
                                        // Remove backdrop if it exists
                                        const backdrop = document.querySelector('.modal-backdrop');
                                        if (backdrop) {
                                            backdrop.remove();
                                        }
                                    }
                                } catch (e) {
                                    console.error('Error closing modal:', e);
                                }
                                
                                // Reload the page to show updated data
                                location.reload();
                            } else {
                                alert(data.error || 'Failed to update user');
                            }
                        })
                        .catch(error => {
                            console.error('Error updating user:', error);
                            alert('Error updating user: ' + error);
                        });
                    }
                </script>
            </body>
            </html>
        ''', users=users, organizations=organizations)
        
    except Exception as e:
        print(f"Error in admin_dashboard function: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        flash(f'Error loading admin dashboard: {str(e)}')
        return redirect(url_for('home'))

@app.route('/create_schedule', methods=['POST'])
def process_schedule_form():
    try:
        # Get form data
        dataset_name = request.form.get('dataset_name')
        if not dataset_name:
            flash('Dataset name is required', 'error')
            return redirect(url_for('manage_schedules'))
        
        # Debug: Print all form data to see what's being submitted
        print("Form data received:")
        for key, value in request.form.items():
            print(f"  {key}: {value}")
            
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
                
        # Email configuration
        email_config = {
            'recipients': request.form.getlist('recipients'),
            'cc': request.form.getlist('cc'),
            'subject': request.form.get('subject', f'Report for {dataset_name}'),
            'body': request.form.get('body', 'Please find the attached report.')
        }
        
        # Format configuration
        format_type = request.form.get('format_type')
        format_config = {'type': format_type}
        
        if format_type == 'csv':
            format_config['delimiter'] = request.form.get('delimiter', ',')
            format_config['quotechar'] = request.form.get('quotechar', '"')
            
        elif format_type == 'excel':
            format_config['sheet_name'] = request.form.get('sheet_name', 'Sheet1')
            
        elif format_type == 'json':
            format_config['indent'] = int(request.form.get('indent', 4))
            format_config['orient'] = request.form.get('orient', 'records')
            
        # Schedule the report
        job_id = report_manager.schedule_report(dataset_name, schedule_config, email_config, format_config)
        
        if job_id:
            flash(f"Schedule created successfully. Next run at: {report_manager.get_next_run_time(job_id)}", 'success')
        else:
            flash("Failed to create schedule. Check logs for details.", 'error')
            
        return redirect(url_for('manage_schedules'))
        
    except Exception as e:
        print(f"Error in process_schedule_form: {str(e)}")
        flash(f"Error creating schedule: {str(e)}", 'error')
        return redirect(url_for('manage_schedules'))

# Fix the admin routes to match endpoint names
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
    # System settings page
    try:
        import sys
        import flask
        import time
        from datetime import datetime
        
        return render_template_string('''
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
                            <a href="{{ url_for('admin_users') }}" class="btn btn-primary w-100 mb-2">👥 Users</a>
                            <a href="{{ url_for('admin_organizations') }}" class="btn btn-primary w-100 mb-2">🏢 Organizations</a>
                            <a href="{{ url_for('admin_system') }}" class="btn btn-primary w-100 mb-2">⚙️ System</a>
                            <hr>
                            <a href="{{ url_for('logout') }}" class="btn btn-secondary w-100">🚪 Logout</a>
                        </div>
                    </div>
                </nav>
                
                <main class="main">
                    <h1>⚙️ System Settings</h1>
                    
                    <div class="card mb-4">
                        <div class="card-body">
                            <h5>Email Configuration</h5>
                            <form id="emailConfigForm">
                                <div class="mb-3">
                                    <label class="form-label">SMTP Server</label>
                                    <input type="text" class="form-control" name="smtp_server" 
                                          value="{{ os.getenv('SMTP_SERVER', '') }}">
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">SMTP Port</label>
                                    <input type="number" class="form-control" name="smtp_port" 
                                          value="{{ os.getenv('SMTP_PORT', '587') }}">
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Sender Email</label>
                                    <input type="email" class="form-control" name="sender_email" 
                                          value="{{ os.getenv('SENDER_EMAIL', '') }}">
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Sender Password</label>
                                    <input type="password" class="form-control" name="sender_password" 
                                          value="{{ os.getenv('SENDER_PASSWORD', '') }}">
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
                </main>
                
                <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
                <script>
                    document.getElementById('emailConfigForm').addEventListener('submit', function(e) {
                        e.preventDefault();
                        // Implement save email settings functionality
                        alert('Save email settings functionality not implemented yet');
                    });
                    
                    function backupDatabase() {
                        // Implement backup database functionality
                        alert('Backup database functionality not implemented yet');
                    }
                    
                    function restoreDatabase() {
                        // Implement restore database functionality
                        alert('Restore database functionality not implemented yet');
                    }
                </script>
            </body>
            </html>
        ''', os=os, sys=sys, flask=flask, time=time, datetime=datetime)
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    app.run(host='0.0.0.0', port=port) 