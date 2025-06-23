#!/bin/bash
# Production deployment script for stock portfolio app
# This script handles the deployment process to production

set -e  # Exit on error

echo "=== Stock Portfolio App Production Deployment ==="
echo "Starting deployment process..."

# 1. Backup current state
echo "Creating backup..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p backups
tar -czf "backups/backup_${TIMESTAMP}.tar.gz" --exclude="backups" --exclude="venv" --exclude="__pycache__" --exclude=".git" .
echo "Backup created at backups/backup_${TIMESTAMP}.tar.gz"

# 2. Run the deployment preparation script
echo "Running deployment preparation..."
python3 deploy_to_production.py

# 3. Run database migrations
echo "Running database migrations..."
python3 migrations/create_stock_transaction_table.py

# 4. Run tests (if available)
if [ -d "tests" ]; then
  echo "Running tests..."
  python3 -m pytest tests/
else
  echo "No tests directory found, skipping tests."
fi

# 5. Set environment to production
export FLASK_DEBUG=false

echo "=== Deployment preparation complete ==="
echo ""
echo "Next steps for production deployment:"
echo "1. Commit changes to version control"
echo "2. Push to production server"
echo "3. Set up environment variables on production server"
echo "4. Restart the application server"
echo ""
echo "For detailed instructions, see PRODUCTION_DEPLOYMENT.md"
