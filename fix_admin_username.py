#!/usr/bin/env python3
"""
Script to update the admin username in production.
This script should be deployed and run in the production environment.
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

# Load database configuration from environment
database_url = os.environ.get('DATABASE_URL')
if not database_url:
    logger.error("DATABASE_URL environment variable not set")
    sys.exit(1)

# Vercel/Neon uses postgres://, but SQLAlchemy needs postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define a minimal User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)

def update_admin_username():
    """Update the username for the admin account in production"""
    with app.app_context():
        admin_email = 'fordutilityapps@gmail.com'
        new_username = 'proud-river'  # The desired username
        
        # Find the admin user
        admin_user = User.query.filter_by(email=admin_email).first()
        
        if admin_user:
            old_username = admin_user.username
            admin_user.username = new_username
            db.session.commit()
            logger.info(f"Updated username for {admin_email} from '{old_username}' to '{new_username}'")
            return True
        else:
            logger.error(f"No user found with email: {admin_email}")
            return False

if __name__ == "__main__":
    try:
        if update_admin_username():
            print("Admin username updated successfully in production")
        else:
            sys.exit(1)
    except Exception as e:
        logger.error(f"Error updating admin username: {str(e)}")
        sys.exit(1)
