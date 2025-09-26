# This file is specifically for Vercel's Python runtime
# It exports the Flask app in a way that Vercel expects

import os
import sys

# Add the current directory to the path so we can import index
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now import the app from index.py
error_info = None
try:
    from index import app
    print("Successfully imported app from index.py")
    print(f"App routes: {[rule.rule for rule in app.url_map.iter_rules()]}")
except Exception as e:
    import traceback
    error_message = str(e)
    error_traceback = traceback.format_exc()
    print(f"Error importing app from index.py: {error_message}")
    print(error_traceback)
    
    # Create a fallback app for debugging
    from flask import Flask, jsonify
    app = Flask(__name__)
    
    @app.route('/')
    def debug_index():
        return jsonify({
            "error": error_message,
            "traceback": error_traceback,
            "sys_path": sys.path,
            "cwd": os.getcwd(),
            "files": os.listdir(os.path.dirname(os.path.abspath(__file__)))
        })

