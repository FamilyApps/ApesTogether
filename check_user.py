#!/usr/bin/env python3
"""
Script to check user details in the database and verify password hashing.
"""
import os
import sys
import sqlite3
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
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

def check_user_in_db():
    """Check user details directly in the database"""
    try:
        # Connect to SQLite database
        conn = sqlite3.connect('portfolio.db')
        cursor = conn.cursor()
        
        # Get all users
        cursor.execute("SELECT * FROM user")
        users = cursor.fetchall()
        
        # Get column names
        column_names = [description[0] for description in cursor.description]
        
        print("\n==== ALL USERS IN DATABASE ====")
        for user in users:
            print("\nUser Record:")
            for i, col in enumerate(column_names):
                print(f"  {col}: {user[i]}")
        
        # Close connection
        conn.close()
    except Exception as e:
        print(f"Error accessing database directly: {str(e)}")

def verify_user_login(username, password):
    """Verify if login would work with given credentials"""
    with app.app_context():
        # Try to find user by username
        user = User.query.filter_by(username=username).first()
        
        if not user:
            print(f"\nNo user found with username: {username}")
            return False
        
        print("\n==== USER DETAILS ====")
        print(f"ID: {user.id}")
        print(f"Username: {user.username}")
        print(f"Email: {user.email}")
        print(f"Has password_hash: {'Yes' if user.password_hash else 'No'}")
        
        if user.password_hash:
            is_valid = check_password_hash(user.password_hash, password)
            print(f"Password valid: {is_valid}")
            return is_valid
        else:
            print("User has no password hash set")
            return False

def create_or_update_user(username, email, password):
    """Create or update a user with password authentication"""
    with app.app_context():
        # Check if user already exists
        user = User.query.filter((User.username == username) | (User.email == email)).first()
        
        if user:
            print(f"\nUpdating existing user: {user.username} (ID: {user.id})")
            # Update password with a new hash
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            print(f"Updated password hash: {user.password_hash[:20]}...")
        else:
            # Create new user
            new_user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password)
            )
            db.session.add(new_user)
            db.session.commit()
            print(f"\nCreated new user: {new_user.username} (ID: {new_user.id})")
            print(f"Password hash: {new_user.password_hash[:20]}...")
            user = new_user
        
        # Verify the password works
        is_valid = check_password_hash(user.password_hash, password)
        print(f"Password verification test: {'Success' if is_valid else 'Failed'}")
        
        return user

if __name__ == "__main__":
    # Default values
    default_username = "testuser"
    default_email = "test@example.com"
    default_password = "password123"
    
    # Get values from command line arguments or use defaults
    username = sys.argv[1] if len(sys.argv) > 1 else default_username
    email = sys.argv[2] if len(sys.argv) > 2 else default_email
    password = sys.argv[3] if len(sys.argv) > 3 else default_password
    
    try:
        print("\n=== CHECKING DATABASE DIRECTLY ===")
        check_user_in_db()
        
        print("\n=== VERIFYING LOGIN ===")
        verify_user_login(username, password)
        
        print("\n=== CREATING/UPDATING USER ===")
        user = create_or_update_user(username, email, password)
        
        print("\n=== FINAL VERIFICATION ===")
        verify_user_login(username, password)
        
        print("\nYou can now try to log in with:")
        print(f"Username: {username}")
        print(f"Password: {password}")
        print("at http://127.0.0.1:5005/login")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)
