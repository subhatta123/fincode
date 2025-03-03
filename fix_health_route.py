#!/usr/bin/env python
"""
Script to fix duplicate health route in app.py
"""

def fix_health_route():
    try:
        # Open the file and read all lines
        with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # Find the line with the duplicate health route
        for i in range(len(lines) - 10, len(lines)):
            if "@app.route('/health')" in lines[i]:
                print(f"Found duplicate health route at line {i+1}")
                # Replace that line and the next few lines with comments
                lines[i] = "# Health check endpoint is already defined earlier in the file\n"
                lines[i+1] = "# The duplicate route has been removed to fix routing conflicts\n"
                lines[i+2] = "\n"  # Keep this line empty
                break
        
        # Write the fixed content back
        with open('app.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print("Successfully fixed duplicate health route in app.py")
        return True
    
    except Exception as e:
        print(f"Error fixing app.py: {str(e)}")
        return False

if __name__ == "__main__":
    fix_health_route() 