#!/usr/bin/env python3
"""
Script to temporarily modify the admin_interface.py file to bypass admin check for local development.
This makes it easy to access the admin interface locally without dealing with OAuth.
"""
import os
import sys
import shutil
import re

ADMIN_INTERFACE_PATH = 'admin_interface.py'
BACKUP_PATH = 'admin_interface.py.bak'

def enable_local_admin():
    """Modify the admin_required decorator to allow any logged-in user"""
    # Check if we're in development mode
    if os.environ.get('FLASK_ENV') != 'development':
        print("This script should only be run in development mode.")
        print("Please set FLASK_ENV=development before running.")
        sys.exit(1)
    
    # Check if the file exists
    if not os.path.exists(ADMIN_INTERFACE_PATH):
        print(f"Error: {ADMIN_INTERFACE_PATH} not found.")
        sys.exit(1)
    
    # Create a backup if it doesn't exist
    if not os.path.exists(BACKUP_PATH):
        print(f"Creating backup of {ADMIN_INTERFACE_PATH} as {BACKUP_PATH}")
        shutil.copy2(ADMIN_INTERFACE_PATH, BACKUP_PATH)
    
    # Read the file
    with open(ADMIN_INTERFACE_PATH, 'r') as f:
        content = f.read()
    
    # Replace the admin_required decorator implementation
    original_decorator = r"""def admin_required\(f\):
    \"\"\"Decorator to check if user is an admin\"\"\"
    def decorated_function\(\*args, \*\*kwargs\):
        if not current_user\.is_authenticated or current_user\.email != 'fordutilityapps@gmail\.com':
            flash\('You must be an admin to access this page\.', 'danger'\)
            return redirect\(url_for\('index'\)\)
        return f\(\*args, \*\*kwargs\)
    decorated_function\.__name__ = f\.__name__
    return decorated_function"""
    
    dev_decorator = """def admin_required(f):
    \"\"\"Decorator to check if user is an admin (BYPASSED FOR LOCAL DEVELOPMENT)\"\"\"
    def decorated_function(*args, **kwargs):
        # In development mode, allow any authenticated user
        if os.environ.get('FLASK_ENV') == 'development':
            if not current_user.is_authenticated:
                flash('You must be logged in to access this page.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        # In production, check for admin email
        if not current_user.is_authenticated or current_user.email != 'fordutilityapps@gmail.com':
            flash('You must be an admin to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function"""
    
    # Add import os if it's not already there
    if "import os" not in content:
        content = content.replace("import stripe", "import os\nimport stripe")
    
    # Replace the decorator
    modified_content = re.sub(original_decorator, dev_decorator, content)
    
    if modified_content == content:
        print("No changes made. The admin_required decorator may have already been modified.")
        sys.exit(0)
    
    # Write the modified content back
    with open(ADMIN_INTERFACE_PATH, 'w') as f:
        f.write(modified_content)
    
    print("Successfully modified admin_interface.py to bypass admin check in development mode.")
    print("\nTo access the admin interface:")
    print("1. Start the Flask app with: export FLASK_ENV=development && python3 app.py")
    print("2. Log in with any user account")
    print("3. Access the admin interface at: http://127.0.0.1:5005/admin")
    print("\nTo restore the original file:")
    print(f"cp {BACKUP_PATH} {ADMIN_INTERFACE_PATH}")

def restore_original():
    """Restore the original admin_interface.py file from backup"""
    if not os.path.exists(BACKUP_PATH):
        print(f"Error: Backup file {BACKUP_PATH} not found.")
        sys.exit(1)
    
    shutil.copy2(BACKUP_PATH, ADMIN_INTERFACE_PATH)
    print(f"Restored original {ADMIN_INTERFACE_PATH} from {BACKUP_PATH}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--restore":
        restore_original()
    else:
        enable_local_admin()
