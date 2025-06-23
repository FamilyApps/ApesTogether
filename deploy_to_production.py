#!/usr/bin/env python3
"""
Production deployment script for the stock portfolio app.
This script:
1. Runs database migrations
2. Cleans up development-only code
3. Prepares the app for production deployment
"""
import os
import sys
import logging
import importlib.util
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_migrations():
    """Run all migration scripts in the migrations directory"""
    logger.info("Running database migrations...")
    migrations_dir = Path("migrations")
    
    if not migrations_dir.exists() or not migrations_dir.is_dir():
        logger.error("Migrations directory not found")
        return False
    
    success = True
    for migration_file in sorted(migrations_dir.glob("*.py")):
        if migration_file.name == "__init__.py" or migration_file.name == "__pycache__":
            continue
            
        logger.info(f"Running migration: {migration_file.name}")
        try:
            # Import and run the migration script
            spec = importlib.util.spec_from_file_location("migration", migration_file)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            
            # If the script has a main function, run it
            if hasattr(migration, "main"):
                migration.main()
            # Otherwise, assume it runs automatically when imported
                
        except Exception as e:
            logger.error(f"Error running migration {migration_file.name}: {str(e)}")
            success = False
    
    return success

def backup_app_py():
    """Create a backup of app.py before modifying it"""
    try:
        with open("app.py", "r") as f:
            content = f.read()
        
        with open("app.py.bak", "w") as f:
            f.write(content)
            
        logger.info("Created backup of app.py at app.py.bak")
        return True
    except Exception as e:
        logger.error(f"Failed to backup app.py: {str(e)}")
        return False

def remove_dev_routes():
    """Remove development-only routes from app.py"""
    try:
        with open("app.py", "r") as f:
            lines = f.readlines()
        
        # Find the start and end of development-only routes
        dev_route_start = None
        dev_route_end = None
        
        for i, line in enumerate(lines):
            if "# Direct admin access route for development" in line:
                dev_route_start = i
            elif dev_route_start is not None and "# Development admin routes" in line:
                # Continue searching for the end
                continue
            elif dev_route_start is not None and i > dev_route_start and "if __name__ == '__main__':" in line:
                dev_route_end = i
                break
        
        if dev_route_start is not None and dev_route_end is not None:
            # Remove the development routes
            new_lines = lines[:dev_route_start] + lines[dev_route_end:]
            
            with open("app.py", "w") as f:
                f.writelines(new_lines)
                
            logger.info("Removed development-only routes from app.py")
            return True
        else:
            logger.warning("Could not find development routes in app.py")
            return False
            
    except Exception as e:
        logger.error(f"Failed to remove development routes: {str(e)}")
        return False

def update_flask_env():
    """Update FLASK_ENV to FLASK_DEBUG in app.py"""
    try:
        with open("app.py", "r") as f:
            content = f.read()
        
        # Replace FLASK_ENV with FLASK_DEBUG
        updated_content = content.replace("os.environ.get('FLASK_ENV')", "os.environ.get('FLASK_DEBUG')")
        
        with open("app.py", "w") as f:
            f.write(updated_content)
            
        logger.info("Updated FLASK_ENV to FLASK_DEBUG in app.py")
        return True
    except Exception as e:
        logger.error(f"Failed to update FLASK_ENV: {str(e)}")
        return False

def main():
    """Main deployment function"""
    logger.info("Starting production deployment process...")
    
    # Backup app.py before making changes
    if not backup_app_py():
        logger.error("Deployment aborted: Failed to backup app.py")
        return False
    
    # Run database migrations
    if not run_migrations():
        logger.warning("Some migrations may have failed")
    
    # Remove development-only routes
    if not remove_dev_routes():
        logger.warning("Failed to remove development routes")
    
    # Update FLASK_ENV to FLASK_DEBUG
    if not update_flask_env():
        logger.warning("Failed to update FLASK_ENV to FLASK_DEBUG")
    
    logger.info("Deployment preparation complete!")
    logger.info("Next steps:")
    logger.info("1. Review the changes to app.py")
    logger.info("2. Test the application locally")
    logger.info("3. Commit the changes to git")
    logger.info("4. Deploy to production")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
