from flask import Blueprint, jsonify

main_bp = Blueprint('main', __name__)

@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "message": "API server is running",
        "version": "1.0.0"
    })

# Add other non-API routes here if needed 