"""
Minimal admin access endpoint for the stock portfolio app.
This is a completely standalone endpoint that doesn't depend on the main app.
"""
from flask import Flask, request, redirect, session, render_template_string
import os
from datetime import datetime

# Create a minimal Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-for-testing')

# Simple HTML template
ADMIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Admin Access</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .success { color: green; }
        .error { color: red; }
        .info { margin-top: 20px; background: #f5f5f5; padding: 15px; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Admin Access</h1>
        {% if admin_access %}
            <p class="success">✅ Admin access granted</p>
            
            <div class="info">
                <h2>Admin User Info:</h2>
                <p><strong>Email:</strong> {{ email }}</p>
            </div>
            
            <div class="info">
                <h2>Environment Info:</h2>
                <p><strong>Time:</strong> {{ current_time }}</p>
                <p><strong>Environment:</strong> {{ environment }}</p>
            </div>
        {% else %}
            <p class="error">❌ Admin access denied</p>
            <p>You must be logged in with the admin email (fordutilityapps@gmail.com).</p>
            <p><a href="/">Return to home page</a></p>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/admin-standalone')
def admin_standalone():
    """Minimal admin access endpoint"""
    # Get email from query parameter (in production, this would come from authentication)
    email = request.args.get('email', '')
    
    # Check if user is admin
    admin_access = (email == 'fordutilityapps@gmail.com')
    
    # Get environment info
    environment = os.environ.get('FLASK_ENV', 'production')
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Render the template
    return render_template_string(
        ADMIN_HTML,
        admin_access=admin_access,
        email=email,
        current_time=current_time,
        environment=environment
    )

# For local testing
if __name__ == '__main__':
    app.run(debug=True)
