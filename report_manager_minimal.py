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
        self.reports_dir = self.data_dir / "reports"
        self.reports_dir.mkdir(exist_ok=True)
        self.public_reports_dir = Path("static/reports")
        self.public_reports_dir.mkdir(parents=True, exist_ok=True)
        self.schedules_file = self.data_dir / "schedules.json"
        self.db_path = 'data/tableau_data.db'
        self._init_database()
        
        # Load settings from environment variables
        self.smtp_server = os.getenv('SMTP_SERVER')
        self.smtp_port = os.getenv('SMTP_PORT')
        self.sender_email = os.getenv('SENDER_EMAIL')
        self.sender_password = os.getenv('SENDER_PASSWORD')
        self.twilio_whatsapp_number = os.getenv('TWILIO_WHATSAPP_NUMBER')
        self.twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        
        # Initialize services
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.twilio_client = None
        
        if all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_whatsapp_number]):
            try:
                self.twilio_client = Client(self.twilio_account_sid, self.twilio_auth_token)
                print("Twilio client initialized successfully")
            except Exception as e:
                print(f"Failed to initialize Twilio client: {str(e)}")
    
    def _init_database(self):
        """Initialize SQLite database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
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
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = report_path.name
        hash_input = f"{original_name}_{timestamp}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        public_filename = f"{hash_value}_{original_name}"
        
        public_path = self.public_reports_dir / public_filename
        shutil.copy2(report_path, public_path)
        
        cleanup_time = datetime.now() + timedelta(hours=24)
        self.scheduler.add_job(
            self._cleanup_report,
            'date',
            run_date=cleanup_time,
            args=[public_path]
        )
        
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