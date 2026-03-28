# This file is specifically for Vercel's Python runtime
# It exports the Flask app in a way that Vercel expects

import os
import sys

# Add both api directory AND root directory to path for imports
api_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(api_dir)
sys.path.insert(0, api_dir)
sys.path.insert(0, root_dir)  # For blueprints in root: mobile_api, leaderboard_routes, etc.

# Import the Flask app from index.py
from index import app

