import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import io
from datetime import datetime
import plotly.graph_objects as go
import plotly.io as pio
import base64
from PIL import Image as PILImage

class ReportFormatter:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.custom_styles = {}
        self.page_size = A4
        self.orientation = 'portrait'
        self.margins = (0.5*inch, 0.5*inch, 0.5*inch, 0.5*inch)  # left, right, top, bottom
        self.header_image = None
        self.footer_text = None
        self.title_style = None
        self.table_style = None
        self.chart_size = (6*inch, 4*inch)
        
        # Set default styles
        self._set_default_styles()
    
    def _set_default_styles(self):
        """Set default styles for the report"""
        # Default title style
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Title'],
            fontSize=24,
            textColor=colors.HexColor('#000000'),
            alignment=TA_CENTER,
            spaceAfter=30
        )
        
        # Default table style
        self.table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2d5d7b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f5f5')),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#808080')),
            ('ROWHEIGHT', (0, 0), (-1, -1), 20),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
    
    def _resize_image(self, image_data, max_width=6*inch, max_height=2*inch):
        """Resize the image to fit within the specified dimensions"""
        try:
            # Create BytesIO object from image data
            image_buffer = io.BytesIO(image_data)
            image = PILImage.open(image_buffer)
            
            # Calculate aspect ratio
            aspect_ratio = image.width / image.height
            
            # Calculate new dimensions maintaining aspect ratio
            if aspect_ratio > max_width / max_height:  # Width is the limiting factor
                new_width = max_width
                new_height = max_width / aspect_ratio
            else:  # Height is the limiting factor
                new_height = max_height
                new_width = max_height * aspect_ratio
            
            # Resize image
            image = image.resize((int(new_width), int(new_height)), PILImage.Resampling.LANCZOS)
            
            # Save to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format=image.format or 'PNG')
            img_byte_arr.seek(0)
            
            return Image(img_byte_arr, width=new_width, height=new_height)
        except Exception as e:
            print(f"Error processing image: {str(e)}")
            return None
    
    def set_format_config(self, format_config: dict):
        """Apply formatting configuration"""
        if not format_config:
            return
            
        # Page settings
        if format_config.get('page_size'):
            self.page_size = A4 if format_config['page_size'].upper() == 'A4' else letter
        
        if format_config.get('orientation'):
            self.orientation = format_config['orientation'].lower()
        
        if format_config.get('margins'):
            margins = format_config['margins']
            self.margins = (
                margins.get('left', 0.5) * inch,
                margins.get('right', 0.5) * inch,
                margins.get('top', 0.5) * inch,
                margins.get('bottom', 0.5) * inch
            )
        
        # Title style
        if format_config.get('title_style'):
            title_style = format_config['title_style']
            self.title_style = ParagraphStyle(
                'CustomTitle',
                parent=self.styles['Title'],
                fontName=title_style.get('fontName', 'Helvetica'),
                fontSize=title_style.get('fontSize', 24),
                textColor=colors.HexColor(title_style.get('textColor', '#000000')),
                alignment=title_style.get('alignment', TA_CENTER),
                spaceAfter=title_style.get('spaceAfter', 30)
            )
        
        # Table style
        if format_config.get('table_style'):
            table_style = format_config['table_style']
            self.table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(table_style.get('headerColor', '#2d5d7b'))),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), table_style.get('fontSize', 10)),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor(table_style.get('rowColor', '#f5f5f5'))),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), table_style.get('fontSize', 10) - 2),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor(table_style.get('gridColor', '#808080'))),
                ('ROWHEIGHT', (0, 0), (-1, -1), table_style.get('rowHeight', 20)),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ])
        
        # Chart size
        if format_config.get('chart_size'):
            chart_size = format_config['chart_size']
            self.chart_size = (
                chart_size.get('width', 6) * inch,
                chart_size.get('height', 4) * inch
            )
        
        # Header image
        if format_config.get('header_image'):
            self.header_image = self._resize_image(format_config['header_image'])
        
        # Footer text
        if format_config.get('footer_text'):
            self.footer_text = format_config['footer_text']
    
    def generate_report(self, df: pd.DataFrame, report_title: str = "Data Report",
                       include_row_count: bool = True, include_totals: bool = True,
                       include_averages: bool = True, selected_columns: list = None) -> io.BytesIO:
        """Generate a formatted PDF report"""
        buffer = io.BytesIO()
        
        # Set up the document
        page_size = self.page_size
        if self.orientation == 'landscape':
            page_size = landscape(page_size)
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=page_size,
            leftMargin=self.margins[0],
            rightMargin=self.margins[1],
            topMargin=self.margins[2],
            bottomMargin=self.margins[3]
        )
        
        # Start building content
        elements = []
        
        # Add header image if present
        if self.header_image:
            elements.append(self.header_image)
            elements.append(Spacer(1, 20))
        
        # Add title
        title = Paragraph(str(report_title), self.title_style)
        elements.append(title)
        
        # Add timestamp
        timestamp_style = ParagraphStyle(
            'Timestamp',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.gray,
            spaceAfter=20
        )
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elements.append(Paragraph(f"Generated on: {timestamp}", timestamp_style))
        
        # Filter columns if specified
        if selected_columns:
            df = df[selected_columns]
        
        # Add summary statistics if requested
        if any([include_row_count, include_totals, include_averages]):
            summary_data = [["Metric", "Value"]]  # Header row
            
            if include_row_count:
                summary_data.append(["Total Rows", f"{len(df):,}"])
            
            numeric_cols = df.select_dtypes(include=['number']).columns
            if include_totals:
                for col in numeric_cols:
                    total = df[col].sum()
                    summary_data.append([f"Total {col}", f"{total:,.2f}"])
            
            if include_averages:
                for col in numeric_cols:
                    avg = df[col].mean()
                    summary_data.append([f"Average {col}", f"{avg:,.2f}"])
            
            if len(summary_data) > 1:  # Only add if we have data beyond the header
                summary_table = Table(summary_data)
                summary_table.setStyle(self.table_style)
                elements.append(summary_table)
                elements.append(Spacer(1, 20))
        
        # Add main data table
        data = [df.columns.tolist()]  # Header row
        
        # Format numeric values
        formatted_df = df.copy()
        for col in df.select_dtypes(include=['number']).columns:
            formatted_df[col] = formatted_df[col].apply(lambda x: f"{x:,.2f}")
        
        data.extend(formatted_df.values.tolist())
        
        # Calculate column widths
        col_widths = []
        for col_idx in range(len(df.columns)):
            col_content = [str(row[col_idx]) for row in data]
            max_content_len = max(len(str(content)) for content in col_content)
            col_widths.append(min(max_content_len * 7, 200))  # Scale factor of 7, max width 200
        
        main_table = Table(data, colWidths=col_widths)
        main_table.setStyle(self.table_style)
        elements.append(main_table)
        
        # Add footer
        if self.footer_text:
            elements.append(Spacer(1, 20))
            footer_style = ParagraphStyle(
                'Footer',
                parent=self.styles['Normal'],
                fontSize=8,
                textColor=colors.gray,
                alignment=TA_CENTER
            )
            elements.append(Paragraph(self.footer_text, footer_style))
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        return buffer

    def generate_email_content(self, report_title="Data Report", include_header=True):
        """Generate email content with proper formatting"""
        email_content = {
            'subject': f"Report: {report_title}",
            'body': f"""
Dear User,

Your report "{report_title}" has been generated and is attached to this email.

Report Details:
- Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- Title: {report_title}

Please find the report attached to this email.

Best regards,
Tableau Data Reporter
            """.strip(),
            'include_header': include_header
        }
        return email_content 