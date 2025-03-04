import tableauserverclient as TSC
import pandas as pd
import sqlite3
from datetime import datetime
import json
import requests

def authenticate(server_url: str, auth_method: str, credentials: dict, site_name: str = None) -> TSC.Server:
    """
    Authenticate with Tableau Server using direct API calls.
    """
    try:
        print(f"Attempting to connect to {server_url}")
        
        # Make sure server URL doesn't end with a slash
        if server_url.endswith("/"):
            server_url = server_url[:-1]
        
        # Create server object with use_server_version=False
        server = TSC.Server(server_url, use_server_version=False)
        
        # Handle site name
        site_id = "" if site_name is None else str(site_name).strip()
        print(f"Using site: '{site_id}'")
        
        # Create auth object based on method
        if auth_method == 'token':
            token_name = credentials.get('token_name')
            token = credentials.get('token')
            
            if not token_name or not token:
                raise ValueError("Token name and token value are required")
                
            print(f"Using token authentication: {token_name}")
            
            # For token auth in v0.36
            # The sign-in API expects these parameters
            payload = {
                "credentials": {
                    "personalAccessTokenName": token_name,
                    "personalAccessTokenSecret": token,
                    "site": {"contentUrl": site_id}
                }
            }
            
            # Also create a TSC auth object for the server
            auth_obj = TSC.PersonalAccessTokenAuth(token_name, token, site_id)
            
        else:  # username/password
            username = credentials.get('username')
            password = credentials.get('password')
            
            if not username or not password:
                raise ValueError("Username and password are required")
                
            print(f"Using username/password authentication: {username}")
            
            # For username/password auth in v0.36
            payload = {
                "credentials": {
                    "name": username,
                    "password": password,
                    "site": {"contentUrl": site_id}
                }
            }
            
            # Also create a TSC auth object for the server
            auth_obj = TSC.TableauAuth(username, password, site_id)
        
        # Direct HTTP API call for authentication
        print("Making direct API auth call...")
        auth_url = f"{server_url}/api/3.8/auth/signin"
        print(f"Auth URL: {auth_url}")
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Make the authentication request
        response = requests.post(auth_url, headers=headers, data=json.dumps(payload), verify=True)
        
        # Check response status
        if response.status_code != 200:
            error_msg = f"Authentication failed with status {response.status_code}: {response.text}"
            print(error_msg)
            raise ValueError(error_msg)
        
        # Parse the response
        auth_response = response.json()
        
        # Extract the token and site ID from the response
        token = auth_response["credentials"]["token"]
        site_id = auth_response["credentials"]["site"]["id"]
        user_id = auth_response["credentials"]["user"]["id"]
        
        print(f"Authentication successful! User ID: {user_id}, Site ID: {site_id}")
        
        # Set up the server object for use with the TSC library
        server.auth = auth_obj  # Set the auth object
        server._auth_token = token  # Set the authentication token
        server._site_id = site_id   # Set the site ID
        server._user_id = user_id   # Set the user ID
        
        # Manually configure the server's session for API calls
        server._session = requests.Session()
        server._session.headers.update({
            'x-tableau-auth': token,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        print("Server object successfully configured with authentication")
        return server
        
    except Exception as e:
        print(f"Authentication failed: {str(e)}")
        
        # Provide helpful error messages
        error_msg = str(e).lower()
        if "certificate" in error_msg:
            print("TIP: Certificate validation error. Check the server URL or use verify=False.")
        elif "401" in error_msg:
            print("TIP: Unauthorized. Check your credentials.")
        elif "404" in error_msg:
            print("TIP: API endpoint not found. Check the server URL and API version.")
        elif "connection" in error_msg:
            print("TIP: Connection error. Check your network connection and server URL.")
        
        raise

def get_workbooks(server: TSC.Server) -> list:
    """Get list of workbooks from Tableau Server using direct API calls"""
    try:
        print("Retrieving workbooks from Tableau Server...")
        
        # Verify we have the required authentication attributes
        if not hasattr(server, "_auth_token") or not server._auth_token:
            print("ERROR: Server missing authentication token")
            return []
            
        if not hasattr(server, "_site_id") or not server._site_id:
            print("ERROR: Server missing site ID")
            return []
        
        # Use direct API call instead of server.workbooks.get()
        try:
            # Build the API URL for workbooks
            workbooks_url = f"{server.server_address}/api/3.8/sites/{server._site_id}/workbooks"
            print(f"Requesting workbooks from: {workbooks_url}")
            
            # Set up authentication headers
            headers = {
                'X-Tableau-Auth': server._auth_token,
                'Accept': 'application/json'
            }
            
            # Make the API request
            response = requests.get(workbooks_url, headers=headers)
            
            # Check response status
            if response.status_code != 200:
                print(f"Error: API request failed with status {response.status_code}")
                print(f"Response: {response.text}")
                return []
            
            # Parse the JSON response
            try:
                workbooks_data = response.json()
                print(f"Response parsed successfully.")
                
                # Extract workbooks from the response
                if 'workbooks' in workbooks_data and 'workbook' in workbooks_data['workbooks']:
                    raw_workbooks = workbooks_data['workbooks']['workbook']
                    print(f"Found {len(raw_workbooks)} workbooks")
                else:
                    print("No workbooks found in response")
                    return []
                
                # Process workbooks
                workbooks = []
                for wb in raw_workbooks:
                    try:
                        # Extract basic workbook info
                        workbook_id = wb.get('id')
                        workbook_name = wb.get('name', f"Workbook {workbook_id}")
                        project_id = wb.get('project', {}).get('id')
                        project_name = wb.get('project', {}).get('name', 'Default')
                        
                        # Get views for this workbook
                        views = []
                        try:
                            # Get views using direct API call
                            views_url = f"{server.server_address}/api/3.8/sites/{server._site_id}/workbooks/{workbook_id}/views"
                            views_response = requests.get(views_url, headers=headers)
                            
                            if views_response.status_code == 200:
                                views_data = views_response.json()
                                if 'views' in views_data and 'view' in views_data['views']:
                                    for view in views_data['views']['view']:
                                        views.append({
                                            'id': view.get('id'),
                                            'name': view.get('name'),
                                            'content_url': view.get('contentUrl', '')
                                        })
                                    print(f"Retrieved {len(views)} views for workbook: {workbook_name}")
                                else:
                                    print(f"No views found for workbook: {workbook_name}")
                            else:
                                print(f"Failed to get views for workbook {workbook_id}: {views_response.status_code}")
                        except Exception as views_error:
                            print(f"Error getting views for workbook {workbook_id}: {str(views_error)}")
                        
                        # Add this workbook to our results
                        workbooks.append({
                            'id': workbook_id,
                            'name': workbook_name,
                            'project_name': project_name,
                            'views': views
                        })
                    except Exception as wb_error:
                        print(f"Error processing workbook: {str(wb_error)}")
                        continue
                
                print(f"Successfully processed {len(workbooks)} workbooks")
                return workbooks
                
            except ValueError as json_error:
                print(f"Error parsing JSON response: {str(json_error)}")
                print(f"Response content: {response.text[:200]}...")  # Show first 200 chars
                return []
            
        except Exception as api_error:
            print(f"Error making API request: {str(api_error)}")
            raise
        
    except Exception as e:
        print(f"Error in get_workbooks: {str(e)}")
        
        # Check for common errors
        error_message = str(e).lower()
        if "missing site id" in error_message or "must sign in" in error_message:
            print("Authentication error: The server session may have expired or authentication failed.")
            print("Please try reconnecting to Tableau.")
        elif "not well-formed" in error_message or "invalid token" in error_message:
            print("XML parsing error: The server response wasn't in the expected format.")
            print("This may indicate an API version mismatch or incorrect endpoint.")
        elif "list" in error_message and "id" in error_message:
            print("Data structure error: Received unexpected data format from server.")
            print("This may indicate an API version mismatch or authentication issue.")
        
        return []

def download_and_save_data(server: TSC.Server, view_ids: list, workbook_name: str, view_names: list, table_name: str) -> bool:
    """Download data from Tableau views and save to SQLite database using direct API calls"""
    try:
        print(f"Downloading data for {len(view_ids)} views...")
        print(f"View IDs: {view_ids}")
        
        # Verify authentication
        if not hasattr(server, "_auth_token") or not server._auth_token:
            print("ERROR: Server missing authentication token")
            return False
            
        if not hasattr(server, "_site_id") or not server._site_id:
            print("ERROR: Server missing site ID")
            return False
        
        # Set up auth headers for API calls
        headers = {
            'X-Tableau-Auth': server._auth_token,
            'Accept': 'application/json'
        }
        
        all_data = []
        
        # Download data from each view using direct API calls
        for i, view_id in enumerate(view_ids):
            try:
                print(f"Processing view {i+1}/{len(view_ids)}: {view_id}...")
                
                # 1. Get view information using direct API call
                view_url = f"{server.server_address}/api/3.8/sites/{server._site_id}/views/{view_id}"
                print(f"Getting view info from: {view_url}")
                
                view_response = requests.get(view_url, headers=headers)
                if view_response.status_code != 200:
                    print(f"Failed to get view info. Status: {view_response.status_code}")
                    print(f"Response: {view_response.text}")
                    continue
                
                # Parse view details
                try:
                    view_data = view_response.json()
                    view_name = view_data.get('view', {}).get('name', f"View {view_id}")
                    print(f"Successfully retrieved view: {view_name}")
                except ValueError as json_error:
                    print(f"Error parsing view JSON: {str(json_error)}")
                    view_name = f"View {view_id}"
                
                # 2. Download CSV data - using correct approach for Tableau API
                # Tableau API doesn't like the Accept: text/csv header - it prefers query parameters
                # So we'll use the CSV format parameter in the URL instead
                csv_url = f"{server.server_address}/api/3.8/sites/{server._site_id}/views/{view_id}/data"
                print(f"Downloading CSV from: {csv_url}")
                
                # Set up query parameters - use vf for CSV format
                params = {
                    'maxAge': 1,
                    'vf': 'csv'  # This is the key - asking for CSV format as a query parameter
                }
                
                # Use standard API headers - don't specify text/csv 
                csv_headers = {
                    'X-Tableau-Auth': server._auth_token
                }
                
                csv_response = requests.get(csv_url, headers=csv_headers, params=params)
                if csv_response.status_code != 200:
                    print(f"Failed to download CSV. Status: {csv_response.status_code}")
                    print(f"Response (first 200 chars): {csv_response.text[:200]}...")
                    
                    # Try alternative approach if the first fails
                    print("Trying alternative URL format...")
                    alt_csv_url = f"{server.server_address}/api/3.8/sites/{server._site_id}/views/{view_id}/data.csv"
                    alt_response = requests.get(alt_csv_url, headers=csv_headers)
                    
                    if alt_response.status_code != 200:
                        print(f"Alternative approach also failed. Status: {alt_response.status_code}")
                        continue
                    else:
                        print("Alternative approach succeeded!")
                        csv_response = alt_response
                
                # 3. Convert CSV to DataFrame
                try:
                    import io
                    csv_content = csv_response.content
                    
                    # Check if we actually got CSV content
                    if not csv_content:
                        print(f"Warning: Empty CSV content for view {view_name}")
                        continue
                        
                    # Check content type to ensure we got CSV 
                    content_type = csv_response.headers.get('Content-Type', '')
                    print(f"Response Content-Type: {content_type}")
                    
                    # If we got HTML instead of CSV (common error), log and skip
                    if content_type.startswith('text/html') or csv_content[:10].decode('utf-8', errors='ignore').strip().startswith('<!DOCTYPE'):
                        print(f"Warning: Received HTML instead of CSV for view {view_name}")
                        print(f"First 100 bytes: {csv_content[:100]}")
                        continue
                    
                    # Parse CSV into DataFrame, with more flexible error handling
                    try:
                        df = pd.read_csv(io.BytesIO(csv_content))
                    except pd.errors.EmptyDataError:
                        print(f"Warning: Empty CSV for view {view_name}")
                        continue
                    except pd.errors.ParserError:
                        # If standard parsing fails, try with more flexible parameters
                        print("Standard CSV parsing failed, trying with more flexible parameters...")
                        df = pd.read_csv(io.BytesIO(csv_content), sep=None, engine='python', error_bad_lines=False)
                    
                    if len(df) == 0:
                        print(f"Warning: CSV had 0 rows for view {view_name}")
                        continue
                        
                    print(f"Successfully downloaded {len(df)} rows for view {view_name}")
                    all_data.append(df)
                    
                except Exception as csv_error:
                    print(f"Error parsing CSV data: {str(csv_error)}")
                    # Print some of the content to help debug
                    print(f"First 100 bytes of content: {csv_content[:100]}")
                    continue
                
            except Exception as view_error:
                print(f"Error processing view {view_id}: {str(view_error)}")
                continue
        
        # Check if we got any data
        if not all_data:
            print("No data was downloaded from any view")
            return False
            
        # Combine DataFrames and save
        try:
            print(f"Combining {len(all_data)} DataFrames...")
            combined_df = pd.concat(all_data, axis=0, ignore_index=True)
            print(f"Combined data has {len(combined_df)} rows and {len(combined_df.columns)} columns")
            
            # Save to database
            print(f"Saving to database table '{table_name}'...")
            with sqlite3.connect('data/tableau_data.db') as conn:
                # First, let's check the actual schema of the _internal_tableau_connections table
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(_internal_tableau_connections)")
                columns = cursor.fetchall()
                print(f"Table structure: {columns}")
                
                # Check if _internal_tableau_connections table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_internal_tableau_connections'")
                if not cursor.fetchone():
                    print("Creating _internal_tableau_connections table with server_url column...")
                    cursor.execute("""
                        CREATE TABLE _internal_tableau_connections (
                            dataset_name TEXT PRIMARY KEY,
                            server_url TEXT NOT NULL,
                            auth_method TEXT NOT NULL,
                            credentials TEXT NOT NULL,
                            site_name TEXT,
                            workbook_name TEXT NOT NULL,
                            view_ids TEXT NOT NULL,
                            view_names TEXT NOT NULL,
                            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                
                # Save data
                combined_df.to_sql(table_name, conn, if_exists='replace', index=False)
                
                # Get connection info from server object
                server_url = server.server_address if hasattr(server, 'server_address') else ''
                
                # Get auth method and site name from session if available
                auth_method = 'unknown'
                credentials = '{}'
                site_name = ''
                
                # Try to get from server object first
                if hasattr(server, 'auth') and hasattr(server.auth, 'method_name'):
                    auth_method = server.auth.method_name
                
                # Try to get from environment
                import os
                if 'TABLEAU_AUTH_METHOD' in os.environ:
                    auth_method = os.environ['TABLEAU_AUTH_METHOD']
                
                # Get from Flask session if available
                try:
                    from flask import session
                    if 'tableau_server' in session:
                        auth_method = session['tableau_server'].get('auth_method', auth_method)
                        site_name = session['tableau_server'].get('site_name', '')
                        # Store credentials as JSON string, but remove sensitive data
                        import json
                        credentials_dict = session['tableau_server'].get('credentials', {}).copy()
                        if 'password' in credentials_dict:
                            credentials_dict['password'] = '********'
                        if 'token' in credentials_dict:
                            credentials_dict['token'] = '********'
                        credentials = json.dumps(credentials_dict)
                except (ImportError, RuntimeError):
                    # Flask not available or not in request context
                    print("Could not access Flask session, using default values")
                    
                # Prepare values to insert
                view_ids_str = json.dumps(view_ids)
                view_names_str = json.dumps(view_names)
                
                # Update tracking table with all required fields
                print(f"Updating _internal_tableau_connections with: server_url={server_url}, auth_method={auth_method}, site_name={site_name}")
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO _internal_tableau_connections 
                    (dataset_name, server_url, auth_method, credentials, site_name, workbook_name, view_ids, view_names, updated_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (table_name, server_url, auth_method, credentials, site_name, workbook_name, view_ids_str, view_names_str, datetime.now().isoformat())
                )
                conn.commit()
                
            print(f"Successfully saved {len(combined_df)} rows to database table '{table_name}'")
            return True
            
        except Exception as save_error:
            print(f"Error combining or saving data: {str(save_error)}")
            return False
        
    except Exception as e:
        print(f"General error in download_and_save_data: {str(e)}")
        return False

def generate_table_name(workbook_name: str, view_names: list) -> str:
    """Generate a valid SQLite table name from workbook and view names"""
    # Combine workbook name and view names
    combined_name = f"{workbook_name}_{'_'.join(view_names)}"
    
    # Replace invalid characters
    table_name = ''.join(c if c.isalnum() else '_' for c in combined_name)
    
    # Ensure name starts with a letter
    if not table_name[0].isalpha():
        table_name = 'table_' + table_name
    
    # Truncate if too long (SQLite has a limit)
    if len(table_name) > 63:
        table_name = table_name[:60] + '_' + str(hash(combined_name))[-2:]
    
    return table_name 