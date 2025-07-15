"""
Vercel serverless function handler for the Flask app.
This is a standalone minimal version that includes admin access.
"""
from flask import Flask, render_template_string, redirect, url_for, request, session, flash
import os
from datetime import datetime
import sys

# Create a Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-for-testing')

# Simple HTML template for the home page
HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ApesTogether</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .info { margin-top: 20px; background: #f5f5f5; padding: 15px; border-radius: 5px; }
        .button { 
            display: inline-block; 
            background: #4CAF50; 
            color: white; 
            padding: 10px 20px; 
            text-decoration: none; 
            border-radius: 5px; 
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ApesTogether Stock Portfolio App</h1>
        
        <div class="info">
            <h2>Admin Access</h2>
            <p>If you are an admin user, you can access the admin panel here:</p>
            <a href="/admin-direct" class="button">Admin Access</a>
        </div>
        
        <div class="info">
            <h2>Environment Info:</h2>
            <p><strong>Time:</strong> {{ current_time }}</p>
            <p><strong>Environment:</strong> {{ environment }}</p>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Main landing page"""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    environment = os.environ.get('VERCEL_ENV', 'development')
    
    return render_template_string(HOME_HTML, 
                                current_time=current_time,
                                environment=environment)

@app.route('/admin-direct')
def admin_direct():
    """Direct admin access route"""
    # Get email from session or query parameter
    email = request.args.get('email', session.get('email', ''))
    
    # Store email in session if provided
    if email:
        session['email'] = email
    
    # Check if user is admin
    is_admin = (email == 'fordutilityapps@gmail.com')
    
    if is_admin:
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Dashboard</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .container { max-width: 800px; margin: 0 auto; }
                .success { background: #dff0d8; padding: 15px; border-radius: 5px; }
                .section { margin-top: 20px; background: #f5f5f5; padding: 15px; border-radius: 5px; }
                .button { 
                    display: inline-block; 
                    background: #4CAF50; 
                    color: white; 
                    padding: 10px 20px; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin-top: 20px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Admin Dashboard</h1>
                
                <div class="success">
                    <h2>Admin Access Granted</h2>
                    <p>Welcome, admin user {{ email }}.</p>
                </div>
                
                <div class="section">
                    <h2>Admin Functions</h2>
                    <p>The full admin functionality is being deployed. This is a temporary admin access page.</p>
                    <p>Please check back soon for the complete admin dashboard.</p>
                </div>
                
                <a href="/" class="button">Back to Home</a>
            </div>
        </body>
        </html>
        """, email=email)
    else:
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Admin Access</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .container { max-width: 800px; margin: 0 auto; }
                .error { background: #f2dede; padding: 15px; border-radius: 5px; }
                .form { margin-top: 20px; background: #f5f5f5; padding: 15px; border-radius: 5px; }
                .button { 
                    display: inline-block; 
                    background: #4CAF50; 
                    color: white; 
                    padding: 10px 20px; 
                    text-decoration: none; 
                    border-radius: 5px; 
                    margin-top: 20px;
                }
                input[type=text] {
                    width: 100%;
                    padding: 12px 20px;
                    margin: 8px 0;
                    box-sizing: border-box;
                }
                input[type=submit] {
                    background-color: #4CAF50;
                    color: white;
                    padding: 14px 20px;
                    margin: 8px 0;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Admin Access</h1>
                
                <div class="error">
                    <h2>Access Denied</h2>
                    <p>You must be logged in with the admin email to access this page.</p>
                </div>
                
                <div class="form">
                    <h2>Admin Login</h2>
                    <form action="/admin-direct" method="get">
                        <label for="email">Admin Email:</label>
                        <input type="text" id="email" name="email" placeholder="Enter admin email">
                        <input type="submit" value="Login">
                    </form>
                </div>
                
                <a href="/" class="button">Back to Home</a>
            </div>
        </body>
        </html>
        """)

# For local testing
if __name__ == '__main__':
    app.run(debug=True)
