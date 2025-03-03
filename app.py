# This file exists only because Render is hardcoded to use app.py
# It simply imports and exposes the Flask app from our minimal_app.py

# Import directly from minimal_app
from minimal_app import app

# Print a startup message to confirm this file is being used
print("=" * 50)
print("Using app.py wrapper to load minimal_app.py")
print("This confirms that Render is loading app.py")
print("=" * 50)

# No need to modify anything else, as we're just importing the app object
# from minimal_app.py which already has all routes defined
