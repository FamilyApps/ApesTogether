#!/usr/bin/env python3
"""
Quick fix for admin access in production.
This script updates the admin_interface.py file to use FLASK_DEBUG instead of FLASK_ENV.
"""
import os
import sys

def fix_admin_interface():
    """Update admin_interface.py to use FLASK_DEBUG instead of FLASK_ENV"""
    try:
        # Read the current file
        with open('admin_interface.py', 'r') as f:
            content = f.read()
        
        # Replace FLASK_ENV with FLASK_DEBUG
        updated_content = content.replace("os.environ.get('FLASK_ENV')", "os.environ.get('FLASK_DEBUG')")
        
        # Write the updated content
        with open('admin_interface.py', 'w') as f:
            f.write(updated_content)
        
        print("Successfully updated admin_interface.py to use FLASK_DEBUG")
        return True
    except Exception as e:
        print(f"Error updating admin_interface.py: {str(e)}")
        return False

if __name__ == "__main__":
    if fix_admin_interface():
        print("Fix applied successfully. Commit and deploy these changes.")
    else:
        sys.exit(1)
