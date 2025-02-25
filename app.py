import os
import subprocess
from flask import Flask

app = Flask(__name__)

# Start Streamlit in a separate process
def run_streamlit():
    streamlit_cmd = f"streamlit run tableau_streamlit_app.py --server.port {os.environ.get('PORT', 8501)} --server.address 0.0.0.0"
    process = subprocess.Popen(streamlit_cmd, shell=True)
    return process

# Initialize Streamlit process
streamlit_process = None

@app.before_first_request
def start_streamlit():
    global streamlit_process
    if not streamlit_process:
        streamlit_process = run_streamlit()

@app.route('/')
def home():
    port = os.environ.get('PORT', 8501)
    return f'<meta http-equiv="refresh" content="0;URL=\'http://localhost:{port}\'" />'

@app.route('/health')
def health():
    return {'status': 'healthy'}, 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8501))
    app.run(host='0.0.0.0', port=port) 