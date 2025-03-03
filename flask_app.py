from flask import Flask

# Create the simplest possible Flask app
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello from Render! The app is working!'

@app.route('/health')
def health():
    return {'status': 'ok'}

# Don't run the app when this file is imported
if __name__ == '__main__':
    app.run(debug=True) 