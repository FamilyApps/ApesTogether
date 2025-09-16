#!/usr/bin/env python3
"""
Debug script to test admin route accessibility and diagnose 404 errors
"""
import sys
import os
from pathlib import Path

def check_route_definitions():
    """Check if admin routes are properly defined in the Flask app"""
    print("🔍 Checking admin route definitions...")
    
    api_index_path = Path("api/index.py")
    if not api_index_path.exists():
        print("❌ api/index.py not found")
        return False
    
    with open(api_index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Critical admin routes to check
    admin_routes = [
        ('/admin/populate-stock-metadata', 'admin_populate_stock_metadata'),
        ('/admin/populate-leaderboard', 'admin_populate_leaderboard'),
        ('/admin/debug', 'admin_debug'),
        ('/health', 'root_health_check'),
        ('/api/health', 'health_check')
    ]
    
    found_routes = []
    missing_routes = []
    
    for route_path, function_name in admin_routes:
        # Check for route decorator
        route_pattern = f"@app.route('{route_path}')"
        function_pattern = f"def {function_name}("
        
        has_route = route_pattern in content
        has_function = function_pattern in content
        
        if has_route and has_function:
            found_routes.append((route_path, function_name))
            print(f"✅ Found: {route_path} -> {function_name}")
        else:
            missing_routes.append((route_path, function_name))
            print(f"❌ Missing: {route_path} -> {function_name} (route: {has_route}, func: {has_function})")
    
    return len(missing_routes) == 0

def check_import_issues():
    """Check for import issues that could cause 404s"""
    print("\n🔍 Checking for import issues...")
    
    # Check stock_metadata_utils import
    api_index_path = Path("api/index.py")
    with open(api_index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'from stock_metadata_utils import' in content:
        print("✅ stock_metadata_utils import found in api/index.py")
        
        # Check if the file exists and has no syntax errors
        metadata_utils_path = Path("stock_metadata_utils.py")
        if metadata_utils_path.exists():
            print("✅ stock_metadata_utils.py exists")
            
            try:
                with open(metadata_utils_path, 'r', encoding='utf-8') as f:
                    metadata_content = f.read()
                
                # Check for potential circular import issues
                if 'from models import' in metadata_content and not 'def ' in metadata_content.split('from models import')[1].split('\n')[0]:
                    print("⚠️  Potential circular import: direct model imports at module level")
                    print("   Recommendation: Move imports inside functions")
                else:
                    print("✅ No obvious circular import issues")
                
                # Try to compile the file
                compile(metadata_content, str(metadata_utils_path), 'exec')
                print("✅ stock_metadata_utils.py syntax is valid")
                
            except SyntaxError as e:
                print(f"❌ Syntax error in stock_metadata_utils.py: {e}")
                return False
            except Exception as e:
                print(f"⚠️  Other issue with stock_metadata_utils.py: {e}")
        else:
            print("❌ stock_metadata_utils.py not found")
            return False
    
    return True

def check_deployment_config():
    """Check deployment configuration files"""
    print("\n🔍 Checking deployment configuration...")
    
    # Check for deployment files
    deployment_files = [
        'Procfile',
        'requirements.txt',
        'app.py',
        'vercel.json',
        'netlify.toml'
    ]
    
    for file_name in deployment_files:
        file_path = Path(file_name)
        if file_path.exists():
            print(f"✅ Found: {file_name}")
        else:
            print(f"⚠️  Missing: {file_name}")
    
    # Check if app.py imports api/index.py correctly
    app_py_path = Path("app.py")
    if app_py_path.exists():
        with open(app_py_path, 'r', encoding='utf-8') as f:
            app_content = f.read()
        
        if 'from api.index import app' in app_content or 'from api import index' in app_content:
            print("✅ app.py imports api correctly")
        else:
            print("⚠️  app.py may not be importing api correctly")
    
    return True

def check_template_issues():
    """Check for template-related issues that could cause errors"""
    print("\n🔍 Checking template usage...")
    
    # Count render_template_string usage (should be minimized)
    api_index_path = Path("api/index.py")
    with open(api_index_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    render_template_string_count = content.count('render_template_string')
    render_template_count = content.count('render_template(')
    
    print(f"📊 Template usage statistics:")
    print(f"   render_template_string: {render_template_string_count} (should be minimal)")
    print(f"   render_template: {render_template_count} (preferred)")
    
    if render_template_string_count > 10:
        print("⚠️  High usage of render_template_string - consider using proper templates")
    
    return True

def main():
    """Run comprehensive admin route diagnostics"""
    print("🚀 Running admin route diagnostics...")
    
    success = True
    
    # 1. Check route definitions
    if not check_route_definitions():
        success = False
    
    # 2. Check import issues
    if not check_import_issues():
        success = False
    
    # 3. Check deployment config
    if not check_deployment_config():
        success = False
    
    # 4. Check template issues
    if not check_template_issues():
        success = False
    
    print(f"\n{'✅ All checks passed!' if success else '❌ Issues found that need attention'}")
    
    if not success:
        print("\n🔧 Recommended fixes:")
        print("1. Ensure all admin routes are properly defined with @app.route decorators")
        print("2. Fix any import issues in stock_metadata_utils.py")
        print("3. Verify deployment configuration is correct")
        print("4. Consider replacing render_template_string with proper templates")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
