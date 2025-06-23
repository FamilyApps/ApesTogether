#!/usr/bin/env python3
"""
Standalone script to create an admin user in the database.
This bypasses the OAuth login for local development.
"""
import os
import sys
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
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

# Define minimal User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    profile_picture = db.Column(db.String(200))
    subscription_active = db.Column(db.Boolean, default=False)

def create_admin_user():
    """Create or update the admin user"""
    with app.app_context():
        admin_email = 'fordutilityapps@gmail.com'
        
        # Check if admin user exists
        admin_user = User.query.filter_by(email=admin_email).first()
        
        if admin_user:
            logger.info(f"Admin user already exists with ID: {admin_user.id}")
        else:
            # Create admin user
            admin_user = User(
                username='Admin',
                email=admin_email,
                profile_picture='https://via.placeholder.com/150',
                subscription_active=True
            )
            db.session.add(admin_user)
            db.session.commit()
            logger.info(f"Created admin user with ID: {admin_user.id}")
        
        print("\n==== ADMIN USER INFO ====")
        print(f"ID: {admin_user.id}")
        print(f"Username: {admin_user.username}")
        print(f"Email: {admin_user.email}")
        print(f"Subscription active: {admin_user.subscription_active}")
        print("========================\n")
        
        print("To access the admin interface:")
        print("1. Start the Flask app with: python3 app.py")
        print("2. Log in with Google using the admin email: fordutilityapps@gmail.com")
        print("3. Access the admin interface at: http://127.0.0.1:5005/admin")

if __name__ == "__main__":
    try:
        create_admin_user()
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")
        sys.exit(1)
