"""
Vercel serverless function handler for the Flask app.
This file is required for Vercel to properly serve the Flask application.
"""
from flask import Flask
import sys
import os

# Add the parent directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the Flask app from app.py
try:
    from app import app as flask_app
    print("Successfully imported Flask app from app.py")
except Exception as e:
    print(f"Error importing Flask app: {e}")
    # Create a minimal fallback app if the main app fails to import
    flask_app = Flask(__name__)
    
    @flask_app.route('/')
    def index():
        return "Flask app import error. Please check the logs."

# This is what Vercel looks for
app = flask_app
