#!/usr/bin/env python
"""
Health check endpoint for Flask application
"""

from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render."""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(debug=True) 