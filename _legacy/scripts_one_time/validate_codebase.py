#!/usr/bin/env python3
"""
Comprehensive codebase validation system
Validates model attributes, template variables, database schema, and imports
"""
import os
import re
import ast
import sys
import importlib.util
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
import json

class CodebaseValidator:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.errors = []
        self.warnings = []
        self.model_attributes = {}
        self.template_variables = {}
        self.route_templates = {}
        
    def log_error(self, message: str):
        self.errors.append(message)
        print(f"❌ ERROR: {message}")
    
    def log_warning(self, message: str):
        self.warnings.append(message)
        print(f"⚠️  WARNING: {message}")
    
    def log_success(self, message: str):
        print(f"✅ {message}")

    def extract_model_definitions(self) -> Dict[str, Dict[str, str]]:
        """Extract all model class definitions and their attributes"""
        print("\n🔍 Extracting model definitions...")
        
        models_file = self.project_root / "models.py"
        if not models_file.exists():
            self.log_error("models.py not found")
            return {}
        
        try:
            with open(models_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_name = node.name
                    attributes = {}
                    
                    # Extract db.Column attributes
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name):
                                    attr_name = target.id
                                    
                                    # Check if it's a db.Column
                                    if isinstance(item.value, ast.Call):
                                        if (isinstance(item.value.func, ast.Attribute) and 
                                            isinstance(item.value.func.value, ast.Name) and
                                            item.value.func.value.id == 'db' and
                                            item.value.func.attr == 'Column'):
                                            
                                            # Extract column type
                                            if item.value.args:
                                                col_type = ast.unparse(item.value.args[0])
                                                attributes[attr_name] = col_type
                                            else:
                                                attributes[attr_name] = "Unknown"
                    
                    if attributes:
                        self.model_attributes[class_name] = attributes
                        self.log_success(f"Found model {class_name} with {len(attributes)} attributes")
            
            return self.model_attributes
            
        except Exception as e:
            self.log_error(f"Failed to parse models.py: {str(e)}")
            return {}

    def scan_model_usage(self) -> Dict[str, List[Tuple[str, int, str]]]:
        """Scan all Python files for Model.attribute usage"""
        print("\n🔍 Scanning model attribute usage...")
        
        usage_patterns = {}
        python_files = list(self.project_root.rglob("*.py"))
        
        # Pattern to match Model.attribute usage
        model_attr_pattern = r'(\w+)\.(\w+)'
        
        for py_file in python_files:
            if py_file.name == 'validate_codebase.py':
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                for line_num, line in enumerate(lines, 1):
                    matches = re.finditer(model_attr_pattern, line)
                    for match in matches:
                        model_name = match.group(1)
                        attr_name = match.group(2)
                        
                        # Skip common non-model patterns
                        if model_name.lower() in ['self', 'db', 'app', 'os', 'sys', 'json', 're', 'time', 'datetime']:
                            continue
                        
                        # Check if this looks like a model usage
                        if model_name in self.model_attributes or model_name.endswith('Info') or model_name.endswith('Entry'):
                            key = f"{model_name}.{attr_name}"
                            if key not in usage_patterns:
                                usage_patterns[key] = []
                            
                            usage_patterns[key].append((str(py_file.relative_to(self.project_root)), line_num, line.strip()))
            
            except Exception as e:
                self.log_warning(f"Could not read {py_file}: {str(e)}")
        
        return usage_patterns

    def validate_model_attributes(self):
        """Validate all model attribute usage against definitions"""
        print("\n🔍 Validating model attributes...")
        
        model_definitions = self.extract_model_definitions()
        usage_patterns = self.scan_model_usage()
        
        validation_errors = 0
        
        for usage, locations in usage_patterns.items():
            model_name, attr_name = usage.split('.', 1)
            
            # Check if model exists
            if model_name not in model_definitions:
                # Only flag if it looks like a model class (capitalized)
                if model_name[0].isupper():
                    self.log_warning(f"Unknown model '{model_name}' used in {len(locations)} locations")
                continue
            
            # Check if attribute exists on model
            if attr_name not in model_definitions[model_name]:
                self.log_error(f"Model {model_name} has no attribute '{attr_name}'")
                validation_errors += 1
                
                for file_path, line_num, line_content in locations:
                    print(f"    📍 {file_path}:{line_num} - {line_content}")
                
                # Suggest similar attributes
                similar_attrs = [attr for attr in model_definitions[model_name].keys() 
                               if attr.lower().startswith(attr_name.lower()[:3])]
                if similar_attrs:
                    print(f"    💡 Similar attributes: {', '.join(similar_attrs)}")
            else:
                self.log_success(f"✓ {usage} - valid attribute")
        
        if validation_errors == 0:
            self.log_success("All model attributes are valid!")
        
        return validation_errors == 0

    def extract_template_variables(self) -> Dict[str, Set[str]]:
        """Extract all variables used in Jinja2 templates"""
        print("\n🔍 Extracting template variables...")
        
        template_files = list(self.project_root.rglob("*.html"))
        
        # Patterns for Jinja2 variables
        variable_pattern = r'\{\{\s*([^}]+)\s*\}\}'
        
        for template_file in template_files:
            try:
                with open(template_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                variables = set()
                
                # Extract {{ variable }} patterns
                for match in re.finditer(variable_pattern, content):
                    var_expr = match.group(1).strip()
                    
                    # Extract base variable name (before dots, filters, etc.)
                    base_var = var_expr.split('.')[0].split('|')[0].strip()
                    if base_var and not base_var.startswith('"') and not base_var.startswith("'"):
                        variables.add(base_var)
                
                template_name = str(template_file.relative_to(self.project_root))
                self.template_variables[template_name] = variables
                
                if variables:
                    self.log_success(f"Template {template_name}: {len(variables)} variables")
            
            except Exception as e:
                self.log_warning(f"Could not read template {template_file}: {str(e)}")
        
        return self.template_variables

    def extract_render_template_calls(self) -> Dict[str, Dict[str, Set[str]]]:
        """Extract all render_template calls and their passed variables"""
        print("\n🔍 Extracting render_template calls...")
        
        python_files = list(self.project_root.rglob("*.py"))
        render_calls = {}
        
        for py_file in python_files:
            if py_file.name == 'validate_codebase.py':
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Find render_template calls
                render_pattern = r'render_template\s*\(\s*[\'"]([^\'"]+)[\'"]([^)]*)\)'
                
                for match in re.finditer(render_pattern, content):
                    template_name = match.group(1)
                    args_str = match.group(2)
                    
                    # Extract keyword arguments
                    passed_vars = set()
                    if args_str.strip():
                        # Simple extraction of keyword arguments
                        kwarg_pattern = r'(\w+)\s*='
                        for kwarg_match in re.finditer(kwarg_pattern, args_str):
                            passed_vars.add(kwarg_match.group(1))
                    
                    file_key = str(py_file.relative_to(self.project_root))
                    if file_key not in render_calls:
                        render_calls[file_key] = {}
                    
                    render_calls[file_key][template_name] = passed_vars
            
            except Exception as e:
                self.log_warning(f"Could not read {py_file}: {str(e)}")
        
        return render_calls

    def validate_template_variables(self):
        """Validate that all template variables are passed by render_template calls"""
        print("\n🔍 Validating template variables...")
        
        template_vars = self.extract_template_variables()
        render_calls = self.extract_render_template_calls()
        
        validation_errors = 0
        
        # Check each template
        for template_name, required_vars in template_vars.items():
            if not required_vars:
                continue
                
            # Find render_template calls for this template
            template_calls = []
            for file_path, calls in render_calls.items():
                for called_template, passed_vars in calls.items():
                    if called_template == template_name or called_template == template_name.replace('templates/', ''):
                        template_calls.append((file_path, passed_vars))
            
            if not template_calls:
                self.log_warning(f"Template {template_name} not found in any render_template calls")
                continue
            
            # Check each call
            for file_path, passed_vars in template_calls:
                missing_vars = required_vars - passed_vars
                if missing_vars:
                    self.log_error(f"Template {template_name} missing variables: {', '.join(missing_vars)}")
                    self.log_error(f"    Called from: {file_path}")
                    validation_errors += 1
                else:
                    self.log_success(f"✓ {template_name} - all variables provided")
        
        return validation_errors == 0

    def check_inline_html_usage(self):
        """Check for inline HTML instead of render_template usage"""
        print("\n🔍 Checking for inline HTML usage...")
        
        python_files = list(self.project_root.rglob("*.py"))
        inline_html_found = False
        
        for py_file in python_files:
            if py_file.name == 'validate_codebase.py':
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                for line_num, line in enumerate(lines, 1):
                    # Check for inline HTML patterns
                    if re.search(r'return\s+[\'"]<html', line, re.IGNORECASE):
                        self.log_error(f"Inline HTML found in {py_file.relative_to(self.project_root)}:{line_num}")
                        inline_html_found = True
                    elif re.search(r'render_template_string\s*\(', line):
                        self.log_warning(f"render_template_string usage in {py_file.relative_to(self.project_root)}:{line_num}")
            
            except Exception as e:
                self.log_warning(f"Could not read {py_file}: {str(e)}")
        
        if not inline_html_found:
            self.log_success("No inline HTML usage found!")
        
        return not inline_html_found

    def validate_imports(self):
        """Validate that all imports work correctly"""
        print("\n🔍 Validating imports...")
        
        python_files = list(self.project_root.rglob("*.py"))
        import_errors = 0
        
        for py_file in python_files:
            if py_file.name == 'validate_codebase.py':
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Parse AST to find imports
                try:
                    tree = ast.parse(content)
                    
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                module_name = alias.name
                                try:
                                    importlib.import_module(module_name)
                                except ImportError as e:
                                    self.log_error(f"Import error in {py_file.relative_to(self.project_root)}: {module_name} - {str(e)}")
                                    import_errors += 1
                        
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                try:
                                    importlib.import_module(node.module)
                                except ImportError as e:
                                    # Only flag if it's not a relative import
                                    if not node.module.startswith('.'):
                                        self.log_error(f"Import error in {py_file.relative_to(self.project_root)}: {node.module} - {str(e)}")
                                        import_errors += 1
                
                except SyntaxError as e:
                    self.log_error(f"Syntax error in {py_file.relative_to(self.project_root)}: {str(e)}")
                    import_errors += 1
            
            except Exception as e:
                self.log_warning(f"Could not validate imports in {py_file}: {str(e)}")
        
        if import_errors == 0:
            self.log_success("All imports are valid!")
        
        return import_errors == 0

    def generate_report(self):
        """Generate comprehensive validation report"""
        print("\n" + "="*80)
        print("📊 VALIDATION REPORT")
        print("="*80)
        
        print(f"\n✅ Successes: {len([msg for msg in sys.stdout.getvalue().split('\n') if '✅' in msg])}")
        print(f"⚠️  Warnings: {len(self.warnings)}")
        print(f"❌ Errors: {len(self.errors)}")
        
        if self.errors:
            print("\n❌ ERRORS TO FIX:")
            for error in self.errors:
                print(f"  • {error}")
        
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  • {warning}")
        
        # Save detailed report
        report = {
            'model_attributes': self.model_attributes,
            'template_variables': {k: list(v) for k, v in self.template_variables.items()},
            'errors': self.errors,
            'warnings': self.warnings
        }
        
        report_file = self.project_root / 'validation_report.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📄 Detailed report saved to: {report_file}")
        
        return len(self.errors) == 0

    def run_full_validation(self):
        """Run complete codebase validation"""
        print("🚀 Starting comprehensive codebase validation...")
        
        success = True
        
        # 1. Validate model attributes
        if not self.validate_model_attributes():
            success = False
        
        # 2. Validate template variables
        if not self.validate_template_variables():
            success = False
        
        # 3. Check inline HTML usage
        if not self.check_inline_html_usage():
            success = False
        
        # 4. Validate imports
        if not self.validate_imports():
            success = False
        
        # 5. Generate report
        self.generate_report()
        
        if success:
            print("\n🎉 All validations passed!")
        else:
            print("\n💥 Validation failed - please fix errors above")
        
        return success

if __name__ == "__main__":
    project_root = os.path.dirname(os.path.abspath(__file__))
    validator = CodebaseValidator(project_root)
    
    success = validator.run_full_validation()
    sys.exit(0 if success else 1)
