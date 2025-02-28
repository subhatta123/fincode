from flask import Flask

# Create the Flask application instance
app = Flask(__name__)

# Configure the application
# app.config.from_object('config.Config')

# Import and register blueprints
from app.routes.scheduler import scheduler_bp
from app.routes.main import main_bp

app.register_blueprint(scheduler_bp)
app.register_blueprint(main_bp) 