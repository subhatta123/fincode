#!/usr/bin/python
"""
Simple script to modify static_url_path in app.py to fix routing conflicts
"""

import re
import shutil

def fix_static_path():
    # Make a backup
    shutil.copy('app.py', 'app.py.bak')
    print("Created backup at app.py.bak")
    
    # Read the file
    with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Replace static_url_path='' with static_url_path='/static_files'
    content = content.replace("static_url_path=''", "static_url_path='/static_files'")
    content = content.replace('static_url_path=""', "static_url_path='/static_files'")
    
    # Replace any current explicit assignments
    content = re.sub(r'app\.static_url_path\s*=\s*[\'"].*?[\'"]', "app.static_url_path = '/static_files'", content)
    
    # Write back to file
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("Fixed static_url_path in app.py")
    
    # Also update index route
    with open('app.py', 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Find the index route and make sure it uses send_from_directory
    if 'def serve_index()' in content and 'app.send_static_file' in content:
        content = content.replace('return app.send_static_file', 'return send_from_directory(app.static_folder, ')
        
        # Write back to file
        with open('app.py', 'w', encoding='utf-8') as f:
            f.write(content)
        
        print("Fixed index file serving in app.py")
    
    print("Complete! Now commit and push these changes.")

if __name__ == "__main__":
    fix_static_path() 