"""
Vercel serverless function handler for the Flask app.
This file imports the main Flask app from app.py and serves it.
"""
import os
import sys

# Add the parent directory to sys.path to allow importing from app.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # Import the Flask app from app.py
    from app import app
    print("Successfully imported app from app.py")
except Exception as e:
    # If import fails, create a minimal app that shows the error
    from flask import Flask, render_template_string
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-for-testing')
    
    @app.route('/')
    def error_page():
        error_message = f"Error importing Flask app: {str(e)}"
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Import Error</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .container { max-width: 800px; margin: 0 auto; }
                .error { margin-top: 20px; background: #ffeeee; padding: 15px; border-radius: 5px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>ApesTogether Stock Portfolio App</h1>
                <div class="error">
                    <h2>Error</h2>
                    <p>{{ error_message }}</p>
                    <p>Please check the server logs for more details.</p>
                </div>
            </div>
        </body>
        </html>
        """, error_message=error_message)
    
    print(f"Failed to import app from app.py: {e}")

# For local testing
if __name__ == '__main__':
    app.run(debug=True)
