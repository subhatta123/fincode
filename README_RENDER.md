# Minimal Render Test App

This repository contains a minimal Flask application specifically designed to troubleshoot deployment issues on Render.com.

## What's Included

- **minimal_app.py**: A bare-bones Flask application with no dependencies beyond Flask itself
- **render.yaml**: Configuration for Render.com deployment
- **test_minimal_app.py**: Simple tests to verify the app works

## Key Features

1. No static file handling (disabled explicitly)
2. No templates
3. No database connections
4. No external dependencies beyond Flask and Gunicorn
5. Debug route that shows environment information

## Deployment Notes

This app is intentionally stripped down to the absolute minimum required to run on Render. If this fails to deploy, it suggests a fundamental issue with how Render is handling the application.

## Local Testing

To test locally:

```bash
# Install dependencies
pip install flask gunicorn

# Run the tests
python test_minimal_app.py

# Run the app
python minimal_app.py
```

You should see the app running at http://localhost:5000 