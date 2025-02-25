from flask import Flask, render_template_string, redirect, url_for, request, jsonify, send_from_directory
import os
import subprocess
import threading
import time
from pathlib import Path

app = Flask(__name__)

# Initialize Streamlit process
streamlit_process = None
streamlit_initialized = False

def get_streamlit_url():
    """Get the Streamlit URL based on environment"""
    if os.environ.get('RENDER'):
        # On Render, use the external URL
        return os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:8501')
    return 'http://localhost:8501'

def run_streamlit():
    """Start Streamlit in a separate process"""
    try:
        port = int(os.environ.get('PORT', 8501))
        streamlit_cmd = f"streamlit run tableau_streamlit_app.py --server.port {port} --server.address 0.0.0.0"
        process = subprocess.Popen(streamlit_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("Streamlit process started")
        return process
    except Exception as e:
        print(f"Error starting Streamlit: {str(e)}")
        return None

@app.before_request
def initialize():
    """Initialize Streamlit before first request"""
    global streamlit_process, streamlit_initialized
    if not streamlit_initialized:
        print("Starting Streamlit process...")
        streamlit_process = run_streamlit()
        time.sleep(10)  # Give Streamlit time to start
        streamlit_initialized = True

@app.route('/health')
def health_check():
    """Health check endpoint"""
    global streamlit_process
    if streamlit_process and streamlit_process.poll() is None:
        return {'status': 'healthy'}, 200
    return {'status': 'initializing'}, 503

@app.route('/')
def home():
    """Main route - serve a loading page that checks Streamlit status"""
    loading_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Loading Tableau Data Reporter</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background-color: #f5f5f5;
            }
            .loader {
                border: 4px solid #f3f3f3;
                border-radius: 50%;
                border-top: 4px solid #3498db;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin-bottom: 20px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .container {
                text-align: center;
            }
            .status {
                margin-top: 20px;
                color: #666;
            }
        </style>
        <script>
            let attempts = 0;
            const maxAttempts = 30; // 60 seconds total (2s * 30)
            
            function checkStreamlit() {
                fetch('/health')
                    .then(response => response.json())
                    .then(data => {
                        attempts++;
                        if (data.status === 'healthy') {
                            window.location.href = '""" + get_streamlit_url() + """';
                        } else if (attempts < maxAttempts) {
                            document.getElementById('status').textContent = `Initializing... (Attempt ${attempts}/${maxAttempts})`;
                            setTimeout(checkStreamlit, 2000);
                        } else {
                            document.getElementById('status').textContent = 'Failed to start application. Please refresh the page.';
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        if (attempts < maxAttempts) {
                            setTimeout(checkStreamlit, 2000);
                        }
                    });
            }
            setTimeout(checkStreamlit, 2000);
        </script>
    </head>
    <body>
        <div class="container">
            <div class="loader"></div>
            <h2>Loading Tableau Data Reporter...</h2>
            <p>Please wait while we initialize the application.</p>
            <p id="status" class="status">Initializing...</p>
        </div>
    </body>
    </html>
    """
    return render_template_string(loading_html)

# Serve static files (reports)
@app.route('/static/reports/<path:filename>')
def serve_report(filename):
    reports_dir = Path("static/reports")
    return send_from_directory(reports_dir, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    app.run(host='0.0.0.0', port=port) 