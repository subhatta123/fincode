import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
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

class ReportManager:
    def __init__(self):
        """Initialize report manager"""
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
        
        # Load email settings from environment variables
        self.smtp_server = os.getenv('SMTP_SERVER')
        self.smtp_port = os.getenv('SMTP_PORT')
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('SENDER_PASSWORD')
        
        # Initialize scheduler
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.load_saved_schedules()
        
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
                
                # Load existing schedules from JSON if they exist
                if self.schedules_file.exists():
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

    def save_report(self, df: pd.DataFrame, dataset_name: str) -> Path:
        """Save a report to the public reports directory"""
        try:
            # Generate PDF from DataFrame
            pdf_buffer = self.generate_pdf(df, f"Report: {dataset_name}")
            
            # Generate a unique filename using a hash of the content and timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            content_hash = hashlib.sha256(pdf_buffer.getvalue()).hexdigest()
            filename = f"{content_hash}_{timestamp}.pdf"
            
            # Save to public reports directory
            report_path = self.public_reports_dir / filename
            with open(report_path, 'wb') as f:
                f.write(pdf_buffer.getvalue())
            
            print(f"Saved report to: {report_path}")
            return report_path
            
        except Exception as e:
            print(f"Failed to save report: {str(e)}")
            print(f"Error details: {e.__dict__ if hasattr(e, '__dict__') else 'No details'}")
            return None

    def get_report_url(self, report_path: Path) -> str:
        """Get the URL for accessing a report"""
        try:
            if not report_path.exists():
                print(f"Report file does not exist: {report_path}")
                return None
                
            # Get the filename
            filename = report_path.name
            
            # Generate the URL with proper formatting
            # Remove any backslashes and use forward slashes for web URLs
            url = f"{self.base_url.rstrip('/')}/static/reports/{filename}"
            print(f"Generated report URL: {url}")
            return url
            
        except Exception as e:
            print(f"Failed to generate report URL: {str(e)}")
            return None

    def _serialize_format_config(self, format_config):
        """Serialize format config for JSON storage"""
        if not format_config:
            return None
            
        # Create a serializable copy of the format config
        serializable_config = {
            'page_size': format_config.get('page_size', None),
            'orientation': format_config.get('orientation', 'portrait'),
            'margins': format_config.get('margins', None),
            'chart_size': format_config.get('chart_size', None),
            'report_content': format_config.get('report_content', {}),
        }
        
        # Handle title style
        if 'title_style' in format_config:
            title_style = format_config['title_style']
            # Convert color to hex string if it exists
            text_color = getattr(title_style, 'textColor', None)
            if text_color:
                if hasattr(text_color, 'rgb'):
                    # Convert RGB values to integers (0-255)
                    rgb = [int(x * 255) if isinstance(x, float) else x for x in text_color.rgb()]
                    text_color = '#{:02x}{:02x}{:02x}'.format(*rgb)
                elif hasattr(text_color, 'hexval'):
                    text_color = '#{:06x}'.format(text_color.hexval())
                else:
                    text_color = '#000000'
            else:
                text_color = '#000000'
                
            serializable_config['title_style'] = {
                'fontName': getattr(title_style, 'fontName', 'Helvetica'),
                'fontSize': getattr(title_style, 'fontSize', 24),
                'alignment': getattr(title_style, 'alignment', 1),  # 0=left, 1=center, 2=right
                'textColor': text_color,
                'spaceAfter': getattr(title_style, 'spaceAfter', 30)
            }
        
        # Handle table style
        if 'table_style' in format_config:
            table_style = format_config['table_style']
            # Convert TableStyle commands to serializable format
            serializable_config['table_style'] = []
            
            # Get the commands from the TableStyle object
            if hasattr(table_style, 'commands'):
                commands = table_style.commands
            elif hasattr(table_style, '_cmds'):
                commands = table_style._cmds
            else:
                commands = []
                
            for cmd in commands:
                # Convert command to serializable format
                try:
                    if len(cmd) != 4:
                        print(f"Skipping invalid command: {cmd}")
                        continue
                        
                    cmd_name, start_pos, end_pos, value = cmd
                    
                    # Convert color objects to hex strings
                    if hasattr(value, 'rgb'):
                        # Convert RGB values to integers (0-255)
                        rgb = [int(x * 255) if isinstance(x, float) else x for x in value.rgb()]
                        value = '#{:02x}{:02x}{:02x}'.format(*rgb)
                    elif hasattr(value, 'hexval'):
                        value = '#{:06x}'.format(value.hexval())
                    elif isinstance(value, (int, float)):
                        # Keep numeric values as is
                        value = float(value)
                    
                    # Convert tuples to lists for JSON serialization
                    serialized_cmd = [
                        cmd_name,
                        list(start_pos) if isinstance(start_pos, tuple) else start_pos,
                        list(end_pos) if isinstance(end_pos, tuple) else end_pos,
                        value
                    ]
                    serializable_config['table_style'].append(serialized_cmd)
                except Exception as e:
                    print(f"Error serializing table style command {cmd}: {str(e)}")
                    continue
        
        return serializable_config
    
    def _deserialize_format_config(self, serialized_config):
        """Deserialize format config from JSON storage"""
        if not serialized_config:
            return None
            
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.colors import HexColor, Color
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
        
        # Create a new format config
        format_config = {
            'page_size': serialized_config.get('page_size', None),
            'orientation': serialized_config.get('orientation', 'portrait'),
            'margins': serialized_config.get('margins', None),
            'chart_size': serialized_config.get('chart_size', None),
            'report_content': serialized_config.get('report_content', {})
        }
        
        # Reconstruct title style
        if 'title_style' in serialized_config:
            title_style_data = serialized_config['title_style']
            alignment_map = {0: TA_LEFT, 1: TA_CENTER, 2: TA_RIGHT}
            
            # Convert hex color string to Color object
            text_color = title_style_data.get('textColor', '#000000')
            if isinstance(text_color, str) and text_color.startswith('#'):
                text_color = HexColor(text_color)
            
            # Get base styles
            styles = getSampleStyleSheet()
            
            # Create title style with proper parent
            format_config['title_style'] = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontName=title_style_data.get('fontName', 'Helvetica'),
                fontSize=title_style_data.get('fontSize', 24),
                alignment=alignment_map.get(title_style_data.get('alignment', 1), TA_CENTER),
                textColor=text_color,
                spaceAfter=title_style_data.get('spaceAfter', 30)
            )
        
        # Reconstruct table style
        if 'table_style' in serialized_config:
            from reportlab.platypus import TableStyle
            try:
                # Convert serialized commands back to TableStyle format
                commands = []
                for cmd in serialized_config['table_style']:
                    # Convert command back to proper format
                    command_name = cmd[0]
                    start_pos = tuple(cmd[1]) if isinstance(cmd[1], list) else cmd[1]
                    end_pos = tuple(cmd[2]) if isinstance(cmd[2], list) else cmd[2]
                    
                    # Handle color values
                    value = cmd[3]
                    if isinstance(value, str) and value.startswith('#'):
                        value = HexColor(value)
                    elif isinstance(value, (int, float)):
                        value = float(value)  # Convert to float for consistency
                    
                    commands.append((command_name, start_pos, end_pos, value))
                
                format_config['table_style'] = TableStyle(commands)
            except Exception as e:
                print(f"Error reconstructing table style: {str(e)}")
                # Use a default table style if reconstruction fails
                format_config['table_style'] = TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('GRID', (0, 0), (-1, -1), 1, colors.gray)
                ])
        
        return format_config

    def schedule_report(self, dataset_name: str, email_config: dict, schedule_config: dict, format_config: dict = None, existing_job_id: str = None) -> str:
        """Schedule a report based on configuration"""
        try:
            # Input validation
            if not dataset_name or not email_config or not schedule_config:
                raise ValueError("Missing required parameters for scheduling")
            
            # Validate schedule configuration
            if 'type' not in schedule_config:
                raise ValueError("Schedule type not specified")
            
            # Validate email configuration
            if not email_config.get('recipients'):
                raise ValueError("No email recipients specified")

            # Generate job_id if not provided
            job_id = existing_job_id or str(uuid.uuid4())
            
            # Create serializable copies of configurations
            def make_serializable(obj):
                """Create a JSON-serializable copy of an object"""
                if isinstance(obj, (str, int, float, bool, type(None))):
                    return obj
                elif isinstance(obj, (list, tuple)):
                    return [make_serializable(item) for item in obj]
                elif isinstance(obj, dict):
                    return {str(k): make_serializable(v) for k, v in obj.items()}
                else:
                    return str(obj)

            email_config_copy = make_serializable(email_config)
            schedule_config_copy = make_serializable(schedule_config)
            format_config_copy = make_serializable(format_config) if format_config else None

            # Get timezone
            timezone_str = schedule_config.get('timezone', 'UTC')
            try:
                timezone = pytz.timezone(timezone_str)
            except:
                print(f"Invalid timezone {timezone_str}, using UTC")
                timezone = pytz.UTC

            # Save schedule to database first
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO schedules (
                            id, dataset_name, schedule_type, schedule_config, 
                            email_config, format_config, timezone, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        job_id,
                        dataset_name,
                        schedule_config['type'],
                        json.dumps(schedule_config_copy),
                        json.dumps(email_config_copy),
                        json.dumps(format_config_copy) if format_config_copy else None,
                        timezone_str,
                        'active'
                    ))
                    conn.commit()
            except Exception as db_error:
                raise Exception(f"Failed to save schedule to database: {str(db_error)}")

            # Create the job based on schedule type
            try:
                if schedule_config['type'] == 'one-time':
                    if 'date' not in schedule_config:
                        raise ValueError("Date not specified for one-time schedule")
                    
                    # Parse date and time in the specified timezone
                    schedule_date = datetime.strptime(
                        f"{schedule_config['date']} {schedule_config['hour']:02d}:{schedule_config['minute']:02d}:00",
                        "%Y-%m-%d %H:%M:%S"
                    )
                    schedule_date = timezone.localize(schedule_date)
                    
                    # Add job to scheduler
                    self.scheduler.add_job(
                        func=self.send_report,
                        trigger='date',
                        run_date=schedule_date,
                        args=[dataset_name, email_config_copy, format_config_copy],
                        id=job_id,
                        name=f"Report_{dataset_name}",
                        replace_existing=True,
                        timezone=timezone
                    )
                
                elif schedule_config['type'] == 'daily':
                    self.scheduler.add_job(
                        func=self.send_report,
                        trigger='cron',
                        hour=schedule_config['hour'],
                        minute=schedule_config['minute'],
                        args=[dataset_name, email_config_copy, format_config_copy],
                        id=job_id,
                        name=f"Report_{dataset_name}",
                        replace_existing=True,
                        timezone=timezone
                    )
                
                elif schedule_config['type'] == 'weekly':
                    self.scheduler.add_job(
                        func=self.send_report,
                        trigger='cron',
                        day_of_week=schedule_config['day'],
                        hour=schedule_config['hour'],
                        minute=schedule_config['minute'],
                        args=[dataset_name, email_config_copy, format_config_copy],
                        id=job_id,
                        name=f"Report_{dataset_name}",
                        replace_existing=True,
                        timezone=timezone
                    )
                
                elif schedule_config['type'] == 'monthly':
                    self.scheduler.add_job(
                        func=self.send_report,
                        trigger='cron',
                        day=schedule_config['day'],
                        hour=schedule_config['hour'],
                        minute=schedule_config['minute'],
                        args=[dataset_name, email_config_copy, format_config_copy],
                        id=job_id,
                        name=f"Report_{dataset_name}",
                        replace_existing=True,
                        timezone=timezone
                    )
                
                else:
                    raise ValueError(f"Invalid schedule type: {schedule_config['type']}")
                
                print(f"Successfully scheduled report with ID: {job_id}")
                return job_id
                
            except Exception as scheduler_error:
                print(f"Failed to create schedule: {str(scheduler_error)}")
                # Clean up if job was partially created
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)
                return None
                
        except Exception as e:
            print(f"Failed to schedule report: {str(e)}")
            return None

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

    def send_report(self, dataset_name: str, email_config: dict, format_config: dict = None):
        """Send scheduled report"""
        try:
            print(f"\nStarting to send report for dataset: {dataset_name}")
            print(f"Email config: {email_config}")
            print(f"Format config: {format_config}")
            
            # Deserialize format_config if it's a string
            if isinstance(format_config, str):
                try:
                    format_config = json.loads(format_config)
                except Exception as format_error:
                    print(f"Error parsing format_config: {str(format_error)}")
                    format_config = None
            
            # Try to refresh dataset from Tableau if connection details are available
            try:
                # Get Tableau connection details from the database
                with sqlite3.connect('data/tableau_data.db') as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT server_url, auth_method, credentials, site_name, workbook_name, view_ids, view_names
                        FROM _internal_tableau_connections 
                        WHERE dataset_name = ?
                    """, (dataset_name,))
                    connection_details = cursor.fetchone()
                    
                if connection_details:
                    try:
                        server_url, auth_method, credentials_json, site_name, workbook_name, view_ids_json, view_names_json = connection_details
                        credentials = json.loads(credentials_json)
                        view_ids = json.loads(view_ids_json)
                        view_names = json.loads(view_names_json)
                        
                        # Authenticate with Tableau
                        server = authenticate(server_url, auth_method, credentials, site_name)
                        
                        # Download fresh data
                        if download_and_save_data(server, view_ids, workbook_name, view_names, dataset_name):
                            print("Successfully refreshed dataset from Tableau")
                        else:
                            print("Failed to refresh dataset, will use saved data")
                    except Exception as auth_error:
                        print(f"Could not authenticate with Tableau: {str(auth_error)}")
                        print("Will proceed with saved dataset")
                else:
                    print("No Tableau connection details found, will use saved dataset")
            except Exception as db_error:
                print(f"Database error checking connection details: {str(db_error)}")
                print("Will proceed with saved dataset")
            
            # Use class-level email settings if not provided in email_config
            email_config = email_config.copy()  # Create a copy to avoid modifying the original
            email_config.setdefault('smtp_server', self.smtp_server)
            email_config.setdefault('smtp_port', self.smtp_port)
            email_config.setdefault('sender_email', self.sender_email)
            email_config.setdefault('sender_password', self.sender_password)
            
            # Validate email configuration
            required_email_fields = ['smtp_server', 'smtp_port', 'sender_email', 'sender_password', 'recipients']
            missing_fields = [field for field in required_email_fields if not email_config.get(field)]
            if missing_fields:
                raise ValueError(f"Missing required email configuration fields: {', '.join(missing_fields)}")
            
            # Load dataset
            try:
                with sqlite3.connect('data/tableau_data.db') as conn:
                    print("Loading dataset from database...")
                    df = pd.read_sql_query(f"SELECT * FROM '{dataset_name}'", conn)
                    print(f"Loaded {len(df)} rows from dataset")
                
                if df.empty:
                    raise ValueError(f"No data found in dataset: {dataset_name}")
            except Exception as load_error:
                raise Exception(f"Failed to load dataset: {str(load_error)}")
            
            # Get the message body or use default
            message_body = email_config.get('body', '').strip()
            if not message_body:
                message_body = f"Please find attached the scheduled report for dataset: {dataset_name}"
            
            print("Generating report...")
            # Generate report with formatting settings
            if format_config:
                from report_formatter_new import ReportFormatter
                formatter = ReportFormatter()
                
                # Apply saved formatting settings
                if isinstance(format_config, dict):
                    if format_config.get('page_size'):
                        formatter.page_size = format_config['page_size']
                    if format_config.get('orientation'):
                        formatter.orientation = format_config['orientation']
                    if format_config.get('margins'):
                        formatter.margins = format_config['margins']
                    
                    # Handle title style
                    if format_config.get('title_style'):
                        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                        from reportlab.lib.colors import HexColor
                        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
                        
                        styles = getSampleStyleSheet()
                        title_style_data = format_config['title_style']
                        
                        if isinstance(title_style_data, dict):
                            # Create new ParagraphStyle
                            formatter.title_style = ParagraphStyle(
                                'CustomTitle',
                                parent=styles['Title'],
                                fontName=title_style_data.get('fontName', 'Helvetica'),
                                fontSize=title_style_data.get('fontSize', 24),
                                alignment=title_style_data.get('alignment', TA_CENTER),
                                textColor=HexColor(title_style_data.get('textColor', '#000000')),
                                spaceAfter=title_style_data.get('spaceAfter', 30)
                            )
                    
                    # Handle table style
                    if format_config.get('table_style'):
                        from reportlab.platypus import TableStyle
                        table_style_data = format_config['table_style']
                        
                        if isinstance(table_style_data, list):
                            # Convert commands to TableStyle
                            commands = []
                            for cmd in table_style_data:
                                if isinstance(cmd, list) and len(cmd) == 4:
                                    command_name = cmd[0]
                                    start_pos = tuple(cmd[1]) if isinstance(cmd[1], list) else cmd[1]
                                    end_pos = tuple(cmd[2]) if isinstance(cmd[2], list) else cmd[2]
                                    value = cmd[3]
                                    
                                    # Handle color values
                                    if isinstance(value, str) and value.startswith('#'):
                                        value = HexColor(value)
                                    elif isinstance(value, (int, float)):
                                        value = float(value)
                                    
                                    commands.append((command_name, start_pos, end_pos, value))
                            
                            formatter.table_style = TableStyle(commands)
                    
                    if format_config.get('chart_size'):
                        formatter.chart_size = format_config['chart_size']
                    
                    # Get selected columns and other content settings
                    selected_columns = format_config.get('selected_columns', df.columns.tolist())
                    df_selected = df[selected_columns]
                    
                    # Generate formatted report
                    report_title = format_config.get('report_title', f"Report: {dataset_name}")
                    pdf_buffer = formatter.generate_report(
                        df_selected,
                        include_row_count=format_config.get('include_row_count', True),
                        include_totals=format_config.get('include_totals', True),
                        include_averages=format_config.get('include_averages', True),
                        report_title=report_title
                    )
                else:
                    print("Format config is not a dictionary, using default formatting...")
                    pdf_buffer = self.generate_pdf(df, f"Report: {dataset_name}")
            else:
                # Use default formatting if no format_config provided
                print("Using default formatting...")
                pdf_buffer = self.generate_pdf(df, f"Report: {dataset_name}")
            
            # Save report
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            content_hash = hashlib.sha256(pdf_buffer.getvalue()).hexdigest()
            filename = f"{content_hash}_{timestamp}.pdf"
            file_path = self.public_reports_dir / filename
            
            with open(file_path, 'wb') as f:
                f.write(pdf_buffer.getvalue())
            print(f"Report saved to: {file_path}")
            
            # Generate shareable link
            share_link = self.get_report_url(file_path)
            if not share_link:
                print("Warning: Failed to generate shareable link")
                share_link = f"File: {file_path.name}"
            
            print("Preparing email...")
            # Create email
            msg = MIMEMultipart()
            msg['From'] = email_config['sender_email']
            msg['To'] = ', '.join(email_config['recipients'])
            msg['Subject'] = f"Scheduled Report: {dataset_name}"
            
            # Format email body with custom message, report details, and link
            email_body = f"""{message_body}

Report Details:
- Dataset: {dataset_name}
- Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

View and download your report here:
{share_link}

(Link expires in 24 hours)

This is an automated report. Please do not reply to this email."""

            msg.attach(MIMEText(email_body, 'plain'))
            
            # Attach report file
            print("Attaching report file...")
            with open(file_path, 'rb') as f:
                attachment = MIMEApplication(f.read(), _subtype='pdf')
                attachment.add_header('Content-Disposition', 'attachment', filename=file_path.name)
                msg.attach(attachment)
            
            # Send email with proper SMTP connection handling
            print(f"Sending email to: {email_config['recipients']}")
            try:
                with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                    server.starttls()
                    print("Logging in to SMTP server...")
                    server.login(email_config['sender_email'], email_config['sender_password'])
                    print("Sending email...")
                    server.send_message(msg)
                    print("Email sent successfully!")
            except smtplib.SMTPAuthenticationError:
                raise Exception("Failed to authenticate with SMTP server. Please check your email credentials.")
            except smtplib.SMTPException as smtp_error:
                raise Exception(f"SMTP error: {str(smtp_error)}")
            
            # Send WhatsApp message if configured
            if self.twilio_client and email_config.get('whatsapp_recipients'):
                print("Sending WhatsApp notifications...")
                # Format WhatsApp message with custom message, report details, and link
                whatsapp_body = f"""📊 *Scheduled Report: {dataset_name}*

{message_body}

*Report Details:*
- Dataset: {dataset_name}
- Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔗 *View and Download Report:*
{share_link}

_(Link expires in 24 hours)_"""
                
                for recipient in email_config['whatsapp_recipients']:
                    print(f"Sending WhatsApp message to: {recipient}")
                    if self.send_whatsapp_message(recipient, whatsapp_body):
                        print(f"WhatsApp notification sent to {recipient}")
                    else:
                        print(f"WhatsApp notification failed for {recipient}. Please check if the number is opted in.")
            
            print(f"Report sent successfully for dataset: {dataset_name}")
            
        except Exception as e:
            error_msg = f"Failed to send report: {str(e)}"
            print(error_msg)
            print(f"Error type: {type(e)}")
            print(f"Error details: {e.__dict__ if hasattr(e, '__dict__') else 'No details'}")
            raise Exception(error_msg) from e
    
    def remove_schedule(self, job_id: str) -> bool:
        """Remove a scheduled report"""
        try:
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
                        SET status = 'deleted' 
                        WHERE id = ?
                    """, (job_id,))
                    conn.commit()
                    print(f"Successfully removed schedule {job_id} from database")
                    return True
                else:
                    print(f"Schedule {job_id} not found in database")
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
        """Load and activate saved schedules from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM schedules WHERE status = 'active'")
                schedules = cursor.fetchall()
                
                for schedule in schedules:
                    schedule_id = schedule[0]
                    dataset_name = schedule[1]
                    schedule_config = json.loads(schedule[3])
                    email_config = json.loads(schedule[4])
                    format_config = json.loads(schedule[5]) if schedule[5] else None
                    
                    # Check if job already exists in scheduler
                    if not self.scheduler.get_job(schedule_id):
                        self.schedule_report(
                            dataset_name,
                            email_config,
                            schedule_config,
                            format_config,
                            existing_job_id=schedule_id
                        )
                
                print(f"Loaded {len(schedules)} saved schedules")
        except Exception as e:
            print(f"Error loading saved schedules: {str(e)}")

    def get_active_schedules(self) -> dict:
        """Get all active schedules from the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, dataset_name, schedule_type, schedule_config, 
                           email_config, format_config, created_at, last_run, 
                           next_run, status 
                    FROM schedules 
                    WHERE status = 'active'
                """)
                rows = cursor.fetchall()
                
                schedules = {}
                for row in rows:
                    schedule_id = row[0]
                    schedules[schedule_id] = {
                        'dataset_name': row[1],
                        'schedule_type': row[2],
                        'schedule_config': json.loads(row[3]),
                        'email_config': json.loads(row[4]),
                        'format_config': json.loads(row[5]) if row[5] else None,
                        'created_at': row[6],
                        'last_run': row[7],
                        'next_run': row[8],
                        'status': row[9]
                    }
                
                print(f"Found {len(schedules)} active schedules")
                return schedules
                
        except Exception as e:
            print(f"Error getting active schedules: {str(e)}")
            return {} 