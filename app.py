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

# Initialize streamlit on first request
streamlit_started = False

@app.before_request
def start_streamlit_if_needed():
    global streamlit_started
    if not streamlit_started:
        thread = threading.Thread(target=run_streamlit)
        thread.daemon = True
        thread.start()
        # Give Streamlit time to start
        time.sleep(5)
        streamlit_started = True

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
    # Get the current host from the environment or default to localhost
    host = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:8501')
    return f'<meta http-equiv="refresh" content="0;URL=\'{host}\'" />'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port) 