#!/usr/bin/env python3
"""
Script to create an admin user directly in the database and add a direct admin access route.
"""
import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create a minimal Flask app
app = Flask(__name__)

# Load database configuration from environment or use SQLite
database_url = os.environ.get('DATABASE_URL', 'sqlite:///portfolio.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Define User model matching the one in app.py
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True)
    oauth_provider = db.Column(db.String(20))
    oauth_id = db.Column(db.String(100))
    stripe_price_id = db.Column(db.String(255), nullable=True)
    subscription_price = db.Column(db.Float, nullable=True)
    stripe_customer_id = db.Column(db.String(255), nullable=True)

def create_admin_user():
    """Create an admin user with the correct email"""
    with app.app_context():
        admin_email = 'fordutilityapps@gmail.com'
        admin_username = 'admin'
        admin_password = 'admin123'  # Simple password for development
        
        # Check if admin user exists
        admin_user = User.query.filter_by(email=admin_email).first()
        
        if admin_user:
            print(f"\nAdmin user already exists with ID: {admin_user.id}")
            # Update password
            admin_user.password_hash = generate_password_hash(admin_password)
            db.session.commit()
            print(f"Updated password for admin user")
        else:
            # Create admin user
            admin_user = User(
                username=admin_username,
                email=admin_email,
                password_hash=generate_password_hash(admin_password)
            )
            db.session.add(admin_user)
            db.session.commit()
            print(f"\nCreated admin user with ID: {admin_user.id}")
        
        print("\n==== ADMIN USER INFO ====")
        print(f"ID: {admin_user.id}")
        print(f"Username: {admin_user.username}")
        print(f"Email: {admin_user.email}")
        print("========================\n")
        
        return admin_user

def add_direct_admin_access():
    """Add a direct admin access route to app.py"""
    app_path = 'app.py'
    
    # Read the current app.py content
    with open(app_path, 'r') as f:
        content = f.read()
    
    # Check if the direct access route already exists
    if "def direct_admin_access():" in content:
        print("Direct admin access route already exists in app.py")
        return
    
    # Find a good place to insert the route (before the if __name__ == '__main__' block)
    insert_marker = "if __name__ == '__main__':"
    if insert_marker not in content:
        print("Could not find a suitable place to insert the direct admin access route")
        return
    
    # Create the direct admin access route
    direct_access_route = """
# Direct admin access route for development
@app.route('/dev-admin')
def direct_admin_access():
    \"\"\"Development-only route to access admin interface directly\"\"\"
    if os.environ.get('FLASK_ENV') != 'development':
        abort(404)  # Only available in development
    
    # Find the admin user
    admin_user = User.query.filter_by(email='fordutilityapps@gmail.com').first()
    if not admin_user:
        flash('Admin user not found. Please run create_admin_direct.py first.', 'danger')
        return redirect(url_for('index'))
    
    # Log in as admin
    login_user(admin_user)
    flash('Logged in as admin for development purposes', 'success')
    
    # Redirect to admin interface
    return redirect(url_for('admin.index'))
"""
    
    # Insert the route before the if __name__ == '__main__' block
    modified_content = content.replace(insert_marker, direct_access_route + "\n\n" + insert_marker)
    
    # Write the modified content back to app.py
    with open(app_path, 'w') as f:
        f.write(modified_content)
    
    print("Added direct admin access route to app.py")
    print("You can now access the admin interface directly at: http://127.0.0.1:5005/dev-admin")

if __name__ == "__main__":
    try:
        admin_user = create_admin_user()
        add_direct_admin_access()
        
        print("\nSetup complete!")
        print("To access the admin interface:")
        print("1. Restart the Flask app with: export FLASK_ENV=development && python3 app.py")
        print("2. Go directly to: http://127.0.0.1:5005/dev-admin")
        print("This will automatically log you in as the admin user")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)
