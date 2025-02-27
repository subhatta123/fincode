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
            page_size_value = format_config['page_size']
            if isinstance(page_size_value, str):
                # Handle string page sizes
                if page_size_value.upper() == 'A4':
                    self.page_size = A4
                elif page_size_value.upper() == 'LETTER':
                    self.page_size = letter
                else:
                    # Default to A4 for unknown string values
                    print(f"Unknown page size: {page_size_value}, using A4")
                    self.page_size = A4
            else:
                # If it's already a ReportLab page size tuple, use it directly
                self.page_size = page_size_value
        
        if format_config.get('orientation'):
            self.orientation = format_config['orientation'].lower()
        
        # Handle margins with proper type conversion
        if format_config.get('margins'):
            try:
                margins = format_config['margins']
                # Check if margins is a dictionary or a tuple
                if isinstance(margins, dict):
                    # Create a new tuple with proper numeric values
                    left = float(margins.get('left', 0.5)) * inch
                    right = float(margins.get('right', 0.5)) * inch
                    top = float(margins.get('top', 0.5)) * inch
                    bottom = float(margins.get('bottom', 0.5)) * inch
                    self.margins = (left, right, top, bottom)
                elif isinstance(margins, (list, tuple)) and len(margins) == 4:
                    # Convert all values to float * inch
                    self.margins = tuple(float(m) * inch for m in margins)
                else:
                    print(f"Invalid margins format: {margins}, using defaults")
                    self.margins = (0.5*inch, 0.5*inch, 0.5*inch, 0.5*inch)
            except (TypeError, ValueError, KeyError) as e:
                print(f"Error converting margins, using defaults: {str(e)}")
                self.margins = (0.5*inch, 0.5*inch, 0.5*inch, 0.5*inch)
        else:
            # Ensure margins is always set
            self.margins = (0.5*inch, 0.5*inch, 0.5*inch, 0.5*inch)
        
        # Title style
        if format_config.get('title_style'):
            title_style = format_config['title_style']
            try:
                self.title_style = ParagraphStyle(
                    'CustomTitle',
                    parent=self.styles['Title'],
                    fontName=str(title_style.get('fontName', 'Helvetica')),
                    fontSize=int(title_style.get('fontSize', 24)),
                    textColor=colors.HexColor(str(title_style.get('textColor', '#000000'))),
                    alignment=title_style.get('alignment', TA_CENTER),
                    spaceAfter=float(title_style.get('spaceAfter', 30))
                )
            except (TypeError, ValueError) as e:
                print(f"Error setting title style, using defaults: {str(e)}")
                self._set_default_styles()
        
        # Table style
        if format_config.get('table_style'):
            table_style = format_config['table_style']
            try:
                self.table_style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(str(table_style.get('headerColor', '#2d5d7b')))),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), int(table_style.get('fontSize', 10))),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor(str(table_style.get('rowColor', '#f5f5f5')))),
                    ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), int(table_style.get('fontSize', 10)) - 2),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor(str(table_style.get('gridColor', '#808080')))),
                    ('ROWHEIGHT', (0, 0), (-1, -1), float(table_style.get('rowHeight', 20))),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ])
            except (TypeError, ValueError) as e:
                print(f"Error setting table style, using defaults: {str(e)}")
                self._set_default_styles()
        
        # Chart size
        if format_config.get('chart_size'):
            try:
                chart_size = format_config['chart_size']
                self.chart_size = (
                    float(chart_size.get('width', 6)) * inch,
                    float(chart_size.get('height', 4)) * inch
                )
            except (TypeError, ValueError) as e:
                print(f"Error setting chart size, using defaults: {str(e)}")
                self.chart_size = (6*inch, 4*inch)
        
        # Header image
        if format_config.get('header_image'):
            self.header_image = self._resize_image(format_config['header_image'])
        
        # Footer text
        if format_config.get('footer_text'):
            self.footer_text = str(format_config['footer_text'])
    
    def generate_report(self, df: pd.DataFrame, report_title: str = "Data Report",
                       include_row_count: bool = True, include_totals: bool = True,
                       include_averages: bool = True, selected_columns: list = None) -> io.BytesIO:
        """Generate a formatted PDF report"""
        buffer = io.BytesIO()
        
        # Set up the document with guaranteed valid values
        try:
            # Ensure page_size is valid
            if isinstance(self.page_size, str):
                print(f"Converting string page size '{self.page_size}' to A4")
                page_size = A4
            else:
                page_size = self.page_size
                
            # Verify page_size is a valid tuple
            if not isinstance(page_size, tuple) or len(page_size) != 2:
                print(f"Invalid page size format: {page_size}, using A4")
                page_size = A4
                
            # Apply orientation
            if self.orientation == 'landscape':
                page_size = landscape(page_size)
                
            # Explicitly create valid margin values
            left_margin = 0.5 * inch
            right_margin = 0.5 * inch
            top_margin = 0.5 * inch
            bottom_margin = 0.5 * inch
            
            # If margins is valid, try to use those values
            if isinstance(self.margins, tuple) and len(self.margins) == 4:
                try:
                    left_margin = float(self.margins[0])
                    right_margin = float(self.margins[1])
                    top_margin = float(self.margins[2])
                    bottom_margin = float(self.margins[3])
                except (ValueError, TypeError):
                    print("Error converting margin values to float, using defaults")
            else:
                print(f"Invalid margins format: {self.margins}, using defaults")
            
            # Create document with explicit validated values
            doc = SimpleDocTemplate(
                buffer,
                pagesize=page_size,
                leftMargin=left_margin,
                rightMargin=right_margin,
                topMargin=top_margin,
                bottomMargin=bottom_margin
            )
        except Exception as e:
            print(f"Error creating document with custom settings: {str(e)}")
            print("Falling back to absolute defaults")
            # Use absolute defaults as fallback
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                leftMargin=0.5*inch,
                rightMargin=0.5*inch,
                topMargin=0.5*inch,
                bottomMargin=0.5*inch
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