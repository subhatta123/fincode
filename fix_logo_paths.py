import os
import sqlite3
import json

def normalize_path(path):
    """Normalize paths to use consistent separators"""
    if not path:
        return path
    
    # Replace backslashes with forward slashes (standard for web paths)
    normalized = path.replace('\\', '/')
    
    # Make sure there aren't any double slashes
    while '//' in normalized:
        normalized = normalized.replace('//', '/')
    
    print(f"Normalized path: {path} -> {normalized}")
    return normalized

def fix_logo_paths():
    """Fix paths in the database schedules table to use consistent separators"""
    try:
        with sqlite3.connect('data/tableau_data.db') as conn:
            cursor = conn.cursor()
            
            # Get all schedules with format_config
            cursor.execute("SELECT id, format_config FROM schedules")
            schedules = cursor.fetchall()
            
            updated_count = 0
            for schedule_id, format_config_str in schedules:
                if not format_config_str:
                    continue
                
                try:
                    format_config = json.loads(format_config_str)
                    if 'header_logo' in format_config and format_config['header_logo']:
                        original_path = format_config['header_logo']
                        format_config['header_logo'] = normalize_path(format_config['header_logo'])
                        
                        if original_path != format_config['header_logo']:
                            # Update the database with the normalized path
                            cursor.execute(
                                "UPDATE schedules SET format_config = ? WHERE id = ?",
                                (json.dumps(format_config), schedule_id)
                            )
                            updated_count += 1
                            print(f"Updated schedule {schedule_id} with normalized path: {format_config['header_logo']}")
                except json.JSONDecodeError:
                    print(f"Error: Could not parse format_config for schedule {schedule_id}")
                    continue
            
            conn.commit()
            print(f"Updated {updated_count} schedules with normalized paths")
            
            # Now check if the logo files exist in the filesystem
            print("\nChecking for logo files on the filesystem:")
            for schedule_id, format_config_str in schedules:
                if not format_config_str:
                    continue
                
                try:
                    format_config = json.loads(format_config_str)
                    if 'header_logo' in format_config and format_config['header_logo']:
                        logo_path = format_config['header_logo']
                        
                        # Check in various potential locations
                        possible_paths = [
                            logo_path,
                            os.path.join('static', logo_path),
                            os.path.join('static', 'images', logo_path),
                            os.path.join('static', 'logos', logo_path)
                        ]
                        
                        found = False
                        for path in possible_paths:
                            normalized_path = path.replace('/', os.sep)
                            if os.path.exists(normalized_path):
                                print(f"Found logo file for schedule {schedule_id} at {normalized_path}")
                                found = True
                                break
                        
                        if not found:
                            print(f"Warning: Logo file not found for schedule {schedule_id}: {logo_path}")
                            
                            # Check if the directory exists
                            parent_dir = os.path.dirname(logo_path.replace('/', os.sep))
                            if not os.path.exists(parent_dir):
                                print(f"Directory doesn't exist: {parent_dir}")
                                os.makedirs(parent_dir, exist_ok=True)
                                print(f"Created directory: {parent_dir}")
                except json.JSONDecodeError:
                    continue
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return False
    
    return True

def fix_report_formatter():
    """Fix path handling in report_formatter_new.py to be more flexible with path separators"""
    try:
        with open('report_formatter_new.py', 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Add a normalize_path function
        function_to_add = '''
    def _normalize_path(self, path):
        """Normalize paths to handle both forward and backslashes"""
        if not path:
            return path
        return path.replace('\\\\', '/').replace('\\\\', '/')
'''
        
        # Add this function after the _resize_image function
        if '_resize_image' in content and '_normalize_path' not in content:
            content = content.replace(
                'def _resize_image', 
                function_to_add + '\n    def _resize_image'
            )
        
        # Now update the path handling in the logo processing code
        if 'logo_path = self.header_logo' in content:
            # Replace the logo path section with improved path handling
            old_code = '''                # Handle both relative and absolute paths
                logo_path = self.header_logo
                if not os.path.isabs(logo_path):
                    # If it's a relative path, try several common locations
                    possible_paths = [
                        os.path.join('static', logo_path),
                        os.path.join('static', 'images', logo_path),
                        os.path.join('static', 'logos', logo_path),
                        logo_path
                    ]'''
                    
            new_code = '''                # Handle both relative and absolute paths
                logo_path = self._normalize_path(self.header_logo)
                if not os.path.isabs(logo_path):
                    # If it's a relative path, try several common locations
                    possible_paths = [
                        os.path.join('static', logo_path).replace('\\\\', '/'),
                        os.path.join('static', 'images', logo_path).replace('\\\\', '/'),
                        os.path.join('static', 'logos', logo_path).replace('\\\\', '/'),
                        logo_path
                    ]'''
            
            content = content.replace(old_code, new_code)
        
        # Update the app.py file to normalize paths
        with open('report_formatter_new.py', 'w', encoding='utf-8') as file:
            file.write(content)
        
        print("Updated report_formatter_new.py with better path handling")
        return True
    except Exception as e:
        print(f"Error updating report_formatter_new.py: {str(e)}")
        return False

def fix_app_py():
    """Fix path handling in app.py for logo uploads"""
    try:
        with open('app.py', 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Modify the path joining in app.py to consistently use forward slashes
        old_code = "format_config['header_logo'] = os.path.join('uploads/logos', filename)"
        new_code = "format_config['header_logo'] = 'uploads/logos/' + filename"
        
        if old_code in content:
            content = content.replace(old_code, new_code)
            
            with open('app.py', 'w', encoding='utf-8') as file:
                file.write(content)
            
            print("Updated app.py to use consistent forward slash paths for logo uploads")
            return True
    except Exception as e:
        print(f"Error updating app.py: {str(e)}")
        return False

if __name__ == "__main__":
    print("Fixing logo paths in the application...")
    
    # Fix paths in the database
    db_success = fix_logo_paths()
    
    # Fix report formatter path handling
    formatter_success = fix_report_formatter()
    
    # Fix app.py path handling
    app_success = fix_app_py()
    
    if db_success and formatter_success and app_success:
        print("\nSuccessfully fixed path issues. Restart the application to apply changes.")
    else:
        print("\nSome fixes were not applied successfully. Please check the logs above.") 