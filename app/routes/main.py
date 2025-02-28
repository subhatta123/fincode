from flask import Blueprint, render_template, jsonify

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Handle the root URL request"""
    # If you have an index.html template:
    # return render_template('index.html')
    
    # Or return a simple JSON response:
    return jsonify({
        "status": "success",
        "message": "API server is running",
        "version": "1.0.0"
    }) 