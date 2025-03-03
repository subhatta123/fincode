import os
import shutil
import sys

def clean_directory():
    """Aggressively clean up the project directory to prevent conflicts."""
    print("=" * 50)
    print("CLEANING PROJECT DIRECTORY")
    print("=" * 50)
    
    # Delete the app directory if it exists
    if os.path.exists('app'):
        print("Removing 'app' directory...")
        try:
            shutil.rmtree('app')
            print("✓ 'app' directory removed successfully")
        except Exception as e:
            print(f"! Failed to remove 'app' directory: {e}")
    else:
        print("✓ No 'app' directory found (good)")
    
    # Delete the frontend directory if it exists
    if os.path.exists('frontend'):
        print("Removing 'frontend' directory...")
        try:
            shutil.rmtree('frontend')
            print("✓ 'frontend' directory removed successfully")
        except Exception as e:
            print(f"! Failed to remove 'frontend' directory: {e}")
    else:
        print("✓ No 'frontend' directory found (good)")
    
    # Try to delete the .streamlit directory
    if os.path.exists('.streamlit'):
        print("Removing '.streamlit' directory...")
        try:
            shutil.rmtree('.streamlit')
            print("✓ '.streamlit' directory removed successfully")
        except Exception as e:
            print(f"! Failed to remove '.streamlit' directory: {e}")
    else:
        print("✓ No '.streamlit' directory found (good)")
    
    # List all files in the current directory
    print("\nCurrent directory contents:")
    for item in os.listdir('.'):
        if os.path.isdir(item):
            print(f"  📁 {item}/")
        else:
            print(f"  📄 {item}")
    
    print("\nCleaning completed!")
    print("=" * 50)

if __name__ == '__main__':
    clean_directory() 