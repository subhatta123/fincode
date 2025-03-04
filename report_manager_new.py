import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import io
import json
import os
from datetime import datetime, timedelta
import sqlite3
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
import uuid
from twilio.rest import Client
import hashlib
import shutil
import pytz
import tableauserverclient as TSC
from tableau_utils import authenticate, download_and_save_data
from dotenv import load_dotenv
from email.mime.base import MIMEBase
from email import encoders
from report_formatter_new import ReportFormatter
import traceback

class ReportManager:
    def __init__(self):
        """Initialize report manager"""
        # Load environment variables
        load_dotenv()
        
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        
        # Create reports directory for storing generated reports
        self.reports_dir = self.data_dir / "reports"
        self.reports_dir.mkdir(exist_ok=True)
        
        # Create a directory for public access to reports
        self.public_reports_dir = Path("static/reports")
        self.public_reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up schedules file path
        self.schedules_file = self.data_dir / "schedules.json"
        
        # Initialize database
        self.db_path = 'data/tableau_data.db'
        self._init_database()
        
        # Load email settings from environment variables with explicit error checking
        self.smtp_server = os.getenv('SMTP_SERVER')
        self.smtp_port = os.getenv('SMTP_PORT')
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('SENDER_PASSWORD')
        
        # Verify email configuration
        missing_fields = []
        if not self.smtp_server:
            missing_fields.append('SMTP_SERVER')
        if not self.smtp_port:
            missing_fields.append('SMTP_PORT')
        if not self.sender_email:
            missing_fields.append('SENDER_EMAIL')
        if not self.sender_password:
            missing_fields.append('SENDER_PASSWORD')
            
        if missing_fields:
            print(f"Warning: Missing email configuration fields: {', '.join(missing_fields)}")
            print("Please check your .env file")
        else:
            print("\nEmail Configuration loaded successfully:")
            print(f"SMTP Server: {self.smtp_server}")
            print(f"SMTP Port: {self.smtp_port}")
            print(f"Sender Email: {self.sender_email}")
            print(f"Password Set: {'Yes' if self.sender_password else 'No'}\n")
        
        # Set base URL for report access
        self.base_url = os.getenv('BASE_URL', 'http://localhost:8501')
        
        # Initialize scheduler
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        
        # Initialize Twilio client for WhatsApp
        self.twilio_client = None
        self.twilio_whatsapp_number = os.getenv('TWILIO_WHATSAPP_NUMBER')
        self.twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        
        if all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_whatsapp_number]):
            try:
                self.twilio_client = Client(self.twilio_account_sid, self.twilio_auth_token)
                print("Twilio client initialized successfully")
            except Exception as e:
                print(f"Failed to initialize Twilio client: {str(e)}")
        else:
            print("Twilio configuration incomplete. Please check your .env file")
            
        # Load saved schedules after everything is initialized
        self.load_saved_schedules()
    
    def _init_database(self):
        """Initialize SQLite database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create schedules table with proper data types
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS schedules (
                        id TEXT PRIMARY KEY,
                        dataset_name TEXT NOT NULL,
                        schedule_type TEXT NOT NULL,
                        schedule_config TEXT NOT NULL,
                        email_config TEXT NOT NULL,
                        format_config TEXT,
                        timezone TEXT DEFAULT 'UTC',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        last_run TEXT,
                        next_run TEXT,
                        status TEXT DEFAULT 'active'
                    )
                """)
                
                # Create schedule_runs table with proper data types
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS schedule_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        schedule_id TEXT NOT NULL,
                        run_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        status TEXT NOT NULL,
                        error_message TEXT,
                        FOREIGN KEY (schedule_id) REFERENCES schedules (id)
                    )
                """)
                
                # Create tableau_connections table (internal table, only visible to superadmin)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _internal_tableau_connections (
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
                
                # Migrate data from old table if it exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tableau_connections'")
                if cursor.fetchone():
                    cursor.execute("""
                        INSERT OR REPLACE INTO _internal_tableau_connections 
                        SELECT * FROM tableau_connections
                    """)
                    cursor.execute("DROP TABLE tableau_connections")
                    conn.commit()
                    print("Migrated tableau_connections to internal table")
                
                conn.commit()
                print("Database initialized successfully")
                
                # Only migrate schedules from JSON if the schedules table is empty
                cursor.execute("SELECT COUNT(*) FROM schedules")
                if cursor.fetchone()[0] == 0 and self.schedules_file.exists():
                    try:
                        with open(self.schedules_file, 'r') as f:
                            schedules = json.load(f)
                            
                        # Migrate schedules to database
                        for job_id, schedule in schedules.items():
                            cursor.execute("""
                                INSERT OR REPLACE INTO schedules (
                                    id, dataset_name, schedule_type, schedule_config, 
                                    email_config, format_config, created_at, status
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                job_id,
                                schedule['dataset_name'],
                                schedule['schedule_config']['type'],
                                json.dumps(schedule['schedule_config']),
                                json.dumps(schedule['email_config']),
                                json.dumps(schedule.get('format_config')),
                                schedule.get('created_at', datetime.now().isoformat()),
                                'active'
                            ))
                        
                        conn.commit()
                        print(f"Migrated {len(schedules)} schedules from JSON to database")
                        
                        # Rename old schedules file as backup
                        backup_file = self.schedules_file.with_suffix('.json.bak')
                        self.schedules_file.rename(backup_file)
                        print(f"Created backup of schedules file: {backup_file}")
                        
                    except Exception as e:
                        print(f"Error migrating schedules from JSON: {str(e)}")
                
        except Exception as e:
            print(f"Error initializing database: {str(e)}")

    def generate_pdf(self, df: pd.DataFrame, title: str) -> io.BytesIO:
        """Generate PDF report from DataFrame"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
        elements = []
        
        # Add title with proper style creation
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            name='CustomTitle',  # Added required 'name' parameter
            parent=styles['Title'],
            fontSize=24,
            spaceAfter=30
        )
        elements.append(Paragraph(str(title), title_style))  # Ensure title is string
        
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp_style = ParagraphStyle(
            name='Timestamp',  # Added required 'name' parameter
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.gray,
            spaceAfter=20
        )
        elements.append(Paragraph(f"Generated on: {timestamp}", timestamp_style))
        
        # Add summary statistics
        summary_style = ParagraphStyle(
            name='Summary',  # Added required 'name' parameter
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=20
        )
        elements.append(Paragraph(f"Total Records: {len(df)}", summary_style))
        
        # Prepare table data
        table_data = [df.columns.tolist()]  # Header row
        table_data.extend(df.values.tolist())
        
        # Calculate column widths based on content
        col_widths = []
        for col_idx in range(len(df.columns)):
            col_content = [str(row[col_idx]) for row in table_data]
            max_content_len = max(len(str(content)) for content in col_content)
            col_widths.append(min(max_content_len * 7, 200))  # Scale factor of 7, max width 200
        
        # Create table
        table = Table(table_data, colWidths=col_widths)
        
        # Add style to table
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        table.setStyle(style)
        
        elements.append(table)
        doc.build(elements)
        
        buffer.seek(0)
        return buffer

    def generate_report_link(self, report_path: Path, expiry_hours: int = 24) -> str:
        """Generate a secure, time-limited link for report access"""
        try:
            # Create reports directory if it doesn't exist
            self.public_reports_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate a unique token
            token = str(uuid.uuid4())
            
            # Create a secure hash of the token
            hash_obj = hashlib.sha256(token.encode())
            secure_hash = hash_obj.hexdigest()
            
            # Create the public file path
            public_path = self.public_reports_dir / f"{secure_hash}{report_path.suffix}"
            if public_path.exists():
                public_path.unlink()
            
            # Copy the file to public directory
            shutil.copy2(report_path, public_path)
            print(f"Copied report to public directory: {public_path}")
            
            # Store metadata about the link
            metadata = {
                'original_path': str(report_path),
                'created_at': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(hours=expiry_hours)).isoformat()
            }
            
            # Save metadata
            metadata_path = self.public_reports_dir / f"{secure_hash}.json"
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Return the file path relative to the static directory
            return str(public_path)
            
        except Exception as e:
            print(f"Failed to generate report link: {str(e)}")
            print(f"Error details: {e.__dict__ if hasattr(e, '__dict__') else 'No details'}")
            return None

    def send_report(self, dataset_name: str, email_config: dict, format_config: dict = None):
        """Send a report with the specified dataset and configurations."""
        try:
            print(f"Sending report for dataset: {dataset_name}")
            print(f"Email config: {email_config}")
            print(f"Format config: {format_config if format_config else 'None'}")
            
            # Ensure format_config is a dictionary
            if not format_config:
                format_config = {}
            elif not isinstance(format_config, dict):
                format_config = json.loads(format_config) if isinstance(format_config, str) else {}
            
            # Prepare the email configuration
            recipients = email_config.get('recipients', [])
            if isinstance(recipients, str):
                recipients = [r.strip() for r in recipients.split(',') if r.strip()]
            
            cc = email_config.get('cc', [])
            if isinstance(cc, str):
                cc = [c.strip() for c in cc.split(',') if c.strip()]
            
            # Load the dataset directly
            print(f"Loading dataset: {dataset_name}")
            try:
                # Connect to the database
                conn = sqlite3.connect(self.db_path)
                # Set row_factory to None to get raw tuples
                conn.row_factory = None
                cursor = conn.cursor()
                
                # Check if the table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (dataset_name,))
                if not cursor.fetchone():
                    raise ValueError(f"Dataset table not found: {dataset_name}")
                
                # Get column names from table info
                cursor.execute(f"PRAGMA table_info({dataset_name})")
                columns = [col[1] for col in cursor.fetchall()]
                
                # Get the data
                cursor.execute(f"SELECT * FROM {dataset_name}")
                rows = cursor.fetchall()
                
                # Create DataFrame
                df = pd.DataFrame(rows, columns=columns)
                
                # Convert all columns to strings, handling tuples
                for col in df.columns:
                    df[col] = df[col].apply(lambda x: str(x[0]) if isinstance(x, tuple) else str(x))
                
                conn.close()
                
                if df.empty:
                    raise ValueError(f"No data found in dataset: {dataset_name}")
                
            except Exception as db_error:
                print(f"Database error: {str(db_error)}")
                raise
            
            # Set up the formatter with format config
            try:
                # Import here as a fallback in case the module import fails
                from report_formatter_new import ReportFormatter
                formatter = ReportFormatter()
                
                # Process format_config - ensure it's a dictionary with proper values
                if format_config:
                    if isinstance(format_config, str):
                        try:
                            format_config = json.loads(format_config)
                        except:
                            print("Warning: Could not parse format_config JSON string")
                            format_config = {}
                else:
                    format_config = {}
                
                # Print format config for debugging
                print(f"Applying format config: {format_config}")
                
                # Ensure title is properly set
                if 'header_title' not in format_config and 'title' in format_config:
                    format_config['header_title'] = format_config['title']
                
                # Apply format settings explicitly
                formatter.set_format_config(format_config)
                
                # Get report title from format config or use default
                report_title = format_config.get('header_title', format_config.get('title', f"Report for {dataset_name}"))
            except ImportError:
                print("Error importing ReportFormatter class")
                raise
            
            # Make sure title is a string
            report_title = str(report_title)
            print(f"Using report title: {report_title}")
            
            # Generate the report
            print(f"Generating report with title: {report_title}")
            try:
                # Include all formatting options in the generate_report call
                pdf_buffer = formatter.generate_report(
                    df,
                    report_title=report_title,
                    include_row_count=format_config.get('include_summary', True),
                    include_totals=format_config.get('include_summary', True),
                    include_averages=format_config.get('include_summary', True),
                    selected_columns=format_config.get('selected_columns', None)
                )
            except Exception as format_error:
                print(f"Error generating report: {str(format_error)}")
                raise
            
            # Save the report
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            hash_obj = hashlib.sha256(f"{dataset_name}_{timestamp}".encode())
            filename = f"{hash_obj.hexdigest()}_{timestamp}.pdf"
            
            # Save to static/reports directory to make it accessible via URL
            reports_dir = Path('static/reports')
            reports_dir.mkdir(parents=True, exist_ok=True)
            report_path = reports_dir / filename
            
            # Write the PDF data to the file
            with open(report_path, 'wb') as f:
                f.write(pdf_buffer.getvalue())
            
            print(f"Report saved to: {report_path}")
            
            # Create the URL path that can be accessed by the web server
            if self.base_url:
                report_url = f"{self.base_url}/static/reports/{filename}"
            else:
                report_url = f"/static/reports/{filename}"
            
            print(f"Generated report URL: {report_url}")
            
            # Create the email body
            email_body = email_config.get('body', 'Please find the attached report.')
            try:
                # Add the URL link to the email body
                email_body += f"\n\nYou can also view the report at: {report_url}"
            except Exception as link_error:
                print(f"Warning: Could not generate shareable link: {str(link_error)}")
            
            # Send the email
            try:
                # Get SMTP settings
                smtp_server = email_config.get('smtp_server', os.getenv('SMTP_SERVER'))
                smtp_port = int(email_config.get('smtp_port', os.getenv('SMTP_PORT', 587)))
                sender_email = email_config.get('sender_email', os.getenv('SENDER_EMAIL'))
                sender_password = email_config.get('sender_password', os.getenv('SENDER_PASSWORD'))
                
                print(f"Sending email via {smtp_server}:{smtp_port}")
                print(f"From: {sender_email}")
                print(f"To: {recipients}")
                print(f"CC: {cc}")
                print(f"Subject: {email_config.get('subject', f'Report for {dataset_name}')}")
                
                if not smtp_server or not sender_email or not sender_password:
                    raise ValueError("Missing required email configuration fields")
                
                # Create message
                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = ', '.join(recipients)
                if cc:
                    msg['Cc'] = ', '.join(cc)
                msg['Subject'] = email_config.get('subject', f"Report for {dataset_name}")
                
                # Add body
                msg.attach(MIMEText(email_body, 'plain'))
                
                # Add attachment
                with open(report_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                msg.attach(part)
                
                # Send email
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    server.starttls()
                    server.login(sender_email, sender_password)
                    server.send_message(msg)
                
                print(f"Email sent successfully to {recipients}")
                return True
            
            except Exception as email_error:
                print(f"Error sending email: {str(email_error)}")
                print(f"Email config: SMTP={smtp_server}, Port={smtp_port}, Sender={sender_email}, Password set: {bool(sender_password)}")
                raise
                
        except Exception as e:
            print(f"Failed to send report: {str(e)}")
            print(f"Error details: {e.__dict__ if hasattr(e, '__dict__') else 'No details'}")
            return False

    def verify_whatsapp_number(self, to_number: str) -> bool:
        """Verify if a WhatsApp number is valid and opted-in"""
        try:
            # Clean up the phone number
            to_number = ''.join(filter(str.isdigit, to_number))
            
            # Add country code if missing
            if not to_number.startswith('1'):
                to_number = '1' + to_number
            
            # Check if the number exists in Twilio
            numbers = self.twilio_client.incoming_phone_numbers.list(
                phone_number=f"+{to_number}"
            )
            
            return len(numbers) > 0
        except Exception as e:
            print(f"Failed to verify WhatsApp number: {str(e)}")
            return False

    def send_whatsapp_message(self, to_number: str, message: str) -> bool:
        """Send WhatsApp message with improved error handling"""
        try:
            if not self.twilio_client:
                print("Twilio client not initialized. Check your environment variables.")
                return False

            # Clean up the phone numbers
            from_number = self.twilio_whatsapp_number.strip()
            to_number = to_number.strip()
            
            # Add whatsapp: prefix if not present
            if not from_number.startswith('whatsapp:'):
                from_number = f'whatsapp:{from_number}'
            if not to_number.startswith('whatsapp:'):
                to_number = f'whatsapp:{to_number}'
            
            print(f"Attempting to send WhatsApp message from {from_number} to {to_number}")
            
            try:
                # First, try to send the actual message
                message = self.twilio_client.messages.create(
                    from_=from_number,
                    body=message,
                    to=to_number
                )
                print(f"WhatsApp message sent successfully with SID: {message.sid}")
                return True
            except Exception as e:
                error_msg = str(e)
                print(f"WhatsApp error: {error_msg}")
                
                if "not currently opted in" in error_msg.lower():
                    # Send sandbox join instructions
                    sandbox_message = f"""
                    *Welcome to Tableau Data Reporter!*
                    
                    To receive notifications, please:
                    1. Save {self.twilio_whatsapp_number} in your contacts
                    2. Send 'join' to this number on WhatsApp
                    3. Wait for confirmation before we can send you reports
                    
                    This is a one-time setup process.
                    """
                    
                    try:
                        message = self.twilio_client.messages.create(
                            from_=from_number,
                            body=sandbox_message,
                            to=to_number
                        )
                        print(f"Sent sandbox join instructions to {to_number}")
                        return False
                    except Exception as sandbox_error:
                        print(f"Failed to send sandbox instructions: {str(sandbox_error)}")
                        return False
                else:
                    raise e

        except Exception as e:
            print(f"Failed to send WhatsApp message: {str(e)}")
            if "not a valid WhatsApp" in str(e):
                print("Please make sure you're using a valid WhatsApp number with country code")
            elif "not currently opted in" in str(e):
                print("Recipient needs to opt in to receive messages")
            return False
    
    def remove_schedule(self, job_id: str) -> bool:
        """Remove a scheduled report"""
        try:
            print(f"Removing schedule {job_id}")
            
            # Remove from scheduler if job exists
            try:
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)
                    print(f"Removed job {job_id} from scheduler")
            except Exception as scheduler_error:
                print(f"Warning: Job not found in scheduler: {str(scheduler_error)}")
            
            # Remove from database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # First check if schedule exists
                cursor.execute("SELECT id FROM schedules WHERE id = ? AND status = 'active'", (job_id,))
                if cursor.fetchone():
                    # Update status to 'deleted' instead of actually deleting
                    cursor.execute("""
                        UPDATE schedules 
                        SET status = 'deleted',
                            next_run = NULL
                        WHERE id = ?
                    """, (job_id,))
                    conn.commit()
                    print(f"Successfully removed schedule {job_id} from database")
                    return True
                else:
                    print(f"Schedule {job_id} not found in database or already deleted")
                    return False
                
        except Exception as e:
            print(f"Failed to remove schedule {job_id}: {str(e)}")
            return False
    
    def load_schedules(self) -> dict:
        """Load saved schedules"""
        try:
            schedules = {}
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                try:
                    # Get column names from the table
                    cursor.execute("PRAGMA table_info(schedules)")
                    columns = [col[1] for col in cursor.fetchall()]
                    print(f"Available columns: {columns}")
                    
                    cursor.execute("""
                        SELECT id, dataset_name, schedule_type, schedule_config, 
                               email_config, format_config, created_at, last_run, 
                               next_run, status 
                        FROM schedules 
                        WHERE status = 'active'
                    """)
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        schedule_id = row[0]  # id column
                        
                        # Parse format_config if it exists
                        format_config_str = row[5]
                        try:
                            format_config = json.loads(format_config_str) if format_config_str else None
                            # Convert string representation of style objects back to proper format
                            if format_config:
                                if 'title_style' in format_config and isinstance(format_config['title_style'], str):
                                    # Create a basic title style configuration
                                    format_config['title_style'] = {
                                        'fontName': 'Helvetica',
                                        'fontSize': 24,
                                        'alignment': 1,  # Center alignment
                                        'textColor': '#000000',
                                        'spaceAfter': 30
                                    }
                                if 'table_style' in format_config and isinstance(format_config['table_style'], str):
                                    # Create a basic table style configuration
                                    format_config['table_style'] = [
                                        ['BACKGROUND', [0, 0], [-1, 0], '#2d5d7b'],
                                        ['TEXTCOLOR', [0, 0], [-1, 0], '#ffffff'],
                                        ['ALIGN', [0, 0], [-1, -1], 'LEFT'],
                                        ['FONTNAME', [0, 0], [-1, 0], 'Helvetica-Bold'],
                                        ['FONTSIZE', [0, 0], [-1, 0], 10],
                                        ['BOTTOMPADDING', [0, 0], [-1, 0], 12],
                                        ['BACKGROUND', [0, 1], [-1, -1], '#f5f5f5'],
                                        ['TEXTCOLOR', [0, 1], [-1, -1], '#000000'],
                                        ['FONTNAME', [0, 1], [-1, -1], 'Helvetica'],
                                        ['FONTSIZE', [0, 1], [-1, -1], 8],
                                        ['GRID', [0, 0], [-1, -1], 1, '#808080'],
                                        ['ROWHEIGHT', [0, 0], [-1, -1], 20],
                                        ['VALIGN', [0, 0], [-1, -1], 'MIDDLE']
                                    ]
                        except Exception as format_error:
                            print(f"Error parsing format_config for schedule {schedule_id}: {str(format_error)}")
                            format_config = None
                        
                        schedules[schedule_id] = {
                            'dataset_name': row[1],
                            'schedule_type': row[2],
                            'schedule_config': json.loads(row[3]),
                            'email_config': json.loads(row[4]),
                            'format_config': format_config,
                            'created_at': row[6],
                            'last_run': row[7],
                            'next_run': row[8],
                            'status': row[9]
                        }
                    
                except sqlite3.OperationalError as e:
                    if "no such table" in str(e) or "no such column" in str(e):
                        print("Database schema issue detected, reinitializing database...")
                        self._init_database()
                        return {}
                    else:
                        raise
                
            print(f"Loaded {len(schedules)} schedules from database")
            return schedules
            
        except Exception as e:
            print(f"Error loading schedules: {str(e)}")
            return {}
    
    def save_schedules(self, schedules: dict):
        """Save schedules to database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Begin transaction
                cursor.execute("BEGIN TRANSACTION")
                
                try:
                    for schedule_id, schedule in schedules.items():
                        # Convert schedule data to JSON strings
                        schedule_config = json.dumps(schedule['schedule_config'])
                        email_config = json.dumps(schedule['email_config'])
                        format_config = json.dumps(schedule.get('format_config')) if schedule.get('format_config') else None
                        
                        # Insert or update schedule
                        cursor.execute("""
                        INSERT OR REPLACE INTO schedules (
                            id, dataset_name, schedule_type, schedule_config, 
                            email_config, format_config, created_at, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            schedule_id,
                            schedule['dataset_name'],
                            schedule['schedule_config']['type'],
                            schedule_config,
                            email_config,
                            format_config,
                            schedule.get('created_at', datetime.now().isoformat()),
                            'active'
                        ))
                    
                    # Commit transaction
                    conn.commit()
                    print(f"Saved {len(schedules)} schedules to database")
                    
                except Exception as e:
                    # Rollback on error
                    conn.rollback()
                    print(f"Error saving schedules, rolling back: {str(e)}")
                    raise
                    
        except Exception as e:
            print(f"Error saving schedules to database: {str(e)}")
            raise
    
    def load_saved_schedules(self):
        """Load saved schedules from database and add them to the scheduler"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, dataset_name, schedule_config, email_config, format_config, timezone
                    FROM schedules 
                    WHERE status = 'active'
                """)
                rows = cursor.fetchall()

            for row in rows:
                job_id, dataset_name, schedule_config_str, email_config_str, format_config_str, timezone_str = row
                
                # Skip if job already exists in scheduler
                if self.scheduler.get_job(job_id):
                    print(f"Job {job_id} already exists in scheduler, skipping")
                    continue
                
                try:
                    # Parse configurations
                    schedule_config = json.loads(schedule_config_str)
                    email_config = json.loads(email_config_str)
                    format_config = json.loads(format_config_str) if format_config_str else None
                    
                    # Ensure timezone is set in schedule_config
                    schedule_config['timezone'] = timezone_str or 'UTC'
                    
                    # Schedule the job using existing method
                    self.schedule_report(
                        dataset_name=dataset_name,
                        email_config=email_config,
                        schedule_config=schedule_config,
                        format_config=format_config,
                        existing_job_id=job_id
                    )
                    
                except Exception as e:
                    print(f"Failed to load schedule {job_id}: {str(e)}")
                    # Mark failed schedule as inactive
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE schedules SET status = 'inactive' WHERE id = ?",
                            (job_id,)
                        )
                        conn.commit()
                    
        except Exception as e:
            print(f"Failed to load saved schedules: {str(e)}")
            return False
        
        return True

    def get_active_schedules(self) -> dict:
        """Get all active schedules with their next run times"""
        schedules = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, dataset_name, schedule_type, schedule_config, email_config, 
                           format_config, timezone, next_run, status
                    FROM schedules 
                    WHERE status = 'active'
                """)
                rows = cursor.fetchall()

                for row in rows:
                    (job_id, dataset_name, schedule_type, schedule_config_str, 
                     email_config_str, format_config_str, timezone_str, next_run_str, status) = row
                    
                    try:
                        # Get timezone
                        try:
                            timezone = pytz.timezone(timezone_str or 'UTC')
                        except pytz.exceptions.UnknownTimeZoneError:
                            timezone = pytz.UTC
                        
                        # Get job from scheduler
                        job = self.scheduler.get_job(job_id)
                        schedule_config = json.loads(schedule_config_str)
                        
                        # Handle next run time based on schedule type
                        if schedule_type == 'one-time':
                            # For one-time schedules, use the scheduled date/time
                            try:
                                date_str = schedule_config.get('date')
                                hour = int(schedule_config.get('hour', 0))
                                minute = int(schedule_config.get('minute', 0))
                                dt_str = f"{date_str} {hour:02d}:{minute:02d}:00"
                                next_run = timezone.localize(datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S'))
                                next_run_str = next_run.isoformat()
                            except Exception as e:
                                print(f"Error parsing one-time schedule date: {str(e)}")
                                next_run_str = None
                        else:
                            # For recurring schedules, get next run time from the scheduler
                            if job and job.next_run_time:
                                next_run = job.next_run_time.astimezone(timezone)
                                next_run_str = next_run.isoformat()
                            else:
                                next_run_str = None
                        
                        email_config = json.loads(email_config_str)
                        format_config = json.loads(format_config_str) if format_config_str else None
                        
                        schedules[job_id] = {
                            'dataset_name': dataset_name,
                            'schedule_type': schedule_type,
                            'schedule_config': schedule_config,
                            'email_config': email_config,
                            'format_config': format_config,
                            'timezone': timezone_str,
                            'next_run': next_run_str,
                            'status': status
                        }
                    except Exception as e:
                        print(f"Error processing schedule {job_id}: {str(e)}")
                        continue

        except Exception as e:
            print(f"Error getting active schedules: {str(e)}")
            return {}

        return schedules

    def get_next_run_time(self, schedule_id: str) -> str:
        """Get the next run time for a schedule"""
        try:
            # Get schedule from database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT schedule_type, schedule_config, timezone
                    FROM schedules 
                    WHERE id = ? AND status = 'active'
                """, (schedule_id,))
                row = cursor.fetchone()
                
                if not row:
                    return "Schedule not found"
                
                schedule_type, schedule_config_str, timezone_str = row
                schedule_config = json.loads(schedule_config_str)
                
                try:
                    timezone = pytz.timezone(timezone_str or 'UTC')
                except pytz.exceptions.UnknownTimeZoneError:
                    timezone = pytz.UTC
                
                # Handle one-time schedules
                if schedule_type == 'one-time':
                    try:
                        date_str = schedule_config.get('date')
                        hour = int(schedule_config.get('hour', 0))
                        minute = int(schedule_config.get('minute', 0))
                        dt_str = f"{date_str} {hour:02d}:{minute:02d}:00"
                        next_run = timezone.localize(datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S'))
                        return next_run.strftime('%Y-%m-%d %H:%M:%S %Z')
                    except Exception as e:
                        print(f"Error parsing one-time schedule date: {str(e)}")
                        return "Invalid schedule date"
                
                # For recurring schedules, get from scheduler
                job = self.scheduler.get_job(schedule_id)
                if job and job.next_run_time:
                    next_run = job.next_run_time.astimezone(timezone)
                    return next_run.strftime('%Y-%m-%d %H:%M:%S %Z')
                
                return "Not scheduled"
                
        except Exception as e:
            print(f"Error getting next run time: {str(e)}")
            return "Error getting next run time"

    def get_schedules(self) -> list:
        """Retrieve all schedules from the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, dataset_name, schedule_type, schedule_config, email_config, 
                           format_config, timezone, next_run, status
                    FROM schedules 
                    WHERE status = 'active'
                """)
                rows = cursor.fetchall()
                
                schedules = []
                for row in rows:
                    schedule = {
                        'id': row[0],
                        'dataset_name': row[1],
                        'schedule_type': row[2],
                        'schedule_config': json.loads(row[3]),
                        'email_config': json.loads(row[4]),
                        'format_config': json.loads(row[5]) if row[5] else {},
                        'timezone': row[6],
                        'next_run': row[7],
                        'status': row[8]
                    }
                    
                    # Add schedule-specific fields based on type
                    if schedule['schedule_type'] == 'weekly':
                        schedule['days'] = schedule['schedule_config'].get('days', [])
                    elif schedule['schedule_type'] == 'monthly':
                        schedule['day_option'] = schedule['schedule_config'].get('day_option')
                        schedule['day'] = schedule['schedule_config'].get('day')
                    
                    # Add common time fields
                    schedule['hour'] = schedule['schedule_config'].get('hour', 0)
                    schedule['minute'] = schedule['schedule_config'].get('minute', 0)
                    
                    schedules.append(schedule)
            
            return schedules
            
        except Exception as e:
            print(f"Error retrieving schedules: {str(e)}")
            return [] 

    def get_schedule(self, schedule_id: str) -> dict:
        """Get a single schedule by ID"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT dataset_name, schedule_type, schedule_config, email_config, 
                           format_config, timezone, next_run, status
                    FROM schedules 
                    WHERE id = ? AND status != 'deleted'
                """, (schedule_id,))
                row = cursor.fetchone()
                
                if not row:
                    print(f"Schedule {schedule_id} not found")
                    return None
                    
                schedule = {
                    'id': schedule_id,
                    'dataset_name': row[0],
                    'schedule_type': row[1],
                    'schedule_config': json.loads(row[2]),
                    'email_config': json.loads(row[3]),
                    'format_config': json.loads(row[4]) if row[4] else {},
                    'timezone': row[5],
                    'next_run': row[6],
                    'status': row[7]
                }
                
                # Add schedule-specific fields based on type
                if schedule['schedule_type'] == 'weekly':
                    schedule['days'] = schedule['schedule_config'].get('days', [])
                elif schedule['schedule_type'] == 'monthly':
                    schedule['day_option'] = schedule['schedule_config'].get('day_option')
                    schedule['day'] = schedule['schedule_config'].get('day')
                
                # Add common time fields
                schedule['hour'] = schedule['schedule_config'].get('hour', 0)
                schedule['minute'] = schedule['schedule_config'].get('minute', 0)
                
                return schedule
                
        except Exception as e:
            print(f"Error getting schedule {schedule_id}: {str(e)}")
            return None

    def run_schedule_now(self, schedule_id: str) -> bool:
        """Run a schedule immediately"""
        try:
            print(f"Running schedule {schedule_id}")
            
            # Get the schedule details
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT dataset_name, email_config, format_config 
                    FROM schedules 
                    WHERE id = ? AND status = 'active'
                """, (schedule_id,))
                row = cursor.fetchone()
                
                if not row:
                    print(f"Schedule {schedule_id} not found or not active")
                    return False
                
                dataset_name, email_config_str, format_config_str = row
                
                try:
                    email_config = json.loads(email_config_str)
                    format_config = json.loads(format_config_str) if format_config_str else None
                except json.JSONDecodeError as e:
                    print(f"Error decoding configuration: {str(e)}")
                    return False
            
            # Add email settings from environment if not present
            email_config.setdefault('smtp_server', self.smtp_server)
            email_config.setdefault('smtp_port', int(self.smtp_port))
            email_config.setdefault('sender_email', self.sender_email)
            email_config.setdefault('sender_password', self.sender_password)
            
            print("\nEmail configuration:")
            print(f"SMTP Server: {email_config.get('smtp_server')}")
            print(f"SMTP Port: {email_config.get('smtp_port')}")
            print(f"Sender Email: {email_config.get('sender_email')}")
            print(f"Password Set: {'Yes' if email_config.get('sender_password') else 'No'}")
            print(f"Recipients: {email_config.get('recipients')}\n")
            
            # Run the report generation and sending
            try:
                success = self.send_report(dataset_name, email_config, format_config)
                
                if success:
                    # Update last_run time in database
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE schedules 
                            SET last_run = ? 
                            WHERE id = ?
                        """, (datetime.now().isoformat(), schedule_id))
                        conn.commit()
                    
                    print(f"Successfully ran schedule {schedule_id}")
                    return True
                else:
                    print(f"Failed to send report for schedule {schedule_id}")
                    return False
                
            except Exception as run_error:
                print(f"Error running schedule {schedule_id}: {str(run_error)}")
                
                # Log the error in schedule_runs table
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO schedule_runs (schedule_id, status, error_message)
                            VALUES (?, 'error', ?)
                        """, (schedule_id, str(run_error)))
                        conn.commit()
                except Exception as log_error:
                    print(f"Error logging run error: {str(log_error)}")
                
                return False
                
        except Exception as e:
            print(f"Error in run_schedule_now: {str(e)}")
            return False

    def update_schedule(self, schedule_id: str, schedule_config: dict, email_config: dict, format_config: dict = None) -> bool:
        """Update an existing schedule with new configuration"""
        try:
            # Get the existing schedule
            existing_schedule = self.get_schedule(schedule_id)
            if not existing_schedule:
                print(f"Schedule {schedule_id} not found")
                return False

            # Get dataset name from existing schedule
            dataset_name = existing_schedule['dataset_name']

            # Remove the old job from the scheduler
            if self.scheduler.get_job(schedule_id):
                self.scheduler.remove_job(schedule_id)
                print(f"Removed old schedule from scheduler: {schedule_id}")

            # Schedule new job with updated configuration
            job_id = self.schedule_report(
                dataset_name=dataset_name,
                schedule_config=schedule_config,
                email_config=email_config,
                format_config=format_config,
                existing_job_id=schedule_id
            )

            if not job_id:
                print("Failed to update schedule")
                return False

            print(f"Successfully updated schedule {schedule_id}")
            return True

        except Exception as e:
            print(f"Error updating schedule: {str(e)}")
            return False 

    def save_settings(self, settings: dict) -> bool:
        """Save system settings to the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create settings table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Begin transaction
                cursor.execute("BEGIN TRANSACTION")
                
                try:
                    # Save each setting
                    for key, value in settings.items():
                        # Convert value to JSON string if it's not a string
                        if not isinstance(value, str):
                            value = json.dumps(value)
                            
                        cursor.execute("""
                            INSERT OR REPLACE INTO system_settings (key, value, updated_at)
                            VALUES (?, ?, ?)
                        """, (key, value, datetime.now().isoformat()))
                    
                    # Update instance variables for email settings
                    if 'smtp_server' in settings:
                        self.smtp_server = settings['smtp_server']
                    if 'smtp_port' in settings:
                        self.smtp_port = str(settings['smtp_port'])
                    if 'sender_email' in settings:
                        self.sender_email = settings['sender_email']
                    if 'sender_password' in settings:
                        self.sender_password = settings['sender_password']
                    
                    # Commit transaction
                    conn.commit()
                    print("Settings saved successfully")
                    return True
                    
                except Exception as e:
                    conn.rollback()
                    print(f"Error saving settings: {str(e)}")
                    return False
                    
        except Exception as e:
            print(f"Database error while saving settings: {str(e)}")
            return False

    def get_settings(self) -> dict:
        """Get system settings from the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create settings table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Get all settings
                cursor.execute("SELECT key, value FROM system_settings")
                settings = dict(cursor.fetchall())
                
                # Try to parse JSON values
                for key, value in settings.items():
                    try:
                        settings[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        # Keep as string if not valid JSON
                        pass
                
                return settings
                
        except Exception as e:
            print(f"Error getting settings: {str(e)}")
            return {} 

    def pause_schedule(self, schedule_id: str) -> bool:
        """Pause a schedule"""
        try:
            # Get the schedule
            schedule = self.get_schedule(schedule_id)
            if not schedule:
                print(f"Schedule {schedule_id} not found")
                return False

            # Pause the job in the scheduler
            if self.scheduler.get_job(schedule_id):
                self.scheduler.pause_job(schedule_id)
                print(f"Paused job {schedule_id} in scheduler")

            # Update status in database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE schedules 
                    SET status = 'paused'
                    WHERE id = ?
                """, (schedule_id,))
                conn.commit()
                print(f"Updated schedule {schedule_id} status to paused")
                return True

        except Exception as e:
            print(f"Error pausing schedule: {str(e)}")
            return False

    def resume_schedule(self, schedule_id: str) -> bool:
        """Resume a paused schedule"""
        try:
            # Get the schedule
            schedule = self.get_schedule(schedule_id)
            if not schedule:
                print(f"Schedule {schedule_id} not found")
                return False

            # Resume the job in the scheduler
            if self.scheduler.get_job(schedule_id):
                self.scheduler.resume_job(schedule_id)
                print(f"Resumed job {schedule_id} in scheduler")

            # Update status in database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE schedules 
                    SET status = 'active'
                    WHERE id = ?
                """, (schedule_id,))
                conn.commit()
                print(f"Updated schedule {schedule_id} status to active")
                return True

        except Exception as e:
            print(f"Error resuming schedule: {str(e)}")
            return False 

    def schedule_report(self, dataset_name: str, email_config: dict, schedule_config: dict, format_config: dict = None) -> str:
        """Schedule a report to be sent at specified times"""
        try:
            print(f"Scheduling report for dataset: {dataset_name}")
            print(f"Schedule config received: {schedule_config}")
            
            # Create a complete email config with environment variables as defaults
            complete_email_config = {
                'smtp_server': self.smtp_server,
                'smtp_port': int(self.smtp_port),
                'sender_email': self.sender_email,
                'sender_password': self.sender_password,
                **email_config  # This will override any duplicate keys from email_config
            }
            
            # Ensure we have required email fields
            required_email_fields = ['smtp_server', 'smtp_port', 'sender_email', 'sender_password', 'recipients']
            missing_fields = [field for field in required_email_fields if not complete_email_config.get(field)]
            if missing_fields:
                raise ValueError(f"Missing required email configuration fields: {', '.join(missing_fields)}")
            
            # Generate a unique job ID
            job_id = str(uuid.uuid4())
            print(f"Generated job ID: {job_id}")
            
            # Get schedule type
            schedule_type = schedule_config.get('type', '').lower()
            if not schedule_type:
                raise ValueError("Schedule type is required")
                
            print(f"Schedule type: {schedule_type}")
            
            # Store timezone if provided
            timezone = schedule_config.get('timezone', 'UTC')
            try:
                tz = pytz.timezone(timezone)
                print(f"Using timezone: {timezone}")
            except:
                print(f"Invalid timezone: {timezone}, using UTC")
                timezone = 'UTC'
                tz = pytz.UTC
            
            # Schedule based on type
            if schedule_type == 'one-time':
                # One-time schedule - our existing code works fine here
                date_str = schedule_config.get('date')
                
                # Check for time in different formats
                time_str = schedule_config.get('time')
                
                # If time is not provided, try time_str or construct from hour/minute
                if not time_str:
                    time_str = schedule_config.get('time_str')
                    if time_str and ' (' in time_str:
                        # Extract the time part if it includes timezone info like '08:50 (Asia/Kolkata)'
                        time_str = time_str.split(' (')[0]
                
                # If still no time_str, construct it from hour and minute
                if not time_str and 'hour' in schedule_config and 'minute' in schedule_config:
                    hour = int(schedule_config.get('hour', 0))
                    minute = int(schedule_config.get('minute', 0))
                    time_str = f"{hour:02d}:{minute:02d}"
                
                print(f"Date: {date_str}, Time: {time_str}")
                
                if not date_str or not time_str:
                    raise ValueError("Date and time are required for one-time schedule")
                
                # Parse the date and time
                try:
                    date_parts = date_str.split('-')
                    time_parts = time_str.split(':')
                    
                    year = int(date_parts[0])
                    month = int(date_parts[1])
                    day = int(date_parts[2])
                    
                    hour = int(time_parts[0])
                    minute = int(time_parts[1])
                    
                    # Create a timezone-aware datetime
                    run_time = tz.localize(datetime(year, month, day, hour, minute))
                    print(f"Scheduling one-time job for: {run_time.isoformat()}")
                    
                    # Convert to UTC for the scheduler
                    utc_time = run_time.astimezone(pytz.UTC)
                    
                    # Add the job
                    self.scheduler.add_job(
                        func=self.send_report,
                        trigger='date',
                        run_date=utc_time,
                        args=[dataset_name, complete_email_config, format_config],
                        id=job_id,
                        name=f"Report_{dataset_name}",
                        replace_existing=True
                    )
                    
                    # Store the original timezone information to display correctly in UI
                    schedule_config['display_timezone'] = timezone
                    schedule_config['original_time'] = run_time.isoformat()
                    
                except Exception as dt_error:
                    raise ValueError(f"Invalid date or time format: {str(dt_error)}")
            
            elif schedule_type == 'daily':
                # Daily schedule
                print("Processing daily schedule...")
                
                # First try to get hour and minute from time_str if available
                hour = None
                minute = None
                time_str = schedule_config.get('time_str') or schedule_config.get('time')
                
                if time_str:
                    # Extract time from string like "08:30" or "08:30 (UTC)"
                    if ' (' in time_str:
                        time_str = time_str.split(' (')[0]
                    try:
                        time_parts = time_str.split(':')
                        hour = int(time_parts[0])
                        minute = int(time_parts[1])
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing time string {time_str}: {e}")
                
                # If that fails, use hour and minute directly
                if hour is None or minute is None:
                    try:
                        hour = int(schedule_config.get('hour', 0))
                        minute = int(schedule_config.get('minute', 0))
                    except (ValueError, TypeError) as e:
                        raise ValueError(f"Invalid hour or minute values: {e}")
                
                print(f"Scheduling daily job at {hour:02d}:{minute:02d} {timezone}")
                
                # Store timezone information
                schedule_config['display_timezone'] = timezone
                
                # Create the job
                try:
                    self.scheduler.add_job(
                        func=self.send_report,
                        trigger='cron',
                        hour=hour,
                        minute=minute,
                        args=[dataset_name, complete_email_config, format_config],
                        id=job_id,
                        name=f"Report_{dataset_name}",
                        replace_existing=True,
                        timezone=tz
                    )
                    print(f"Daily schedule created with job ID: {job_id}")
                except Exception as sched_error:
                    raise ValueError(f"Error creating daily schedule: {str(sched_error)}")
            
            elif schedule_type == 'weekly':
                # Weekly schedule
                print("Processing weekly schedule...")
                
                # Get days from schedule config
                days = schedule_config.get('days')
                print(f"Days received: {days}")
                
                # Define a mapping from day names to day numbers (0-6, where 0=Monday for APScheduler)
                day_name_to_number = {
                    'monday': 0, 'mon': 0, 
                    'tuesday': 1, 'tue': 1, 
                    'wednesday': 2, 'wed': 2, 
                    'thursday': 3, 'thu': 3, 
                    'friday': 4, 'fri': 4, 
                    'saturday': 5, 'sat': 5, 
                    'sunday': 6, 'sun': 6
                }
                
                # Convert days to integers based on name or index
                day_integers = []
                
                # Handle days as string, list, or comma-separated values
                if isinstance(days, str):
                    if ',' in days:
                        day_items = [d.strip().lower() for d in days.split(',') if d.strip()]
                    else:
                        day_items = [days.lower()]
                elif isinstance(days, (list, tuple)):
                    day_items = [str(d).lower() for d in days]
                else:
                    raise ValueError("Days must be provided as a list, comma-separated string, or single value")
                
                # Convert each day to its numerical value
                for day in day_items:
                    try:
                        # Try parsing as a direct integer (0-6)
                        day_int = int(day)
                        if 0 <= day_int <= 6:
                            day_integers.append(day_int)
                        else:
                            raise ValueError(f"Day number must be between 0 and 6, got {day_int}")
                    except ValueError:
                        # Try converting from day name to number
                        if day in day_name_to_number:
                            day_integers.append(day_name_to_number[day])
                        else:
                            raise ValueError(f"Invalid day name: {day}")
                
                if not day_integers:
                    raise ValueError("At least one day must be selected for weekly schedule")
                    
                # Get hour and minute, similar to daily
                hour = None
                minute = None
                time_str = schedule_config.get('time_str') or schedule_config.get('time')
                
                if time_str:
                    if ' (' in time_str:
                        time_str = time_str.split(' (')[0]
                    try:
                        time_parts = time_str.split(':')
                        hour = int(time_parts[0])
                        minute = int(time_parts[1])
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing time string {time_str}: {e}")
                
                if hour is None or minute is None:
                    try:
                        hour = int(schedule_config.get('hour', 0))
                        minute = int(schedule_config.get('minute', 0))
                    except (ValueError, TypeError) as e:
                        raise ValueError(f"Invalid hour or minute values: {e}")
                
                # Convert days to string format for cron (0=Monday in APScheduler)
                day_str = ','.join(str(day) for day in day_integers)
                print(f"Scheduling weekly job for days {day_str} at {hour:02d}:{minute:02d} {timezone}")
                
                # Store timezone information
                schedule_config['display_timezone'] = timezone
                
                # Create the job
                try:
                    self.scheduler.add_job(
                        func=self.send_report,
                        trigger='cron',
                        day_of_week=day_str,
                        hour=hour,
                        minute=minute,
                        args=[dataset_name, complete_email_config, format_config],
                        id=job_id,
                        name=f"Report_{dataset_name}",
                        replace_existing=True,
                        timezone=tz
                    )
                    print(f"Weekly schedule created with job ID: {job_id}")
                except Exception as sched_error:
                    print(f"Error creating weekly schedule: {str(sched_error)}")
                    print(f"Traceback: {traceback.format_exc()}")
                    raise ValueError(f"Error creating weekly schedule: {str(sched_error)}")
            
            elif schedule_type == 'monthly':
                # Monthly schedule
                print("Processing monthly schedule...")
                
                # Get day of month
                day_type = schedule_config.get('day_type', 'specific')
                
                # Handle different types of monthly schedules
                if day_type == 'specific':
                    try:
                        day = int(schedule_config.get('day', 1))
                        if day < 1 or day > 31:
                            raise ValueError(f"Day must be between 1 and 31, got {day}")
                        day_spec = str(day)
                    except (ValueError, TypeError) as e:
                        raise ValueError(f"Invalid day value: {e}")
                elif day_type == 'last':
                    day_spec = 'last'
                elif day_type == 'first_weekday':
                    day_spec = '1'  # We'll handle this special case later
                elif day_type == 'last_weekday':
                    day_spec = 'last'  # We'll handle this special case later
                else:
                    raise ValueError(f"Invalid day_type: {day_type}")
                
                # Get hour and minute, similar to daily
                hour = None
                minute = None
                time_str = schedule_config.get('time_str') or schedule_config.get('time')
                
                if time_str:
                    if ' (' in time_str:
                        time_str = time_str.split(' (')[0]
                    try:
                        time_parts = time_str.split(':')
                        hour = int(time_parts[0])
                        minute = int(time_parts[1])
                    except (ValueError, IndexError) as e:
                        print(f"Error parsing time string {time_str}: {e}")
                
                if hour is None or minute is None:
                    try:
                        hour = int(schedule_config.get('hour', 0))
                        minute = int(schedule_config.get('minute', 0))
                    except (ValueError, TypeError) as e:
                        raise ValueError(f"Invalid hour or minute values: {e}")
                
                print(f"Scheduling monthly job for day {day_spec} at {hour:02d}:{minute:02d} {timezone}")
                
                # Store timezone information
                schedule_config['display_timezone'] = timezone
                
                # Create the job
                try:
                    self.scheduler.add_job(
                        func=self.send_report,
                        trigger='cron',
                        day=day_spec,
                        hour=hour,
                        minute=minute,
                        args=[dataset_name, complete_email_config, format_config],
                        id=job_id,
                        name=f"Report_{dataset_name}",
                        replace_existing=True,
                        timezone=tz
                    )
                    print(f"Monthly schedule created with job ID: {job_id}")
                except Exception as sched_error:
                    raise ValueError(f"Error creating monthly schedule: {str(sched_error)}")
            
            else:
                # Invalid schedule type
                raise ValueError(f"Invalid schedule type: {schedule_type}")
            
            # Save schedule to database
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO schedules (
                            id, dataset_name, schedule_type, schedule_config, 
                            email_config, format_config, created_at, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        job_id,
                        dataset_name,
                        schedule_type,
                        json.dumps(schedule_config),
                        json.dumps(complete_email_config),
                        json.dumps(format_config) if format_config else None,
                        datetime.now().isoformat(),
                        'active'
                    ))
                    conn.commit()
                    print(f"Schedule saved to database with ID: {job_id}")
                    return job_id
            except Exception as db_error:
                print(f"Error saving schedule to database: {str(db_error)}")
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)
                return None
            
        except Exception as e:
            print(f"Error scheduling report: {str(e)}")
            traceback.print_exc()  # Print the full traceback for debugging
            return None

    def get_report_url(self, report_path: Path) -> str:
        """Generate a URL for a report file
        
        Args:
            report_path: Path to the report file
            
        Returns:
            str: URL to access the report
        """
        try:
            # Generate the relative path
            static_dir = Path('static')
            if report_path.is_absolute():
                # Try to make it relative to the static directory
                try:
                    relative_path = report_path.relative_to(static_dir)
                    url_path = f"static/{relative_path}"
                except ValueError:
                    # If not in static directory, just use the filename
                    url_path = f"static/reports/{report_path.name}"
            else:
                # Already relative
                url_path = str(report_path)
                
            # Ensure base_url is set
            if not hasattr(self, 'base_url') or not self.base_url:
                self.base_url = os.getenv('BASE_URL', 'http://localhost:8501')
                
            # Create the full URL
            if self.base_url.endswith('/'):
                url = f"{self.base_url}{url_path}"
            else:
                url = f"{self.base_url}/{url_path}"
                
            print(f"Generated report URL: {url}")
            return url
            
        except Exception as e:
            print(f"Error generating report URL: {str(e)}")
            return f"file://{report_path}" 