import sqlite3
import hashlib
import os
from pathlib import Path
import uuid
import datetime

class UserManagement:
    def __init__(self):
        """Initialize the user management system."""
        self.db_file = "data/app.db"
        self._ensure_data_dir()
        self._init_db()
    
    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        data_dir = os.path.dirname(self.db_file)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)
            print(f"Created data directory: {data_dir}")
    
    def _init_db(self):
        """Initialize the database with necessary tables."""
        try:
            conn = sqlite3.connect(self.db_file)
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
            
            # Create organizations table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS organizations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Insert default organization if it doesn't exist
            cursor.execute('SELECT id FROM organizations WHERE id = 1')
            if not cursor.fetchone():
                cursor.execute('INSERT INTO organizations (id, name) VALUES (1, "Default Organization")')
            
            conn.commit()
            conn.close()
            print("UserManagement database initialized successfully")
        except Exception as e:
            print(f"Error initializing user database: {str(e)}")
            raise
    
    def hash_password(self, password):
        """Hash a password for storage."""
        salt = uuid.uuid4().hex
        hashed = hashlib.sha256(salt.encode() + password.encode()).hexdigest()
        return f"{salt}${hashed}"
    
    def verify_password(self, stored_password, provided_password):
        """Verify a password against its stored hash."""
        salt, hashed = stored_password.split('$')
        verified_hash = hashlib.sha256(salt.encode() + provided_password.encode()).hexdigest()
        return verified_hash == hashed
    
    def create_user(self, username, password, role, permission_type, organization_id=1, organization_name="Default Organization"):
        """Create a new user."""
        try:
            # Check if username already exists
            existing_user = self.get_user_by_username(username)
            if existing_user:
                print(f"Username '{username}' already exists")
                return False
            
            # Hash the password
            hashed_password = self.hash_password(password)
            
            # Insert new user
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO users (username, password, role, permission_type, organization_id, organization_name) VALUES (?, ?, ?, ?, ?, ?)',
                (username, hashed_password, role, permission_type, organization_id, organization_name)
            )
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            print(f"User created: {username}, ID: {user_id}")
            return user_id
        except Exception as e:
            print(f"Error creating user: {str(e)}")
            return False
    
    def verify_user(self, username, password):
        """Verify user credentials and return user data if valid."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            conn.close()
            
            if user and self.verify_password(user[2], password):
                print(f"User verification successful: {username}")
                return user
            else:
                print(f"User verification failed: {username}")
                return None
        except Exception as e:
            print(f"Error verifying user: {str(e)}")
            return None
    
    def get_user_by_username(self, username):
        """Get a user by username."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            conn.close()
            return user
        except Exception as e:
            print(f"Error getting user by username: {str(e)}")
            return None
    
    def get_user_by_id(self, user_id):
        """Get a user by ID."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            conn.close()
            return user
        except Exception as e:
            print(f"Error getting user by ID: {str(e)}")
            return None
    
    def get_all_users(self):
        """Get all users."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users')
            users = cursor.fetchall()
            conn.close()
            return users
        except Exception as e:
            print(f"Error getting all users: {str(e)}")
            return []
    
    def update_user(self, user_id, updates):
        """Update user information."""
        try:
            valid_fields = ['username', 'password', 'role', 'permission_type', 'organization_id', 'organization_name']
            update_fields = []
            update_values = []
            
            for field, value in updates.items():
                if field in valid_fields:
                    if field == 'password':
                        value = self.hash_password(value)
                    update_fields.append(f"{field} = ?")
                    update_values.append(value)
            
            if not update_fields:
                return False
            
            update_values.append(user_id)
            
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?",
                update_values
            )
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            return success
        except Exception as e:
            print(f"Error updating user: {str(e)}")
            return False
    
    def delete_user(self, user_id):
        """Delete a user."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            return success
        except Exception as e:
            print(f"Error deleting user: {str(e)}")
            return False
    
    def create_organization(self, name):
        """Create a new organization."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('INSERT INTO organizations (name) VALUES (?)', (name,))
            org_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return org_id
        except Exception as e:
            print(f"Error creating organization: {str(e)}")
            return False
    
    def get_all_organizations(self):
        """Get all organizations."""
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM organizations')
            orgs = cursor.fetchall()
            conn.close()
            
            return orgs
        except Exception as e:
            print(f"Error getting organizations: {str(e)}")
            return [] 