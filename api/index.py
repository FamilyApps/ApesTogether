"""
Vercel serverless function handler for the Flask app.
This is a standalone version with admin access functionality.
"""
import os
from flask import Flask, render_template_string, redirect, url_for, request, session, flash
from datetime import datetime

# Create a Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-for-testing')

# Database connection string from environment variable
DATABASE_URL = os.environ.get('DATABASE_URL')

# Check if we're running on Vercel
VERCEL_ENV = os.environ.get('VERCEL_ENV')
if VERCEL_ENV:
    print(f"Running in Vercel environment: {VERCEL_ENV}")

# Admin email for authentication
ADMIN_EMAIL = 'fordutilityapps@gmail.com'

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
    is_admin = (email == ADMIN_EMAIL)
    
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
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:hover {background-color: #f5f5f5;}
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
            <p>Select an admin function below:</p>
            <a href="/admin-direct/users" class="button">View Users</a>
            <a href="/admin-direct/transactions" class="button">View Transactions</a>
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

# Admin routes for viewing users and transactions
@app.route('/admin-direct/users')
def admin_users():
    """Admin route to view users"""
    # Check if user is admin
    email = session.get('email', '')
    if email != ADMIN_EMAIL:
        return redirect(url_for('admin_direct'))
    
    # In a real app, we would query the database
    # For now, we'll use mock data
    users = [
        {'id': 1, 'username': 'witty-raven', 'email': 'fordutilityapps@gmail.com', 'is_admin': True},
        {'id': 2, 'username': 'user1', 'email': 'user1@example.com', 'is_admin': False},
        {'id': 3, 'username': 'user2', 'email': 'user2@example.com', 'is_admin': False}
    ]
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Admin - Users</title>
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
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:hover {background-color: #f5f5f5;}
    </style>
</head>
<body>
    <div class="container">
        <h1>Admin - Users</h1>
        
        <div class="section">
            <h2>User List</h2>
            <table>
                <tr>
                    <th>ID</th>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Admin</th>
                </tr>
                {% for user in users %}
                <tr>
                    <td>{{ user.id }}</td>
                    <td>{{ user.username }}</td>
                    <td>{{ user.email }}</td>
                    <td>{{ 'Yes' if user.is_admin else 'No' }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
        
        <a href="/admin-direct" class="button">Back to Admin</a>
        <a href="/" class="button">Back to Home</a>
    </div>
</body>
</html>
    """, users=users)

@app.route('/admin-direct/transactions')
def admin_transactions():
    """Admin route to view transactions"""
    # Check if user is admin
    email = session.get('email', '')
    if email != ADMIN_EMAIL:
        return redirect(url_for('admin_direct'))
    
    # In a real app, we would query the database
    # For now, we'll use mock data
    transactions = [
        {'id': 1, 'user_id': 1, 'stock': 'AAPL', 'quantity': 10, 'price': 150.00, 'type': 'buy', 'date': '2023-01-15'},
        {'id': 2, 'user_id': 1, 'stock': 'GOOGL', 'quantity': 5, 'price': 2500.00, 'type': 'buy', 'date': '2023-01-20'},
        {'id': 3, 'user_id': 2, 'stock': 'MSFT', 'quantity': 8, 'price': 300.00, 'type': 'buy', 'date': '2023-02-01'},
        {'id': 4, 'user_id': 1, 'stock': 'AAPL', 'quantity': 5, 'price': 160.00, 'type': 'sell', 'date': '2023-03-10'}
    ]
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Admin - Transactions</title>
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
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:hover {background-color: #f5f5f5;}
        .buy { color: green; }
        .sell { color: red; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Admin - Transactions</h1>
        
        <div class="section">
            <h2>Transaction List</h2>
            <table>
                <tr>
                    <th>ID</th>
                    <th>User ID</th>
                    <th>Stock</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Type</th>
                    <th>Date</th>
                </tr>
                {% for tx in transactions %}
                <tr>
                    <td>{{ tx.id }}</td>
                    <td>{{ tx.user_id }}</td>
                    <td>{{ tx.stock }}</td>
                    <td>{{ tx.quantity }}</td>
                    <td>${{ tx.price }}</td>
                    <td class="{{ tx.type }}">{{ tx.type }}</td>
                    <td>{{ tx.date }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
        
        <a href="/admin-direct" class="button">Back to Admin</a>
        <a href="/" class="button">Back to Home</a>
    </div>
</body>
</html>
    """, transactions=transactions)

# Add an error handler to provide more information on 500 errors
@app.errorhandler(500)
def server_error(e):
    # Log the error for debugging
    print(f"Server error: {str(e)}")
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Server Error</title>
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
                <h2>Server Error</h2>
                <p>Sorry, something went wrong on our server.</p>
                <p>Error details: {{ error }}</p>
            </div>
        </div>
    </body>
    </html>
    """, error=str(e)), 500

# For local testing
if __name__ == '__main__':
    app.run(debug=True, port=5000)
