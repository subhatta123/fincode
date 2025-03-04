#!/usr/bin/env python
"""
Standalone script to initialize the database and create a superadmin user.
Used by Render during the deployment process.
"""

import os
import sys
import sqlite3
import hashlib
import uuid

def hash_password(password):
    """Create a salted hash for the password."""
    salt = uuid.uuid4().hex
    return f"{salt}${hashlib.sha256((salt + password).encode()).hexdigest()}"

def init_database():
    print("=" * 50)
    print("INITIALIZING DATABASE")
    print("=" * 50)
    
    # Create data directory if it doesn't exist
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        print(f"Created data directory: {data_dir}")
    
    db_path = os.path.join(data_dir, "app.db")
    print(f"Database path: {db_path}")
    
    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create users table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            permission_type TEXT NOT NULL,
            organization_id INTEGER NOT NULL,
            organization_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        print("Users table created or already exists")
        
        # Create organizations table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        print("Organizations table created or already exists")
        
        # Check if default organization exists
        cursor.execute('SELECT id FROM organizations WHERE id = 1')
        if not cursor.fetchone():
            cursor.execute('INSERT INTO organizations (id, name) VALUES (1, "Default Organization")')
            print("Default organization created")
        else:
            print("Default organization already exists")
        
        # Check if superadmin user exists
        cursor.execute('SELECT id FROM users WHERE username = "superadmin"')
        if not cursor.fetchone():
            # Create superadmin user
            hashed_password = hash_password("admin123")
            cursor.execute('''
            INSERT INTO users (username, password, role, permission_type, organization_id, organization_name)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', ("superadmin", hashed_password, "superadmin", "all", 1, "Default Organization"))
            print("Superadmin user created with password: admin123")
        else:
            print("Superadmin user already exists")
        
        # Verify the user was created
        cursor.execute('SELECT * FROM users WHERE username = "superadmin"')
        user = cursor.fetchone()
        if user:
            print(f"Verified superadmin user exists with ID: {user[0]}")
        else:
            print("WARNING: Failed to create superadmin user!")
        
        # Commit changes and close connection
        conn.commit()
        conn.close()
        
        print("Database initialization completed successfully")
        return True
    except Exception as e:
        print(f"ERROR initializing database: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    init_database() 