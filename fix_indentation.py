#!/usr/bin/env python
"""
Quick script to fix indentation issues in flask_app.py
"""

def fix_indentation():
    with open('flask_app.py', 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    # Common indentation issues to check for
    fixed_lines = []
    in_decorator = False
    expected_indent = 0
    
    for i, line in enumerate(lines):
        # Check for decorator start
        if '@wraps' in line or '@app.route' in line:
            in_decorator = True
            expected_indent = len(line) - len(line.lstrip())
            fixed_lines.append(line)
            continue
            
        # Check for def lines that should start new function blocks
        if line.strip().startswith('def ') and in_decorator:
            current_indent = len(line) - len(line.lstrip())
            if current_indent != expected_indent:
                # Fix indentation for function definition
                fixed_lines.append(' ' * expected_indent + line.lstrip())
                expected_indent += 4  # Standard Python indentation
            else:
                fixed_lines.append(line)
                expected_indent += 4
            in_decorator = False
            continue
            
        # Check function body indentation in decorator functions
        if in_decorator and line.strip():
            current_indent = len(line) - len(line.lstrip())
            if current_indent != expected_indent + 4:  # Body should be indented +4 from def
                fixed_lines.append(' ' * (expected_indent + 4) + line.lstrip())
            else:
                fixed_lines.append(line)
            continue
            
        # Normal line
        fixed_lines.append(line)
    
    # Write fixed file
    with open('flask_app_fixed.py', 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)
    
    print("Created flask_app_fixed.py with corrected indentation")
    print("Review the changes, then rename it to flask_app.py if it looks good")

if __name__ == "__main__":
    fix_indentation() 