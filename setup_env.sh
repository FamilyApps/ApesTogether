#!/bin/bash
# Script to set up environment variables for the Stock Portfolio App

# Local environment setup
echo "Setting up local environment variables..."
cat > .env << EOL
# Stock Portfolio App Environment Variables
SECRET_KEY="$(openssl rand -hex 32)"
DATABASE_URL="postgresql://username:password@localhost:5432/stock_portfolio"
# Add other environment variables as needed
EOL

echo "Local .env file created with secure SECRET_KEY"
echo ""
echo "IMPORTANT: You need to update the DATABASE_URL in the .env file with your actual database credentials"
echo ""

# Instructions for Vercel setup
echo "===== VERCEL ENVIRONMENT SETUP INSTRUCTIONS ====="
echo "1. Go to the Vercel dashboard: https://vercel.com/dashboard"
echo "2. Select your project (apestogether.ai)"
echo "3. Go to Settings > Environment Variables"
echo "4. Add the following environment variables:"
echo "   - SECRET_KEY: $(openssl rand -hex 32)"
echo "   - DATABASE_URL: Your actual PostgreSQL connection string"
echo "5. Click 'Save' and redeploy your application"
echo ""
echo "NOTE: Make sure your DATABASE_URL is properly formatted for SQLAlchemy:"
echo "      If it starts with 'postgres://', change it to 'postgresql://'"
