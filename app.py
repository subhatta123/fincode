from flask import Flask, send_from_directory
import os
import subprocess
import threading
import time
from config import DATA_DIR, PUBLIC_REPORTS_DIR

app = Flask(__name__)

# Start Streamlit in a separate thread
def run_streamlit():
    streamlit_cmd = f"streamlit run tableau_streamlit_app.py --server.port 8501 --server.address 0.0.0.0"
    subprocess.Popen(streamlit_cmd, shell=True)

# Start Streamlit when the Flask app starts
@app.before_first_request
def start_streamlit():
    thread = threading.Thread(target=run_streamlit)
    thread.daemon = True
    thread.start()
    # Give Streamlit time to start
    time.sleep(5)

# Health check endpoint
@app.route('/health')
def health_check():
    return {'status': 'healthy'}, 200

# Serve static files
@app.route('/static/reports/<path:filename>')
def serve_report(filename):
    return send_from_directory(PUBLIC_REPORTS_DIR, filename)

# Main route - redirect to Streamlit
@app.route('/')
def home():
    return f'<meta http-equiv="refresh" content="0;URL=\'http://localhost:8501\'" />'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port) 