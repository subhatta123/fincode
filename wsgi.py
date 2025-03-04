from app import app

# Add debug info
import os
print(f"Current working directory: {os.getcwd()}")
print(f"Static folder: {app.static_folder}")
print(f"Static folder exists: {os.path.exists(app.static_folder)}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True) 