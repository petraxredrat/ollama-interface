from flask import Flask
from flask_cors import CORS
import os

def create_app():
    app = Flask(__name__)
    CORS(app)  # Enable CORS for all routes
    
    # Configure generated code directory
    app.config['GENERATED_CODE_DIR'] = os.path.join(os.path.dirname(app.root_path), 'generated_code')
    os.makedirs(app.config['GENERATED_CODE_DIR'], exist_ok=True)
    
    # Register routes
    from . import routes
    app.register_blueprint(routes.bp)
    
    return app
