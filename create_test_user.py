#!/usr/bin/env python3
"""
Script to create a test user with password authentication for local development.
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

def create_test_user(username, email, password):
    """Create a test user with password authentication"""
    with app.app_context():
        # Check if user already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        
        if existing_user:
            if existing_user.username == username:
                logger.info(f"User with username '{username}' already exists.")
                # Update password
                existing_user.password_hash = generate_password_hash(password)
                db.session.commit()
                logger.info(f"Updated password for user '{username}'")
                return existing_user
            else:
                logger.error(f"Email '{email}' is already in use by another user.")
                return None
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        logger.info(f"Created test user: {username} (ID: {new_user.id})")
        return new_user

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
        user = create_test_user(username, email, password)
        if user:
            print("\n==== TEST USER CREATED ====")
            print(f"Username: {user.username}")
            print(f"Email: {user.email}")
            print(f"Password: {password}")
            print("==========================\n")
            print("You can now log in with these credentials at http://127.0.0.1:5005/login")
    except Exception as e:
        logger.error(f"Error creating test user: {str(e)}")
        sys.exit(1)
