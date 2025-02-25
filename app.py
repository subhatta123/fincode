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

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Initialize managers
user_manager = UserManagement()
report_manager = ReportManager()
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
                        <h5>👤 User Profile</h5>
                        <p><strong>Username:</strong> {{ session.user.username }}</p>
                        <p><strong>Role:</strong> {{ session.user.role }}</p>
                        <p><strong>Organization:</strong> {{ session.user.organization_name or 'Not assigned' }}</p>
                    </div>
                    <hr>
                    <div class="px-3">
                        <a href="{{ url_for('tableau_connect') }}" class="btn btn-primary w-100 mb-2">🔌 Connect to Tableau</a>
                        <a href="{{ url_for('schedule_reports') }}" class="btn btn-primary w-100 mb-2">📅 Schedule Reports</a>
                        <hr>
                        <a href="{{ url_for('logout') }}" class="btn btn-secondary w-100">🚪 Logout</a>
                    </div>
                </div>
            </nav>
            
            <main class="main">
                <h1>💾 Saved Datasets</h1>
                {% if not datasets %}
                    <div class="alert alert-info">No datasets available. Connect to Tableau to import data.</div>
                {% else %}
                    <div class="row">
                        {% for dataset in datasets %}
                            <div class="col-md-6 mb-4">
                                <div class="card">
                                    <div class="card-body">
                                        <h5 class="card-title">📊 {{ dataset }}</h5>
                                        <div class="table-responsive">
                                            {{ dataset_previews[dataset] | safe }}
                                        </div>
                                        <p class="text-muted">Total rows: {{ dataset_rows[dataset] }}</p>
                                        <div class="btn-group">
                                            <a href="{{ url_for('schedule_dataset', dataset=dataset) }}" 
                                               class="btn btn-primary">📅 Schedule</a>
                                            <button onclick="deleteDataset('{{ dataset }}')" 
                                                    class="btn btn-danger">🗑️ Delete</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        {% endfor %}
                    </div>
                {% endif %}
            </main>
            
            <script>
                function deleteDataset(dataset) {
                    if (confirm('Are you sure you want to delete this dataset?')) {
                        fetch(`/api/datasets/${dataset}`, { method: 'DELETE' })
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    location.reload();
                                } else {
                                    alert('Failed to delete dataset');
                                }
                            });
                    }
                }
            </script>
        </body>
        </html>
    ''', datasets=datasets, 
        dataset_previews={d: get_dataset_preview_html(d) for d in datasets},
        dataset_rows={d: get_dataset_row_count(d) for d in datasets})

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
                        <h5>👤 Power User Profile</h5>
                        <p><strong>Username:</strong> {{ session.user.username }}</p>
                        <p><strong>Role:</strong> {{ session.user.role }}</p>
                        <p><strong>Organization:</strong> {{ session.user.organization_name or 'Not assigned' }}</p>
                    </div>
                    <hr>
                    <div class="px-3">
                        <a href="{{ url_for('tableau_connect') }}" class="btn btn-primary w-100 mb-2">🔌 Connect to Tableau</a>
                        <a href="{{ url_for('schedule_reports') }}" class="btn btn-primary w-100 mb-2">📅 Schedule Reports</a>
                        <a href="{{ url_for('qa_page') }}" class="btn btn-primary w-100 mb-2">❓ Ask Questions</a>
                        <hr>
                        <a href="{{ url_for('logout') }}" class="btn btn-secondary w-100">🚪 Logout</a>
                    </div>
                </div>
            </nav>
            
            <main class="main">
                <h1>💾 Saved Datasets</h1>
                {% if not datasets %}
                    <div class="alert alert-info">No datasets available. Connect to Tableau to import data.</div>
                {% else %}
                    <div class="row">
                        {% for dataset in datasets %}
                            <div class="col-md-6 mb-4">
                                <div class="card">
                                    <div class="card-body">
                                        <h5 class="card-title">📊 {{ dataset }}</h5>
                                        <div class="table-responsive">
                                            {{ dataset_previews[dataset] | safe }}
                                        </div>
                                        <p class="text-muted">Total rows: {{ dataset_rows[dataset] }}</p>
                                        <div class="btn-group">
                                            <a href="{{ url_for('schedule_dataset', dataset=dataset) }}" 
                                               class="btn btn-primary">📅 Schedule</a>
                                            <a href="{{ url_for('qa_page', dataset=dataset) }}"
                                               class="btn btn-info">❓ Ask Questions</a>
                                            <button onclick="deleteDataset('{{ dataset }}')" 
                                                    class="btn btn-danger">🗑️ Delete</button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        {% endfor %}
                    </div>
                {% endif %}
            </main>
            
            <script>
                function deleteDataset(dataset) {
                    if (confirm('Are you sure you want to delete this dataset?')) {
                        fetch(`/api/datasets/${dataset}`, { method: 'DELETE' })
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    location.reload();
                                } else {
                                    alert('Failed to delete dataset');
                                }
                            });
                    }
                }
            </script>
        </body>
        </html>
    ''', datasets=datasets, 
        dataset_previews={d: get_dataset_preview_html(d) for d in datasets},
        dataset_rows={d: get_dataset_row_count(d) for d in datasets})

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
        
        return jsonify({
            'success': True,
            'answer': answer,
            'visualization': visualization.to_dict() if visualization else None
        })
        
    except Exception as e:
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

@app.route('/admin')
@login_required
@role_required(['superadmin'])
def admin_dashboard():
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
                    // Implement edit user functionality
                }
                
                function deleteUser(userId) {
                    if (confirm('Are you sure you want to delete this user?')) {
                        fetch(`/api/users/${userId}`, {
                            method: 'DELETE'
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                location.reload();
                            } else {
                                alert(data.error || 'Failed to delete user');
                            }
                        });
                    }
                }
                
                function filterUsers() {
                    const search = document.getElementById('searchUser').value.toLowerCase();
                    const permission = document.getElementById('filterPermission').value;
                    const rows = document.getElementById('userTableBody').getElementsByTagName('tr');
                    
                    for (let row of rows) {
                        const username = row.cells[0].textContent.toLowerCase();
                        const email = row.cells[1].textContent.toLowerCase();
                        const role = row.cells[2].textContent.toLowerCase();
                        
                        const matchesSearch = username.includes(search) || 
                                           email.includes(search);
                        const matchesPermission = !permission || role === permission;
                        
                        row.style.display = matchesSearch && matchesPermission ? '' : 'none';
                    }
                }
            </script>
        </body>
        </html>
    ''', users=get_users(), organizations=get_organizations())

@app.route('/api/users', methods=['POST'])
@login_required
@role_required(['superadmin'])
def create_user_api():
    try:
        data = request.json
        if user_manager.add_user_to_org(
            username=data['username'],
            password=data['password'],
            org_id=data['organization_id'] or None,
            permission_type=data['permission_type'],
            email=data['email']
        ):
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Failed to create user'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/users/<user_id>', methods=['DELETE'])
@login_required
@role_required(['superadmin'])
def delete_user_api(user_id):
    try:
        if user_manager.delete_user(user_id):
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Failed to delete user'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def get_users():
    """Get all users"""
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.rowid, u.username, u.email, u.role, u.organization_id, o.name
                FROM users u
                LEFT JOIN organizations o ON u.organization_id = o.rowid
                ORDER BY u.username
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
            return users
    except Exception as e:
        print(f"Error getting users: {str(e)}")
        return []

def get_organizations():
    """Get all organizations"""
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT rowid, name FROM organizations ORDER BY name")
            return [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error getting organizations: {str(e)}")
        return []

@app.route('/tableau-connect', methods=['GET', 'POST'])
@login_required
def tableau_connect():
    if request.method == 'POST':
        try:
            server_url = request.form.get('server_url')
            site_name = request.form.get('site_name')
            auth_method = request.form.get('auth_method')
            
            if not server_url:
                flash('Please enter server URL')
                return redirect(url_for('tableau_connect'))
            
            credentials = {}
            if auth_method == 'token':
                token_name = request.form.get('token_name')
                token_value = request.form.get('token_value')
                if not (token_name and token_value):
                    flash('Please enter both token name and value')
                    return redirect(url_for('tableau_connect'))
                credentials = {'token_name': token_name, 'token_value': token_value}
            else:
                username = request.form.get('username')
                password = request.form.get('password')
                if not (username and password):
                    flash('Please enter both username and password')
                    return redirect(url_for('tableau_connect'))
                credentials = {'username': username, 'password': password}
            
            # Attempt to authenticate
            server = authenticate(server_url, auth_method, credentials, site_name)
            if not server:
                flash('Failed to connect to Tableau server')
                return redirect(url_for('tableau_connect'))
            
            # Get workbooks
            workbooks = get_workbooks(server)
            if not workbooks:
                flash('No workbooks found or insufficient permissions')
                return redirect(url_for('tableau_connect'))
            
            # Store connection in session
            session['tableau_connection'] = {
                'server_url': server_url,
                'site_name': site_name,
                'auth_method': auth_method,
                'credentials': credentials,
                'workbooks': workbooks
            }
            
            return redirect(url_for('select_workbook'))
            
        except Exception as e:
            flash(f'Error connecting to Tableau: {str(e)}')
            return redirect(url_for('tableau_connect'))
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Connect to Tableau - Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="row justify-content-center">
                    <div class="col-md-8">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h1>🔌 Connect to Tableau</h1>
                            <a href="{{ url_for('home') }}" class="btn btn-outline-primary">← Back</a>
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
                                <form method="post">
                                    <div class="mb-3">
                                        <label class="form-label">Server URL</label>
                                        <input type="text" class="form-control" name="server_url" 
                                               placeholder="https://your-server.tableau.com" required>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Site Name (optional)</label>
                                        <input type="text" class="form-control" name="site_name" 
                                               placeholder="Leave blank for default site">
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Authentication Method</label>
                                        <div class="form-check">
                                            <input class="form-check-input" type="radio" name="auth_method" 
                                                   value="token" id="authToken" checked>
                                            <label class="form-check-label" for="authToken">
                                                Personal Access Token
                                            </label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="radio" name="auth_method" 
                                                   value="password" id="authPassword">
                                            <label class="form-check-label" for="authPassword">
                                                Username/Password
                                            </label>
                                        </div>
                                    </div>
                                    
                                    <div id="tokenAuth">
                                        <div class="row">
                                            <div class="col-md-6">
                                                <div class="mb-3">
                                                    <label class="form-label">Token Name</label>
                                                    <input type="text" class="form-control" name="token_name">
                                                </div>
                                            </div>
                                            <div class="col-md-6">
                                                <div class="mb-3">
                                                    <label class="form-label">Token Value</label>
                                                    <input type="password" class="form-control" name="token_value">
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div id="passwordAuth" style="display: none;">
                                        <div class="row">
                                            <div class="col-md-6">
                                                <div class="mb-3">
                                                    <label class="form-label">Username</label>
                                                    <input type="text" class="form-control" name="username">
                                                </div>
                                            </div>
                                            <div class="col-md-6">
                                                <div class="mb-3">
                                                    <label class="form-label">Password</label>
                                                    <input type="password" class="form-control" name="password">
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <button type="submit" class="btn btn-primary">Connect</button>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                document.querySelectorAll('input[name="auth_method"]').forEach(radio => {
                    radio.addEventListener('change', function() {
                        document.getElementById('tokenAuth').style.display = 
                            this.value === 'token' ? 'block' : 'none';
                        document.getElementById('passwordAuth').style.display = 
                            this.value === 'password' ? 'block' : 'none';
                    });
                });
            </script>
        </body>
        </html>
    ''')

@app.route('/select-workbook')
@login_required
def select_workbook():
    if 'tableau_connection' not in session:
        flash('Please connect to Tableau first')
        return redirect(url_for('tableau_connect'))
    
    workbooks = session['tableau_connection']['workbooks']
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Select Workbook - Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
                .workbook-card {
                    cursor: pointer;
                    transition: transform 0.2s;
                }
                .workbook-card:hover {
                    transform: translateY(-5px);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="row justify-content-center">
                    <div class="col-md-10">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h1>📚 Select Workbook</h1>
                            <div>
                                <a href="{{ url_for('tableau_connect') }}" class="btn btn-outline-primary me-2">
                                    🔄 Reconnect
                                </a>
                                <a href="{{ url_for('home') }}" class="btn btn-outline-secondary">
                                    ← Back
                                </a>
                            </div>
                        </div>
                        
                        {% with messages = get_flashed_messages() %}
                            {% if messages %}
                                {% for message in messages %}
                                    <div class="alert alert-info">{{ message }}</div>
                                {% endfor %}
                            {% endif %}
                        {% endwith %}
                        
                        <div class="row">
                            {% for workbook in workbooks %}
                                <div class="col-md-6 mb-4">
                                    <div class="card workbook-card h-100" 
                                         onclick="selectWorkbook('{{ workbook.id }}')">
                                        <div class="card-body">
                                            <h5 class="card-title">
                                                📊 {{ workbook.name }}
                                            </h5>
                                            <p class="card-text text-muted">
                                                Project: {{ workbook.project_name }}
                                            </p>
                                            <p class="card-text">
                                                Available Views: {{ workbook.views|length }}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                function selectWorkbook(workbookId) {
                    window.location.href = `/select-views/${workbookId}`;
                }
            </script>
        </body>
        </html>
    ''', workbooks=workbooks)

@app.route('/select-views/<workbook_id>')
@login_required
def select_views(workbook_id):
    if 'tableau_connection' not in session:
        flash('Please connect to Tableau first')
        return redirect(url_for('tableau_connect'))
    
    workbooks = session['tableau_connection']['workbooks']
    workbook = next((w for w in workbooks if w['id'] == workbook_id), None)
    
    if not workbook:
        flash('Workbook not found')
        return redirect(url_for('select_workbook'))
    
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Select Views - Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
                .view-card {
                    cursor: pointer;
                }
                .view-card.selected {
                    border-color: #0d6efd;
                    background-color: #f8f9fa;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="row justify-content-center">
                    <div class="col-md-10">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h1>🖼️ Select Views</h1>
                            <div>
                                <a href="{{ url_for('select_workbook') }}" class="btn btn-outline-primary me-2">
                                    ← Back to Workbooks
                                </a>
                            </div>
                        </div>
                        
                        <div class="card mb-4">
                            <div class="card-body">
                                <h5>Selected Workbook</h5>
                                <p class="mb-0">
                                    <strong>{{ workbook.name }}</strong>
                                    <span class="text-muted">({{ workbook.project_name }})</span>
                                </p>
                            </div>
                        </div>
                        
                        {% with messages = get_flashed_messages() %}
                            {% if messages %}
                                {% for message in messages %}
                                    <div class="alert alert-info">{{ message }}</div>
                                {% endfor %}
                            {% endif %}
                        {% endwith %}
                        
                        <form id="viewsForm" method="post" action="{{ url_for('download_views') }}">
                            <input type="hidden" name="workbook_id" value="{{ workbook.id }}">
                            
                            <div class="row">
                                {% for view in workbook.views %}
                                    <div class="col-md-6 mb-4">
                                        <div class="card view-card" onclick="toggleView(this, '{{ view.id }}')">
                                            <div class="card-body">
                                                <div class="form-check">
                                                    <input class="form-check-input" type="checkbox" 
                                                           name="view_ids" value="{{ view.id }}"
                                                           style="display: none;">
                                                    <label class="form-check-label">
                                                        <h5 class="card-title mb-0">
                                                            🖼️ {{ view.name }}
                                                        </h5>
                                                    </label>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                {% endfor %}
                            </div>
                            
                            <div class="d-flex justify-content-end mt-4">
                                <button type="submit" class="btn btn-primary" id="downloadBtn" disabled>
                                    Download Selected Views
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
            
            <script>
                function toggleView(card, viewId) {
                    const checkbox = card.querySelector('input[type="checkbox"]');
                    checkbox.checked = !checkbox.checked;
                    card.classList.toggle('selected', checkbox.checked);
                    
                    // Enable/disable download button
                    const checkedBoxes = document.querySelectorAll('input[name="view_ids"]:checked');
                    document.getElementById('downloadBtn').disabled = checkedBoxes.length === 0;
                }
            </script>
        </body>
        </html>
    ''', workbook=workbook)

@app.route('/download-views', methods=['POST'])
@login_required
def download_views():
    if 'tableau_connection' not in session:
        flash('Please connect to Tableau first')
        return redirect(url_for('tableau_connect'))
    
    workbook_id = request.form.get('workbook_id')
    view_ids = request.form.getlist('view_ids')
    
    if not view_ids:
        flash('Please select at least one view')
        return redirect(url_for('select_views', workbook_id=workbook_id))
    
    # Get workbook and views
    workbooks = session['tableau_connection']['workbooks']
    workbook = next((w for w in workbooks if w['id'] == workbook_id), None)
    views = [v for v in workbook['views'] if v['id'] in view_ids]
    
    # Generate table name
    view_names = [view['name'] for view in views]
    table_name = generate_table_name(workbook['name'], view_names)
    
    try:
        # Authenticate with saved credentials
        conn = session['tableau_connection']
        server = authenticate(
            conn['server_url'],
            conn['auth_method'],
            conn['credentials'],
            conn['site_name']
        )
        
        # Download and save data
        success = download_and_save_data(
            server,
            view_ids,
            workbook['name'],
            view_names,
            table_name
        )
        
        if success:
            flash('Data downloaded successfully!')
            return redirect(url_for('home'))
        else:
            flash('Failed to download data')
            return redirect(url_for('select_views', workbook_id=workbook_id))
            
    except Exception as e:
        flash(f'Error downloading data: {str(e)}')
        return redirect(url_for('select_views', workbook_id=workbook_id))

@app.route('/schedule-reports')
@login_required
def schedule_reports():
    datasets = get_saved_datasets()
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Schedule Reports - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="row justify-content-center">
                    <div class="col-md-10">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h1>📅 Schedule Reports</h1>
                            <a href="{{ url_for('home') }}" class="btn btn-outline-primary">← Back</a>
                        </div>
                        
                        {% if not datasets %}
                            <div class="alert alert-info">
                                No datasets available. Please connect to Tableau and download some data first.
                            </div>
                        {% else %}
                            <div class="row">
                                {% for dataset in datasets %}
                                    <div class="col-md-6 mb-4">
                                        <div class="card">
                                            <div class="card-body">
                                                <h5 class="card-title">📊 {{ dataset }}</h5>
                                                <p class="text-muted">Rows: {{ dataset_rows[dataset] }}</p>
                                                <a href="{{ url_for('schedule_dataset', dataset=dataset) }}" 
                                                   class="btn btn-primary">Schedule Report</a>
                                            </div>
                                        </div>
                                    </div>
                                {% endfor %}
                            </div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </body>
        </html>
    ''', datasets=datasets, dataset_rows={d: get_dataset_row_count(d) for d in datasets})

@app.route('/schedule-dataset/<dataset>')
@login_required
def schedule_dataset(dataset):
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Schedule Dataset Report - Tableau Data Reporter</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body { padding: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="row justify-content-center">
                    <div class="col-md-8">
                        <div class="d-flex justify-content-between align-items-center mb-4">
                            <h1>📅 Schedule Report</h1>
                            <a href="{{ url_for('schedule_reports') }}" class="btn btn-outline-primary">← Back</a>
                        </div>
                        
                        <div class="card mb-4">
                            <div class="card-body">
                                <h5>Dataset: {{ dataset }}</h5>
                                <p class="text-muted mb-0">Total rows: {{ row_count }}</p>
                            </div>
                        </div>
                        
                        <div class="card">
                            <div class="card-body">
                                <form id="scheduleForm" onsubmit="return submitSchedule(event)">
                                    <input type="hidden" name="dataset" value="{{ dataset }}">
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Schedule Type</label>
                                        <select class="form-select" name="schedule_type" onchange="updateScheduleFields()" required>
                                            <option value="one-time">One Time</option>
                                            <option value="daily">Daily</option>
                                            <option value="weekly">Weekly</option>
                                            <option value="monthly">Monthly</option>
                                        </select>
                                    </div>
                                    
                                    <div id="oneTimeFields">
                                        <div class="mb-3">
                                            <label class="form-label">Date</label>
                                            <input type="date" class="form-control" name="date" 
                                                   min="{{ today }}" required>
                                        </div>
                                    </div>
                                    
                                    <div id="weeklyFields" style="display: none;">
                                        <div class="mb-3">
                                            <label class="form-label">Days of Week</label>
                                            <div class="form-check">
                                                <input type="checkbox" class="form-check-input" name="days[]" value="0">
                                                <label class="form-check-label">Monday</label>
                                            </div>
                                            <div class="form-check">
                                                <input type="checkbox" class="form-check-input" name="days[]" value="1">
                                                <label class="form-check-label">Tuesday</label>
                                            </div>
                                            <div class="form-check">
                                                <input type="checkbox" class="form-check-input" name="days[]" value="2">
                                                <label class="form-check-label">Wednesday</label>
                                            </div>
                                            <div class="form-check">
                                                <input type="checkbox" class="form-check-input" name="days[]" value="3">
                                                <label class="form-check-label">Thursday</label>
                                            </div>
                                            <div class="form-check">
                                                <input type="checkbox" class="form-check-input" name="days[]" value="4">
                                                <label class="form-check-label">Friday</label>
                                            </div>
                                            <div class="form-check">
                                                <input type="checkbox" class="form-check-input" name="days[]" value="5">
                                                <label class="form-check-label">Saturday</label>
                                            </div>
                                            <div class="form-check">
                                                <input type="checkbox" class="form-check-input" name="days[]" value="6">
                                                <label class="form-check-label">Sunday</label>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div id="monthlyFields" style="display: none;">
                                        <div class="mb-3">
                                            <label class="form-label">Day of Month</label>
                                            <select class="form-select" name="day_option">
                                                <option value="specific">Specific Day</option>
                                                <option value="last">Last Day</option>
                                                <option value="first_weekday">First Weekday</option>
                                                <option value="last_weekday">Last Weekday</option>
                                            </select>
                                        </div>
                                        <div id="specificDayField" class="mb-3">
                                            <label class="form-label">Day</label>
                                            <input type="number" class="form-control" name="day" 
                                                   min="1" max="31" value="1">
                                        </div>
                                    </div>
                                    
                                    <div class="row">
                                        <div class="col-md-6">
                                            <div class="mb-3">
                                                <label class="form-label">Hour (24-hour)</label>
                                                <input type="number" class="form-control" name="hour" 
                                                       min="0" max="23" value="0" required>
                                            </div>
                                        </div>
                                        <div class="col-md-6">
                                            <div class="mb-3">
                                                <label class="form-label">Minute</label>
                                                <input type="number" class="form-control" name="minute" 
                                                       min="0" max="59" value="0" required>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Timezone</label>
                                        <select class="form-select" name="timezone" required>
                                            {% for tz in timezones %}
                                                <option value="{{ tz }}"
                                                        {% if tz == 'UTC' %}selected{% endif %}>
                                                    {{ tz }}
                                                </option>
                                            {% endfor %}
                                        </select>
                                    </div>
                                    
                                    <hr>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Report Format</label>
                                        <div class="form-check">
                                            <input class="form-check-input" type="radio" name="format" value="PDF" id="formatPDF" checked>
                                            <label class="form-check-label" for="formatPDF">PDF</label>
                                        </div>
                                        <div class="form-check">
                                            <input class="form-check-input" type="radio" name="format" value="CSV" id="formatCSV">
                                            <label class="form-check-label" for="formatCSV">CSV</label>
                                        </div>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Email Recipients (comma-separated)</label>
                                        <input type="text" class="form-control" name="recipients" 
                                               placeholder="email1@example.com, email2@example.com" required>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">WhatsApp Recipients (comma-separated)</label>
                                        <input type="text" class="form-control" name="whatsapp_recipients" 
                                               placeholder="+1234567890, +0987654321">
                                        <small class="text-muted">Include country code (e.g., +1 for US)</small>
                                    </div>
                                    
                                    <div class="mb-3">
                                        <label class="form-label">Message (optional)</label>
                                        <textarea class="form-control" name="message" rows="3"
                                                  placeholder="Optional message to include in the email and WhatsApp"></textarea>
                                    </div>
                                    
                                    <button type="submit" class="btn btn-primary">Create Schedule</button>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
                function updateScheduleFields() {
                    const scheduleType = document.querySelector('select[name="schedule_type"]').value;
                    
                    document.getElementById('oneTimeFields').style.display = 
                        scheduleType === 'one-time' ? 'block' : 'none';
                    document.getElementById('weeklyFields').style.display = 
                        scheduleType === 'weekly' ? 'block' : 'none';
                    document.getElementById('monthlyFields').style.display = 
                        scheduleType === 'monthly' ? 'block' : 'none';
                    
                    // Update required attributes
                    document.querySelector('input[name="date"]').required = 
                        scheduleType === 'one-time';
                }
                
                function submitSchedule(event) {
                    event.preventDefault();
                    const form = event.target;
                    const formData = new FormData(form);
                    
                    // Get selected days for weekly schedule
                    if (formData.get('schedule_type') === 'weekly') {
                        const days = Array.from(document.querySelectorAll('input[name="days[]"]:checked'))
                            .map(cb => parseInt(cb.value));
                        if (days.length === 0) {
                            alert('Please select at least one day for weekly schedule');
                            return false;
                        }
                        formData.delete('days[]');
                        formData.append('days', JSON.stringify(days));
                    }
                    
                    // Get WhatsApp recipients
                    const whatsappRecipients = formData.get('whatsapp_recipients')
                        .split(',')
                        .map(num => num.trim())
                        .filter(num => num);
                    
                    fetch('/api/schedules', {
                        method: 'POST',
                        body: formData
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            window.location.href = "{{ url_for('schedule_reports') }}";
                        } else {
                            alert(data.error || 'Failed to create schedule');
                        }
                    });
                    
                    return false;
                }
                
                // Initialize fields on load
                document.addEventListener('DOMContentLoaded', updateScheduleFields);
            </script>
        </body>
        </html>
    ''', dataset=dataset, row_count=get_dataset_row_count(dataset),
        today=datetime.now().strftime('%Y-%m-%d'),
        timezones=pytz.all_timezones)

@app.route('/api/schedules', methods=['POST'])
@login_required
def create_schedule_api():
    try:
        dataset = request.form.get('dataset')
        schedule_type = request.form.get('schedule_type')
        timezone = request.form.get('timezone', 'UTC')
        
        # Parse schedule configuration
        schedule_config = {
            'type': schedule_type,
            'hour': int(request.form.get('hour', 0)),
            'minute': int(request.form.get('minute', 0)),
            'timezone': timezone
        }
        
        if schedule_type == 'one-time':
            schedule_config['date'] = request.form.get('date')
        elif schedule_type == 'weekly':
            schedule_config['days'] = json.loads(request.form.get('days', '[]'))
        elif schedule_type == 'monthly':
            schedule_config['day_option'] = request.form.get('day_option')
            if schedule_config['day_option'] == 'specific':
                schedule_config['day'] = int(request.form.get('day', 1))
        
        # Parse email configuration
        email_config = {
            'recipients': [email.strip() for email in request.form.get('recipients', '').split(',')],
            'whatsapp_recipients': [num.strip() for num in request.form.get('whatsapp_recipients', '').split(',') if num.strip()],
            'body': request.form.get('message', '').strip(),
            'format': request.form.get('format', 'PDF'),
            'smtp_server': os.getenv('SMTP_SERVER'),
            'smtp_port': int(os.getenv('SMTP_PORT', 587)),
            'sender_email': os.getenv('SENDER_EMAIL'),
            'sender_password': os.getenv('SENDER_PASSWORD')
        }
        
        # Create schedule
        job_id = report_manager.schedule_report(dataset, email_config, schedule_config)
        if job_id:
            return jsonify({'success': True, 'job_id': job_id})
        return jsonify({'success': False, 'error': 'Failed to create schedule'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    app.run(host='0.0.0.0', port=port) 