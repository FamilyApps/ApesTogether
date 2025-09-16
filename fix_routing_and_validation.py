#!/usr/bin/env python3
"""
Fix routing configuration issues and validate all model attributes
This script addresses the 404 errors on admin endpoints and model mismatches
"""
import os
import sys
import re
from pathlib import Path

def diagnose_routing_issues():
    """Diagnose why admin endpoints return 404 errors"""
    print("🔍 Diagnosing routing configuration issues...")
    
    # Check if the admin endpoints are properly defined
    api_index_path = Path("api/index.py")
    if not api_index_path.exists():
        print("❌ api/index.py not found")
        return False
    
    with open(api_index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for admin endpoint definitions
    admin_endpoints = [
        '/admin/populate-stock-metadata',
        '/admin/populate-leaderboard',
        '/admin/debug',
        '/health',
        '/api/health'
    ]
    
    found_endpoints = []
    missing_endpoints = []
    
    for endpoint in admin_endpoints:
        pattern = rf"@app\.route\(['\"]({re.escape(endpoint)})['\"]"
        if re.search(pattern, content):
            found_endpoints.append(endpoint)
        else:
            missing_endpoints.append(endpoint)
    
    print(f"✅ Found endpoints: {found_endpoints}")
    if missing_endpoints:
        print(f"❌ Missing endpoints: {missing_endpoints}")
    
    # Check for import errors in stock_metadata_utils
    if 'from stock_metadata_utils import' in content:
        print("✅ stock_metadata_utils import found")
        
        # Check if the file exists
        metadata_utils_path = Path("stock_metadata_utils.py")
        if metadata_utils_path.exists():
            print("✅ stock_metadata_utils.py exists")
            
            # Check for syntax errors
            try:
                with open(metadata_utils_path, 'r', encoding='utf-8') as f:
                    metadata_content = f.read()
                
                # Look for potential import issues
                if 'from models import' in metadata_content:
                    print("⚠️  Direct model imports found in stock_metadata_utils.py")
                    print("   This could cause circular import issues")
                
                compile(metadata_content, str(metadata_utils_path), 'exec')
                print("✅ stock_metadata_utils.py syntax is valid")
            except SyntaxError as e:
                print(f"❌ Syntax error in stock_metadata_utils.py: {e}")
                return False
        else:
            print("❌ stock_metadata_utils.py not found")
            return False
    
    return len(missing_endpoints) == 0

def validate_all_model_attributes():
    """Validate all model attribute usage across the codebase"""
    print("\n🔍 Validating model attributes...")
    
    # Define the actual model attributes from models.py
    model_attributes = {
        'User': ['id', 'email', 'username', 'password_hash', 'oauth_provider', 'oauth_id', 
                'stripe_price_id', 'subscription_price', 'stripe_customer_id'],
        'Stock': ['id', 'ticker', 'quantity', 'purchase_price', 'purchase_date', 'user_id'],
        'Transaction': ['id', 'user_id', 'ticker', 'quantity', 'price', 'transaction_type', 'timestamp', 'notes'],
        'StockInfo': ['id', 'ticker', 'company_name', 'market_cap', 'cap_classification', 'sector', 
                     'industry', 'naics_code', 'exchange', 'country', 'is_active', 'last_updated', 'created_at'],
        'PortfolioSnapshot': ['id', 'user_id', 'date', 'total_value', 'cash_flow', 'created_at'],
        'Subscription': ['id', 'subscriber_id', 'subscribed_to_id', 'stripe_subscription_id', 'status', 'created_at'],
        'LeaderboardCache': ['id', 'period', 'leaderboard_data', 'generated_at'],
        'UserPortfolioChartCache': ['id', 'user_id', 'period', 'chart_data', 'generated_at']
    }
    
    # Common attribute mismatches to check for
    attribute_mismatches = [
        ('Transaction', 'symbol', 'ticker'),
        ('Transaction', 'shares', 'quantity'),
        ('Transaction', 'date', 'timestamp'),
        ('Stock', 'symbol', 'ticker'),
        ('StockInfo', 'symbol', 'ticker')
    ]
    
    errors_found = []
    
    # Scan all Python files
    python_files = list(Path('.').rglob('*.py'))
    for py_file in python_files:
        if py_file.name in ['fix_routing_and_validation.py', 'validate_codebase.py']:
            continue
            
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for specific mismatches
            for model, wrong_attr, correct_attr in attribute_mismatches:
                pattern = rf'{model}\.{wrong_attr}\b'
                if re.search(pattern, content):
                    errors_found.append(f"{py_file}: {model}.{wrong_attr} should be {model}.{correct_attr}")
                
                # Also check in templates
                template_pattern = rf'{{\s*\w+\.{wrong_attr}\s*}}'
                if re.search(template_pattern, content):
                    errors_found.append(f"{py_file}: Template uses .{wrong_attr} should be .{correct_attr}")
        
        except Exception as e:
            print(f"⚠️  Could not read {py_file}: {e}")
    
    # Check HTML templates
    html_files = list(Path('.').rglob('*.html'))
    for html_file in html_files:
        try:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for template variable mismatches
            for model, wrong_attr, correct_attr in attribute_mismatches:
                pattern = rf'{{\s*\w+\.{wrong_attr}\s*}}'
                if re.search(pattern, content):
                    errors_found.append(f"{html_file}: Template uses .{wrong_attr} should be .{correct_attr}")
        
        except Exception as e:
            print(f"⚠️  Could not read {html_file}: {e}")
    
    if errors_found:
        print("❌ Model attribute errors found:")
        for error in errors_found:
            print(f"   {error}")
        return False
    else:
        print("✅ No model attribute mismatches found")
        return True

def check_template_usage():
    """Check for inline HTML usage instead of proper templates"""
    print("\n🔍 Checking template usage...")
    
    python_files = list(Path('.').rglob('*.py'))
    inline_html_found = []
    
    for py_file in python_files:
        if py_file.name in ['fix_routing_and_validation.py', 'validate_codebase.py']:
            continue
            
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line_num, line in enumerate(lines, 1):
                # Check for inline HTML
                if re.search(r'return.*render_template_string.*<html', line, re.IGNORECASE):
                    inline_html_found.append(f"{py_file}:{line_num}")
                elif re.search(r'return\s+[\'"]<html', line, re.IGNORECASE):
                    inline_html_found.append(f"{py_file}:{line_num}")
        
        except Exception as e:
            print(f"⚠️  Could not read {py_file}: {e}")
    
    if inline_html_found:
        print("⚠️  Inline HTML usage found (should use templates):")
        for location in inline_html_found:
            print(f"   {location}")
        return False
    else:
        print("✅ No problematic inline HTML usage found")
        return True

def main():
    """Run comprehensive validation and fixes"""
    print("🚀 Running routing and validation fixes...")
    
    success = True
    
    # 1. Diagnose routing issues
    if not diagnose_routing_issues():
        success = False
    
    # 2. Validate model attributes
    if not validate_all_model_attributes():
        success = False
    
    # 3. Check template usage
    if not check_template_usage():
        success = False
    
    if success:
        print("\n✅ All validations passed!")
    else:
        print("\n❌ Issues found that need to be fixed")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
