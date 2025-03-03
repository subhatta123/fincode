#!/bin/bash
# Setup script to ensure static files are correctly organized

echo "Setting up static file structure..."

# Create necessary directories
mkdir -p frontend/build/static
mkdir -p frontend/build/logos
mkdir -p frontend/build/reports

# Copy static files from static to frontend/build
if [ -d "static" ]; then
  echo "Copying files from static to frontend/build..."
  cp -r static/* frontend/build/ 2>/dev/null || true
fi

# Ensure index.html exists
if [ ! -f "frontend/build/index.html" ]; then
  echo "Creating default index.html..."
  cp -f static/index.html frontend/build/ 2>/dev/null || true
fi

# Set proper permissions
chmod -R 755 frontend

echo "Static file setup complete." 