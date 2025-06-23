#!/usr/bin/env python3
"""
Script to update the username for the admin account in production.
This script should be run in the production environment.
"""
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash

# Create a minimal Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///portfolio.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define a minimal User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)

def update_admin_username():
    """Update the username for the admin account"""
    with app.app_context():
        admin_email = 'fordutilityapps@gmail.com'
        new_username = 'proud-river'  # The desired username
        
        # Find the admin user
        admin_user = User.query.filter_by(email=admin_email).first()
        
        if admin_user:
            old_username = admin_user.username
            admin_user.username = new_username
            db.session.commit()
            print(f"Updated username for {admin_email} from '{old_username}' to '{new_username}'")
        else:
            print(f"No user found with email: {admin_email}")

if __name__ == "__main__":
    update_admin_username()
