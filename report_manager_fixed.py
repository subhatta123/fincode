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
from tableau_streamlit_app import authenticate, download_and_save_data

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
                
                # Create tableau_connections table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tableau_connections (
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
                
                conn.commit()
                print("Database initialized successfully")
        except Exception as e:
            print(f"Error initializing database: {str(e)}")
    
    def send_report(self, dataset_name: str, email_config: dict, format_config: dict = None):
        """Send scheduled report"""
        try:
            print(f"\nStarting to send report for dataset: {dataset_name}")
            print(f"Email config: {email_config}")
            print(f"Format config: {format_config}")
            
            # Refresh dataset from Tableau if connection details are available
            try:
                # Get Tableau connection details from the database
                with sqlite3.connect('data/tableau_data.db') as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT server_url, auth_method, credentials, site_name, workbook_name, view_ids, view_names
                        FROM tableau_connections 
                        WHERE dataset_name = ?
                    """, (dataset_name,))
                    connection_details = cursor.fetchone()
                    
                if connection_details:
                    server_url, auth_method, credentials_json, site_name, workbook_name, view_ids_json, view_names_json = connection_details
                    credentials = json.loads(credentials_json)
                    view_ids = json.loads(view_ids_json)
                    view_names = json.loads(view_names_json)
                    
                    # Authenticate with Tableau
                    server = authenticate(server_url, auth_method, credentials, site_name)
                    
                    # Download fresh data
                    if not download_and_save_data(server, view_ids, workbook_name, view_names, dataset_name):
                        raise Exception("Failed to refresh dataset from Tableau")
                    
                    print("Successfully refreshed dataset from Tableau")
            except Exception as refresh_error:
                print(f"Warning: Failed to refresh dataset from Tableau: {str(refresh_error)}")
            
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
            with sqlite3.connect('data/tableau_data.db') as conn:
                print("Loading dataset from database...")
                df = pd.read_sql_query(f"SELECT * FROM '{dataset_name}'", conn)
                print(f"Loaded {len(df)} rows from dataset")
            
            if df.empty:
                print(f"No data found in dataset: {dataset_name}")
                return
            
            # Get the message body or use default
            message_body = email_config.get('body', '').strip()
            if not message_body:
                message_body = f"Please find attached the scheduled report for dataset: {dataset_name}"
            
            # Generate and save report
            report_title = f"Report: {dataset_name}"
            pdf_buffer = self.generate_pdf(df, report_title)
            
            # Save report to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{dataset_name}_{timestamp}.pdf"
            file_path = self.reports_dir / filename
            with open(file_path, 'wb') as f:
                f.write(pdf_buffer.getvalue())
            
            # Generate shareable link
            share_link = self.get_report_url(file_path)
            
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
            with open(file_path, 'rb') as f:
                attachment = MIMEApplication(f.read(), _subtype='pdf')
                attachment.add_header('Content-Disposition', 'attachment', filename=filename)
                msg.attach(attachment)
            
            # Send email
            with smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port']) as server:
                server.starttls()
                server.login(email_config['sender_email'], email_config['sender_password'])
                server.send_message(msg)
            
            # Send WhatsApp message if configured
            if self.twilio_client and email_config.get('whatsapp_recipients'):
                # Format WhatsApp message
                whatsapp_body = f"""📊 *Scheduled Report: {dataset_name}*

{message_body}

*Report Details:*
- Dataset: {dataset_name}
- Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔗 *View and Download Report:*
{share_link}

_(Link expires in 24 hours)_"""
                
                for recipient in email_config['whatsapp_recipients']:
                    if self.send_whatsapp_message(recipient, whatsapp_body):
                        print(f"WhatsApp notification sent to {recipient}")
                    else:
                        print(f"WhatsApp notification failed for {recipient}")
            
            print(f"Report sent successfully for dataset: {dataset_name}")
            
        except Exception as e:
            error_msg = f"Failed to send report: {str(e)}"
            print(error_msg)
            print(f"Error type: {type(e)}")
            print(f"Error details: {e.__dict__ if hasattr(e, '__dict__') else 'No details'}")
            raise Exception(error_msg) from e
    
    def get_schedule_description(self, schedule_config: dict) -> str:
        """Get a human-readable description of a schedule"""
        try:
            schedule_type = schedule_config.get('type')
            if not schedule_type:
                return "Invalid schedule"

            hour = schedule_config.get('hour', 0)
            minute = schedule_config.get('minute', 0)
            timezone = schedule_config.get('timezone', 'UTC')
            time_str = f"{hour:02d}:{minute:02d} {timezone}"

            if schedule_type == 'one-time':
                date = schedule_config.get('date')
                if not date:
                    return "Invalid one-time schedule"
                return f"One time on {date} at {time_str}"

            elif schedule_type == 'daily':
                return f"Daily at {time_str}"

            elif schedule_type == 'weekly':
                days = schedule_config.get('days', [])
                if not days:
                    return "Invalid weekly schedule"
                
                # Convert day indices to names
                day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                day_str = ", ".join([day_names[day] for day in days])
                return f"Weekly on {day_str} at {time_str}"

            elif schedule_type == 'monthly':
                day_option = schedule_config.get('day_option', 'Specific Day')
                
                if day_option == 'Last Day':
                    return f"Monthly on the last day at {time_str}"
                elif day_option == 'First Weekday':
                    return f"Monthly on the first weekday at {time_str}"
                elif day_option == 'Last Weekday':
                    return f"Monthly on the last weekday at {time_str}"
                else:
                    day = schedule_config.get('day')
                    if not day:
                        return "Invalid monthly schedule"
                    return f"Monthly on day {day} at {time_str}"

            else:
                return "Invalid schedule type"
            
        except Exception as e:
            print(f"Error generating schedule description: {str(e)}")
            return "Invalid schedule configuration"
    
    def generate_pdf(self, df: pd.DataFrame, title: str) -> io.BytesIO:
        """Generate PDF report from DataFrame"""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
        elements = []
        
        # Add title
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontSize=24,
            spaceAfter=30
        )
        elements.append(Paragraph(title, title_style))
        
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp_style = ParagraphStyle(
            'Timestamp',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.gray,
            spaceAfter=20
        )
        elements.append(Paragraph(f"Generated on: {timestamp}", timestamp_style))
        
        # Add summary statistics
        summary_style = ParagraphStyle(
            'Summary',
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
    
    def get_report_url(self, report_path: Path) -> str:
        """Generate a shareable URL for a report"""
        # Create a unique filename using hash of original path and timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = report_path.name
        hash_input = f"{original_name}_{timestamp}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        public_filename = f"{hash_value}_{original_name}"
        
        # Copy report to public directory
        public_path = self.public_reports_dir / public_filename
        shutil.copy2(report_path, public_path)
        
        # Schedule cleanup after 24 hours
        cleanup_time = datetime.now() + timedelta(hours=24)
        self.scheduler.add_job(
            self._cleanup_report,
            'date',
            run_date=cleanup_time,
            args=[public_path]
        )
        
        # Return shareable URL
        base_url = os.getenv('BASE_URL', 'http://localhost:8501')
        return f"{base_url}/reports/{public_filename}"
    
    def _cleanup_report(self, report_path: Path):
        """Clean up expired report file"""
        try:
            if report_path.exists():
                report_path.unlink()
                print(f"Cleaned up expired report: {report_path}")
        except Exception as e:
            print(f"Error cleaning up report {report_path}: {str(e)}")
    
    def send_whatsapp_message(self, recipient: str, message: str) -> bool:
        """Send WhatsApp message using Twilio"""
        if not self.twilio_client:
            print("WhatsApp messaging not configured")
            return False
        
        try:
            message = self.twilio_client.messages.create(
                body=message,
                from_=f"whatsapp:{self.twilio_whatsapp_number}",
                to=f"whatsapp:{recipient}"
            )
            return True
        except Exception as e:
            print(f"Error sending WhatsApp message: {str(e)}")
            return False
    
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
                    
                    self.schedule_report(
                        schedule_id,
                        dataset_name,
                        schedule_config,
                        email_config,
                        format_config
                    )
                
                print(f"Loaded {len(schedules)} saved schedules")
        except Exception as e:
            print(f"Error loading saved schedules: {str(e)}")
    
    def schedule_report(self, schedule_id: str, dataset_name: str, schedule_config: dict,
                       email_config: dict, format_config: dict = None):
        """Schedule a report based on configuration"""
        try:
            schedule_type = schedule_config.get('type')
            if not schedule_type:
                raise ValueError("Schedule type not specified")
            
            # Convert schedule configuration to APScheduler trigger
            trigger = self._create_trigger(schedule_config)
            
            # Add job to scheduler
            self.scheduler.add_job(
                self.send_report,
                trigger=trigger,
                args=[dataset_name, email_config, format_config],
                id=schedule_id,
                replace_existing=True
            )
            
            print(f"Scheduled report for dataset: {dataset_name}")
            print(f"Schedule description: {self.get_schedule_description(schedule_config)}")
            
        except Exception as e:
            error_msg = f"Failed to schedule report: {str(e)}"
            print(error_msg)
            raise Exception(error_msg) from e
    
    def _create_trigger(self, schedule_config: dict) -> CronTrigger:
        """Create APScheduler trigger from schedule configuration"""
        schedule_type = schedule_config['type']
        hour = schedule_config.get('hour', 0)
        minute = schedule_config.get('minute', 0)
        timezone = pytz.timezone(schedule_config.get('timezone', 'UTC'))
        
        if schedule_type == 'one-time':
            date = schedule_config.get('date')
            if not date:
                raise ValueError("Date not specified for one-time schedule")
            return CronTrigger(
                year=date.split('-')[0],
                month=date.split('-')[1],
                day=date.split('-')[2],
                hour=hour,
                minute=minute,
                timezone=timezone
            )
        
        elif schedule_type == 'daily':
            return CronTrigger(
                hour=hour,
                minute=minute,
                timezone=timezone
            )
        
        elif schedule_type == 'weekly':
            days = schedule_config.get('days', [])
            if not days:
                raise ValueError("Days not specified for weekly schedule")
            return CronTrigger(
                day_of_week=','.join(str(day) for day in days),
                hour=hour,
                minute=minute,
                timezone=timezone
            )
        
        elif schedule_type == 'monthly':
            day_option = schedule_config.get('day_option', 'Specific Day')
            
            if day_option == 'Last Day':
                return CronTrigger(
                    day='last',
                    hour=hour,
                    minute=minute,
                    timezone=timezone
                )
            elif day_option in ['First Weekday', 'Last Weekday']:
                # These require custom logic in the job itself
                day = 1 if day_option == 'First Weekday' else 'last'
                return CronTrigger(
                    day=day,
                    hour=hour,
                    minute=minute,
                    timezone=timezone
                )
            else:
                day = schedule_config.get('day')
                if not day:
                    raise ValueError("Day not specified for monthly schedule")
                return CronTrigger(
                    day=day,
                    hour=hour,
                    minute=minute,
                    timezone=timezone
                )
        
        else:
            raise ValueError(f"Invalid schedule type: {schedule_type}") 