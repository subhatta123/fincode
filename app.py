from flask import Flask, send_from_directory, render_template_string
import os
import subprocess
import threading
import time
from config import DATA_DIR, PUBLIC_REPORTS_DIR

app = Flask(__name__)

def get_streamlit_url():
    port = int(os.environ.get('PORT', 10000))
    if os.environ.get('RENDER'):
        # On Render, use the external URL
        return os.environ.get('RENDER_EXTERNAL_URL', f'http://localhost:{port}')
    return f'http://localhost:8501'

# Start Streamlit in a separate thread
def run_streamlit():
    try:
        port = int(os.environ.get('PORT', 10000))
        streamlit_cmd = f"streamlit run tableau_streamlit_app.py --server.port {port} --server.address 0.0.0.0"
        process = subprocess.Popen(streamlit_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("Streamlit process started")
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            print(f"Streamlit process failed: {stderr.decode()}")
        return process
    except Exception as e:
        print(f"Error starting Streamlit: {str(e)}")
        return None

# Initialize streamlit process
streamlit_process = None

@app.before_first_request
def initialize():
    global streamlit_process
    if not streamlit_process:
        print("Starting Streamlit process...")
        streamlit_process = run_streamlit()
        time.sleep(10)  # Give Streamlit more time to start

# Health check endpoint
@app.route('/health')
def health_check():
    return {'status': 'healthy'}, 200

# Serve static files
@app.route('/static/reports/<path:filename>')
def serve_report(filename):
    return send_from_directory(PUBLIC_REPORTS_DIR, filename)

# Main route - serve a loading page that checks Streamlit status
@app.route('/')
def home():
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
        </style>
        <script>
            function checkStreamlit() {
                fetch('/health')
                    .then(response => response.json())
                    .then(data => {
                        if (data.status === 'healthy') {
                            window.location.href = '""" + get_streamlit_url() + """';
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        setTimeout(checkStreamlit, 2000);
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
        </div>
    </body>
    </html>
    """
    return render_template_string(loading_html)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port) 