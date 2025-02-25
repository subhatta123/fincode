import tableauserverclient as TSC
import pandas as pd
import sqlite3
from datetime import datetime
import json

def authenticate(server_url: str, auth_method: str, credentials: dict, site_name: str = None) -> TSC.Server:
    """Authenticate with Tableau Server"""
    try:
        # Configure Tableau Server authentication
        if auth_method == 'token':
            auth = TSC.PersonalAccessTokenAuth(
                token_name=credentials['token_name'],
                personal_access_token=credentials['token'],
                site_id=site_name or ''
            )
        else:  # username/password
            auth = TSC.TableauAuth(
                username=credentials['username'],
                password=credentials['password'],
                site_id=site_name or ''
            )
        
        # Create server instance
        server = TSC.Server(server_url, use_server_version=True)
        
        # Sign in to server
        server.auth = auth
        server.auth.sign_in(server)
        
        print(f"Successfully authenticated with {server_url}")
        return server
        
    except Exception as e:
        print(f"Authentication failed: {str(e)}")
        raise

def get_workbooks(server: TSC.Server) -> list:
    """Get list of workbooks from Tableau Server"""
    try:
        # Get all workbooks
        workbooks = []
        pagination_item = TSC.Pager(page_size=100)
        
        all_workbooks, pagination_item = server.workbooks.get(req_options=pagination_item)
        
        for workbook in all_workbooks:
            # Get workbook details
            server.workbooks.populate_views(workbook)
            server.workbooks.populate_preview_image(workbook)
            
            # Get project name
            project = None
            try:
                project = server.projects.get_by_id(workbook.project_id)
            except:
                pass
            
            # Get views
            views = []
            for view in workbook.views:
                views.append({
                    'id': view.id,
                    'name': view.name,
                    'content_url': view.content_url
                })
            
            workbooks.append({
                'id': workbook.id,
                'name': workbook.name,
                'project_name': project.name if project else 'Default',
                'views': views
            })
        
        return workbooks
        
    except Exception as e:
        print(f"Error getting workbooks: {str(e)}")
        return []

def download_and_save_data(server: TSC.Server, view_ids: list, workbook_name: str, view_names: list, table_name: str) -> bool:
    """Download data from Tableau views and save to SQLite database"""
    try:
        print(f"Downloading data for {len(view_ids)} views...")
        all_data = []
        
        # Download data from each view
        for view_id in view_ids:
            try:
                # Get view by ID
                view = server.views.get_by_id(view_id)
                
                # Download the view data
                csv_req_option = TSC.CSVRequestOptions()
                server.views.populate_csv(view, csv_req_option)
                
                # Read CSV data into DataFrame
                df = pd.read_csv(view.csv)
                all_data.append(df)
                
            except Exception as view_error:
                print(f"Error downloading view {view_id}: {str(view_error)}")
                continue
        
        if not all_data:
            print("No data downloaded from any view")
            return False
        
        # Combine all DataFrames
        combined_df = pd.concat(all_data, axis=0, ignore_index=True)
        
        # Save to SQLite database
        with sqlite3.connect('data/tableau_data.db') as conn:
            # Save the data
            combined_df.to_sql(table_name, conn, if_exists='replace', index=False)
            
            # Update tableau_connections table
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE _internal_tableau_connections 
                SET updated_at = ? 
                WHERE dataset_name = ?
            """, (datetime.now().isoformat(), table_name))
            conn.commit()
        
        print(f"Successfully saved {len(combined_df)} rows to dataset: {table_name}")
        return True
        
    except Exception as e:
        print(f"Error downloading and saving data: {str(e)}")
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