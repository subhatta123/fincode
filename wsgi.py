from app import app
import os

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True) 