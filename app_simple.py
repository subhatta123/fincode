from flask import Flask, jsonify

# Create Flask app
app = Flask(__name__)

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Basic Flask App on Render</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            h1 { color: #333; }
            p { margin-bottom: 15px; }
            .status { padding: 15px; background-color: #f0f8ff; border-radius: 5px; margin-bottom: 20px; }
            .nav { margin-top: 20px; }
            .nav a { display: inline-block; margin-right: 15px; padding: 8px 15px; background: #0d6efd; color: white; text-decoration: none; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>Basic Flask App on Render</h1>
        <div class="status">
            <p>This minimal application should definitely work on Render!</p>
        </div>
        <div class="nav">
            <a href="/health">Health Check</a>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "message": "The application is working correctly"
    })

# This is important - the app needs to be available at the module level for gunicorn
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=True) 