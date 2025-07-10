"""
Vercel serverless function handler for Flask application
"""

import sys
import os

# Add parent directory to path so we can import from app.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the Flask app
from app import app

# This is required for Vercel serverless functions
handler = app
