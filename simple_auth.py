"""
Simple authentication routes for login and register
These can be imported directly into app.py or used for testing
"""
from flask import Blueprint, render_template_string, request, redirect, url_for, flash, session

# Create a Blueprint for auth routes
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/simple-login', methods=['GET', 'POST'])
def simple_login():
    """A simplified login route for testing."""
    error = None
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Very simple authentication for testing
        if username == 'admin' and password == 'password':
            session['user'] = {
                'username': username,
                'role': 'admin'
            }
            return redirect(url_for('serve_index'))
        else:
            error = 'Invalid credentials'
    
    # Render the login form
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Simple Login</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                .container { max-width: 400px; margin: 50px auto; padding: 20px; border: 1px solid #ddd; }
                .form-group { margin-bottom: 15px; }
                label { display: block; margin-bottom: 5px; }
                input[type="text"], input[type="password"] { width: 100%; padding: 8px; }
                button { padding: 10px 15px; background: #0066cc; color: white; border: none; cursor: pointer; }
                .error { color: red; margin-bottom: 15px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Simple Login</h1>
                {% if error %}
                    <div class="error">{{ error }}</div>
                {% endif %}
                <form method="post">
                    <div class="form-group">
                        <label for="username">Username:</label>
                        <input type="text" id="username" name="username" required>
                    </div>
                    <div class="form-group">
                        <label for="password">Password:</label>
                        <input type="password" id="password" name="password" required>
                    </div>
                    <button type="submit">Login</button>
                </form>
                <p>Try: admin / password</p>
            </div>
        </body>
        </html>
    ''', error=error)

@auth_bp.route('/simple-register', methods=['GET', 'POST'])
def simple_register():
    """A simplified registration route for testing."""
    error = None
    success = None
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Very simple registration for testing
        if username and password:
            # In a real app, you would save to a database
            success = f'User {username} registered successfully'
        else:
            error = 'Username and password are required'
    
    # Render the registration form
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Simple Register</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                .container { max-width: 400px; margin: 50px auto; padding: 20px; border: 1px solid #ddd; }
                .form-group { margin-bottom: 15px; }
                label { display: block; margin-bottom: 5px; }
                input[type="text"], input[type="password"] { width: 100%; padding: 8px; }
                button { padding: 10px 15px; background: #0066cc; color: white; border: none; cursor: pointer; }
                .error { color: red; margin-bottom: 15px; }
                .success { color: green; margin-bottom: 15px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Simple Register</h1>
                {% if error %}
                    <div class="error">{{ error }}</div>
                {% endif %}
                {% if success %}
                    <div class="success">{{ success }}</div>
                {% endif %}
                <form method="post">
                    <div class="form-group">
                        <label for="username">Username:</label>
                        <input type="text" id="username" name="username" required>
                    </div>
                    <div class="form-group">
                        <label for="password">Password:</label>
                        <input type="password" id="password" name="password" required>
                    </div>
                    <button type="submit">Register</button>
                </form>
            </div>
        </body>
        </html>
    ''', error=error, success=success) 