import os
import sys

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the app from the right module
try:
    from app import app
    print("Imported app from app/__init__.py")
except ImportError:
    from app import app
    print("Imported app from app.py")

# Add debug info
print(f"Current working directory: {os.getcwd()}")
print(f"Static folder: {app.static_folder}")
print(f"Static folder exists: {os.path.exists(app.static_folder)}")

# Make sure the static folder exists
if not os.path.exists(app.static_folder):
    print(f"Creating static folder: {app.static_folder}")
    os.makedirs(app.static_folder, exist_ok=True)

# Create the index.html file if it doesn't exist
index_path = os.path.join(app.static_folder, 'index.html')
if not os.path.exists(index_path):
    print(f"Creating index.html at {index_path}")
    with open(index_path, 'w') as f:
        f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Fincode API Server</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #333; }
        .status { padding: 15px; background-color: #f0f8ff; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>Fincode API Server</h1>
    <div class="status">
        <p>API server is running successfully.</p>
        <p>This is a temporary frontend page. The actual frontend will be added in future deployments.</p>
    </div>
</body>
</html>""")

# Print routes for debugging
print("Available routes:")
for rule in app.url_map.iter_rules():
    print(f"Route: {rule}, Endpoint: {rule.endpoint}")

if __name__ == "__main__":
    # Get port from environment variable or use default
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True) 