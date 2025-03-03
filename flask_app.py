"""
Simplified Flask application that ensures proper handling of static vs. dynamic routes
"""
import os
from flask import Flask, render_template_string, redirect, url_for, request, jsonify, send_from_directory, session, flash

def create_app():
    """Create and configure the Flask application with clear static file handling."""
    # Initialize Flask with absolute static folder path and a distinct static URL path
    app = Flask(__name__)
    
    # Configure static folder using environment variable or default
    static_folder = os.environ.get('STATIC_FOLDER', os.path.join(os.getcwd(), 'frontend', 'build'))
    static_url_path = os.environ.get('STATIC_URL_PATH', '/static_files')
    
    # Set static folder and URL path
    app.static_folder = static_folder
    app.static_url_path = static_url_path
    
    print(f"Static folder: {app.static_folder}")
    print(f"Static URL path: {app.static_url_path}")
    
    # Set secret key from environment variable or generate random one
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
    
    # Basic route for root path
    @app.route('/')
    def index():
        """Serve the index page."""
        index_path = os.path.join(app.static_folder, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(app.static_folder, 'index.html')
        return "Index file not found", 404
    
    # Test route to verify Flask routing works
    @app.route('/test')
    def test():
        """Test route to verify Flask is handling routes correctly."""
        print("TEST ROUTE ACCESSED")
        return "Success! Flask routing is working correctly."
    
    # Simple login test
    @app.route('/login-test')
    def login_test():
        """Simple login test page."""
        print("LOGIN TEST ROUTE ACCESSED")
        return """
        <html>
        <head><title>Login Test</title></head>
        <body>
            <h1>Login Test Working!</h1>
            <p>This confirms Flask is handling dynamic routes properly.</p>
            <a href="/">Back to home</a>
        </body>
        </html>
        """
    
    # Simple register test
    @app.route('/register-test')
    def register_test():
        """Simple register test page."""
        print("REGISTER TEST ROUTE ACCESSED")
        return """
        <html>
        <head><title>Register Test</title></head>
        <body>
            <h1>Register Test Working!</h1>
            <p>This confirms Flask is handling dynamic routes properly.</p>
            <a href="/">Back to home</a>
        </body>
        </html>
        """
    
    # Debug route to show all registered routes
    @app.route('/debug/routes')
    def debug_routes():
        """Show all registered routes for debugging."""
        routes = []
        for rule in app.url_map.iter_rules():
            routes.append({
                'endpoint': rule.endpoint,
                'methods': ','.join(sorted(rule.methods)),
                'path': str(rule)
            })
        return jsonify({'total_routes': len(routes), 'routes': routes})
    
    # Health check for Render
    @app.route('/health')
    def health_check():
        """Health check endpoint for Render."""
        return jsonify({'status': 'ok'})
    
    # Create a basic login page
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Basic login functionality."""
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            # Super basic authentication for testing
            if username == 'admin' and password == 'password':
                session['user'] = {'username': username, 'role': 'admin'}
                return redirect('/')
            
            return "Invalid credentials", 401
        
        return """
        <html>
        <head>
            <title>Login</title>
            <style>
                body { font-family: Arial; margin: 0; padding: 20px; }
                .container { max-width: 400px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; }
                input { width: 100%; padding: 8px; margin-bottom: 10px; }
                button { padding: 10px; background: #0066cc; color: white; border: none; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Login</h1>
                <form method="post">
                    <div>
                        <input type="text" name="username" placeholder="Username" required>
                    </div>
                    <div>
                        <input type="password" name="password" placeholder="Password" required>
                    </div>
                    <button type="submit">Login</button>
                </form>
                <p>Use admin/password for testing</p>
                <p><a href="/">Back to home</a></p>
            </div>
        </body>
        </html>
        """
    
    # Create a basic register page
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        """Basic registration functionality."""
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            # Just show success for now
            return f"Registered user: {username} (this is just a test)", 200
        
        return """
        <html>
        <head>
            <title>Register</title>
            <style>
                body { font-family: Arial; margin: 0; padding: 20px; }
                .container { max-width: 400px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; }
                input { width: 100%; padding: 8px; margin-bottom: 10px; }
                button { padding: 10px; background: #0066cc; color: white; border: none; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Register</h1>
                <form method="post">
                    <div>
                        <input type="text" name="username" placeholder="Username" required>
                    </div>
                    <div>
                        <input type="password" name="password" placeholder="Password" required>
                    </div>
                    <button type="submit">Register</button>
                </form>
                <p><a href="/">Back to home</a></p>
            </div>
        </body>
        </html>
        """
    
    return app

# Create the application
app = create_app() 