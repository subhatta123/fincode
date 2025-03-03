#!/bin/bash

# Display system information
echo "Deployment preparation script running..."
echo "Current directory: $(pwd)"
echo "Directory contents before cleanup:"
ls -la

# Check for and remove the app directory if it exists
if [ -d "app" ]; then
  echo "Found app directory - removing to prevent conflicts..."
  rm -rf app
else
  echo "No app directory found (good)"
fi

# Check for and remove problematic files
echo "Checking for wsgi.py..."
if [ -f "wsgi.py" ]; then
  echo "Found wsgi.py - renaming to wsgi.py.bak..."
  mv wsgi.py wsgi.py.bak
else
  echo "No wsgi.py found (good)"
fi

# Check if frontend directory exists and remove it
if [ -d "frontend" ]; then
  echo "Found frontend directory - removing to prevent conflicts..."
  rm -rf frontend
else
  echo "No frontend directory found (good)"
fi

# Create a simple test to verify everything is working
echo "Creating test access file..."
echo "This is a test file created during deployment: $(date)" > deployment_test.txt

# Display final directory contents
echo "Directory contents after cleanup:"
ls -la

echo "Deployment preparation complete!" 