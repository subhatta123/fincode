from flask import Flask, send_from_directory, jsonify
import os
from config import DATA_DIR, PUBLIC_REPORTS_DIR

app = Flask(__name__)

# Health check endpoint
@app.route('/health')
def health_check():
    return {'status': 'healthy'}, 200

# Serve static files
@app.route('/static/reports/<path:filename>')
def serve_report(filename):
    return send_from_directory(PUBLIC_REPORTS_DIR, filename)

# Main route
@app.route('/')
def home():
    return jsonify({
        'status': 'running',
        'message': 'Tableau Data Reporter API is running'
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port) 