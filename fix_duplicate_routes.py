#!/usr/bin/env python
"""
Script to fix duplicate routes in app.py
"""

import re
import os

def remove_duplicate_health_route():
    with open('app.py', 'r') as f:
        content = f.read()
    
    # Find all health route definitions
    health_routes = re.findall(r'@app\.route\(\'\/health\'.*?\)\s+def health_check\(\):', content, re.DOTALL)
    
    if len(health_routes) > 1:
        print(f"Found {len(health_routes)} health routes. Removing duplicates.")
        
        # Find the position of the second health route
        second_health_pos = content.find(health_routes[1])
        
        if second_health_pos != -1:
            # Find the end of the function
            next_def_pos = content.find('def ', second_health_pos + len(health_routes[1]))
            if next_def_pos == -1:
                next_def_pos = len(content)
            
            # Extract the content before and after the duplicate
            content_before = content[:second_health_pos]
            content_after = content[next_def_pos:]
            
            # Add a comment
            new_content = content_before + "# Health check endpoint is already defined earlier in the file\n# Removing duplicate definition to fix routing conflicts\n\n" + content_after
            
            # Write back to the file
            with open('app.py', 'w') as f:
                f.write(new_content)
            
            print("Successfully removed duplicate health route.")
        else:
            print("Could not find second health route position.")
    else:
        print("No duplicate health routes found.")

if __name__ == '__main__':
    remove_duplicate_health_route() 