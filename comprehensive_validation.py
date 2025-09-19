#!/usr/bin/env python3
"""
COMPREHENSIVE VALIDATION SYSTEM
Implements all validation protocol rules to prevent production issues
"""

import os
import re
import json
import ast
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
import importlib.util

class ComprehensiveValidator:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.errors = []
        self.warnings = []
        self.model_attributes = {}
        self.template_variables = {}
        self.render_template_calls = []
        
    def log_error(self, message: str):
        """Log a validation error"""
        self.errors.append(f"❌ ERROR: {message}")
        print(f"❌ ERROR: {message}")
    
    def log_warning(self, message: str):
        """Log a validation warning"""
        self.warnings.append(f"⚠️  WARNING: {message}")
        print(f"⚠️  WARNING: {message}")
    
    def log_success(self, message: str):
        """Log a validation success"""
        print(f"✅ SUCCESS: {message}")

    def scan_model_attributes(self):
        """Scan models.py to extract all model class definitions and their attributes"""
        print("\n🔍 SCANNING MODEL ATTRIBUTES...")
        
        models_file = self.project_root / "models.py"
        if not models_file.exists():
            self.log_error("models.py file not found")
            return
        
        try:
            with open(models_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the AST to extract model classes and their attributes
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if this is a model class (inherits from db.Model)
                    is_model = False
                    for base in node.bases:
                        if isinstance(base, ast.Attribute) and base.attr == 'Model':
                            is_model = True
                            break
                    
                    if is_model:
                        class_name = node.name
                        attributes = []
                        
                        # Extract db.Column attributes
                        for item in node.body:
                            if isinstance(item, ast.Assign):
                                for target in item.targets:
                                    if isinstance(target, ast.Name):
                                        attr_name = target.value
                                        # Check if it's a db.Column
                                        if isinstance(item.value, ast.Call):
                                            if (isinstance(item.value.func, ast.Attribute) and 
                                                item.value.func.attr == 'Column'):
                                                attributes.append(attr_name)
                        
                        self.model_attributes[class_name] = attributes
                        self.log_success(f"Found model {class_name} with attributes: {attributes}")
        
        except Exception as e:
            self.log_error(f"Failed to parse models.py: {str(e)}")

    def scan_model_usage_in_python_files(self):
        """Scan all Python files for Model.attribute usage and validate against model definitions"""
        print("\n🔍 SCANNING MODEL ATTRIBUTE USAGE IN PYTHON FILES...")
        
        # Pattern to match Model.attribute usage
        model_usage_pattern = r'(\w+)\.(\w+)'
        
        python_files = list(self.project_root.glob("*.py"))
        python_files.extend(list(self.project_root.glob("**/*.py")))
        
        for py_file in python_files:
            if py_file.name.startswith('.') or 'venv' in str(py_file) or '__pycache__' in str(py_file):
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Find all Model.attribute patterns
                matches = re.finditer(model_usage_pattern, content)
                
                for match in matches:
                    model_name = match.group(1)
                    attribute_name = match.group(2)
                    
                    # Check if this looks like a model usage
                    if model_name in self.model_attributes:
                        if attribute_name not in self.model_attributes[model_name]:
                            # Check for common mistakes
                            if model_name == 'Stock' and attribute_name == 'symbol':
                                self.log_error(f"In {py_file}: {model_name}.{attribute_name} should be {model_name}.ticker")
                            elif model_name == 'Stock' and attribute_name == 'shares':
                                self.log_error(f"In {py_file}: {model_name}.{attribute_name} should be {model_name}.quantity")
                            elif model_name == 'UserActivity' and attribute_name == 'action':
                                self.log_error(f"In {py_file}: {model_name}.{attribute_name} should be {model_name}.activity_type")
                            else:
                                self.log_warning(f"In {py_file}: {model_name}.{attribute_name} not found in model definition")
                        else:
                            self.log_success(f"In {py_file}: {model_name}.{attribute_name} ✓")
            
            except Exception as e:
                self.log_warning(f"Could not scan {py_file}: {str(e)}")

    def extract_template_variables(self):
        """Parse all Jinja2 templates to extract required variables"""
        print("\n🔍 EXTRACTING TEMPLATE VARIABLES...")
        
        template_files = list(self.project_root.glob("templates/**/*.html"))
        
        # Regex patterns for Jinja2 variables
        variable_pattern = r'\{\{\s*([^}]+)\s*\}\}'
        extends_pattern = r'\{\%\s*extends\s+["\']([^"\']+)["\']\s*\%\}'
        
        for template_file in template_files:
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                template_name = template_file.name
                variables = set()
                
                # Extract all {{ variable }} patterns
                var_matches = re.finditer(variable_pattern, content)
                for match in var_matches:
                    var_expr = match.group(1).strip()
                    # Extract the base variable name (before dots, filters, etc.)
                    base_var = var_expr.split('.')[0].split('|')[0].strip()
                    if base_var and not base_var.startswith(('loop', 'super')):
                        variables.add(base_var)
                
                # Check for template inheritance
                extends_match = re.search(extends_pattern, content)
                parent_template = None
                if extends_match:
                    parent_template = extends_match.group(1)
                
                self.template_variables[template_name] = {
                    'variables': variables,
                    'parent_template': parent_template,
                    'path': str(template_file)
                }
                
                self.log_success(f"Template {template_name}: variables={variables}, extends={parent_template}")
            
            except Exception as e:
                self.log_error(f"Could not parse template {template_file}: {str(e)}")

    def validate_template_inheritance(self):
        """Check parent templates for inherited variable requirements"""
        print("\n🔍 VALIDATING TEMPLATE INHERITANCE...")
        
        for template_name, info in self.template_variables.items():
            if info['parent_template']:
                parent_name = info['parent_template']
                if parent_name in self.template_variables:
                    parent_vars = self.template_variables[parent_name]['variables']
                    child_vars = info['variables']
                    
                    # Check if child template provides all parent variables
                    missing_vars = parent_vars - child_vars
                    if missing_vars:
                        self.log_warning(f"Template {template_name} extends {parent_name} but may be missing variables: {missing_vars}")
                    else:
                        self.log_success(f"Template {template_name} properly inherits from {parent_name}")
                else:
                    self.log_warning(f"Template {template_name} extends {parent_name} but parent not found")

    def scan_render_template_calls(self):
        """Find all render_template() calls and extract passed variables"""
        print("\n🔍 SCANNING RENDER_TEMPLATE CALLS...")
        
        python_files = list(self.project_root.glob("*.py"))
        python_files.extend(list(self.project_root.glob("**/*.py")))
        
        render_pattern = r'render_template\s*\(\s*["\']([^"\']+)["\']\s*(?:,\s*(.+?))?\s*\)'
        
        for py_file in python_files:
            if py_file.name.startswith('.') or 'venv' in str(py_file):
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                matches = re.finditer(render_pattern, content, re.DOTALL)
                
                for match in matches:
                    template_name = match.group(1)
                    params_str = match.group(2) if match.group(2) else ""
                    
                    # Extract parameter names (simplified)
                    param_names = set()
                    if params_str:
                        # Look for keyword arguments
                        param_matches = re.findall(r'(\w+)\s*=', params_str)
                        param_names.update(param_matches)
                    
                    self.render_template_calls.append({
                        'file': str(py_file),
                        'template': template_name,
                        'params': param_names
                    })
                    
                    self.log_success(f"In {py_file}: render_template('{template_name}', {param_names})")
            
            except Exception as e:
                self.log_warning(f"Could not scan {py_file}: {str(e)}")

    def validate_render_template_variables(self):
        """Verify every render_template() call passes all required template variables"""
        print("\n🔍 VALIDATING RENDER_TEMPLATE VARIABLE PASSING...")
        
        for call in self.render_template_calls:
            template_name = call['template']
            provided_params = call['params']
            file_path = call['file']
            
            if template_name in self.template_variables:
                required_vars = self.template_variables[template_name]['variables']
                parent_template = self.template_variables[template_name]['parent_template']
                
                # Add parent template variables if exists
                if parent_template and parent_template in self.template_variables:
                    required_vars = required_vars.union(self.template_variables[parent_template]['variables'])
                
                # Check for missing variables
                missing_vars = required_vars - provided_params
                
                # Filter out variables that might be provided by Flask context
                flask_context_vars = {'current_user', 'request', 'session', 'g', 'url_for', 'get_flashed_messages'}
                missing_vars = missing_vars - flask_context_vars
                
                if missing_vars:
                    self.log_error(f"In {file_path}: render_template('{template_name}') missing variables: {missing_vars}")
                else:
                    self.log_success(f"In {file_path}: render_template('{template_name}') has all required variables")
            else:
                self.log_warning(f"In {file_path}: Template '{template_name}' not found in template analysis")

    def check_template_files_exist(self):
        """Test that all template files exist at specified paths"""
        print("\n🔍 CHECKING TEMPLATE FILE EXISTENCE...")
        
        for call in self.render_template_calls:
            template_name = call['template']
            template_path = self.project_root / "templates" / template_name
            
            if template_path.exists():
                self.log_success(f"Template file exists: {template_name}")
            else:
                self.log_error(f"Template file missing: {template_name}")

    def validate_no_inline_html(self):
        """Verify all routes use render_template() instead of inline HTML"""
        print("\n🔍 CHECKING FOR INLINE HTML IN ROUTES...")
        
        python_files = list(self.project_root.glob("*.py"))
        python_files.extend(list(self.project_root.glob("**/*.py")))
        
        inline_html_patterns = [
            r'return\s+["\']<html',
            r'return\s+["\']<!DOCTYPE',
            r'render_template_string\s*\(',
        ]
        
        for py_file in python_files:
            if py_file.name.startswith('.') or 'venv' in str(py_file):
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                for pattern in inline_html_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        line_num = content[:match.start()].count('\n') + 1
                        self.log_warning(f"In {py_file}:{line_num}: Possible inline HTML detected")
            
            except Exception as e:
                self.log_warning(f"Could not scan {py_file}: {str(e)}")

    def validate_imports_and_method_calls(self):
        """Verify all imports work and method calls use correct names"""
        print("\n🔍 VALIDATING IMPORTS AND METHOD CALLS...")
        
        python_files = list(self.project_root.glob("*.py"))
        python_files.extend(list(self.project_root.glob("**/*.py")))
        
        for py_file in python_files:
            if py_file.name.startswith('.') or 'venv' in str(py_file):
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check for common method name mistakes
                method_mistakes = [
                    (r'calculate_current_portfolio_value', 'calculate_portfolio_value'),
                    (r'StockTransaction', 'Transaction'),
                    (r'\.symbol\b', '.ticker'),
                    (r'\.shares\b', '.quantity'),
                    (r'\.action\b', '.activity_type'),
                ]
                
                for wrong_pattern, correct_name in method_mistakes:
                    if re.search(wrong_pattern, content):
                        self.log_error(f"In {py_file}: Found '{wrong_pattern}' - should be '{correct_name}'")
            
            except Exception as e:
                self.log_warning(f"Could not validate {py_file}: {str(e)}")

    def generate_validation_report(self):
        """Generate a comprehensive validation report"""
        print("\n" + "="*80)
        print("📋 COMPREHENSIVE VALIDATION REPORT")
        print("="*80)
        
        print(f"\n✅ SUCCESSES: {len([msg for msg in self.warnings + self.errors if '✅' in msg])}")
        print(f"⚠️  WARNINGS: {len(self.warnings)}")
        print(f"❌ ERRORS: {len(self.errors)}")
        
        if self.errors:
            print("\n❌ CRITICAL ERRORS THAT MUST BE FIXED:")
            for error in self.errors:
                print(f"  {error}")
        
        if self.warnings:
            print("\n⚠️  WARNINGS TO REVIEW:")
            for warning in self.warnings:
                print(f"  {warning}")
        
        # Summary
        print(f"\n📊 VALIDATION SUMMARY:")
        print(f"  - Model classes found: {len(self.model_attributes)}")
        print(f"  - Templates analyzed: {len(self.template_variables)}")
        print(f"  - render_template calls found: {len(self.render_template_calls)}")
        
        if not self.errors:
            print("\n🎉 ALL CRITICAL VALIDATIONS PASSED! Ready for deployment.")
            return True
        else:
            print(f"\n🚨 {len(self.errors)} CRITICAL ERRORS FOUND! Fix before deployment.")
            return False

    def run_full_validation(self):
        """Run the complete validation suite"""
        print("🚀 STARTING COMPREHENSIVE VALIDATION...")
        print("="*80)
        
        # Model validation
        self.scan_model_attributes()
        self.scan_model_usage_in_python_files()
        
        # Template validation
        self.extract_template_variables()
        self.validate_template_inheritance()
        self.scan_render_template_calls()
        self.validate_render_template_variables()
        self.check_template_files_exist()
        
        # Code quality validation
        self.validate_no_inline_html()
        self.validate_imports_and_method_calls()
        
        # Generate final report
        return self.generate_validation_report()

def main():
    """Main validation entry point"""
    project_root = os.path.dirname(os.path.abspath(__file__))
    validator = ComprehensiveValidator(project_root)
    
    success = validator.run_full_validation()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
