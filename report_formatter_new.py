import pandas as pd
from reportlab.lib import colors, enums
from reportlab.lib.pagesizes import (
    letter, A4, A3, A5, B4, B5, LEGAL, TABLOID,
    landscape
)
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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
import matplotlib.pyplot as plt
from io import BytesIO

# Define page size mapping
PAGE_SIZES = {
    'A4': A4,
    'A3': A3,
    'A5': A5,
    'B4': B4,
    'B5': B5,
    'LETTER': letter,
    'LEGAL': LEGAL,
    'TABLOID': TABLOID
}

# Define alignment mapping
ALIGNMENTS = {
    'LEFT': TA_LEFT,
    'CENTER': TA_CENTER,
    'RIGHT': TA_RIGHT
}

class ReportFormatter:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.custom_styles = {}
        self.page_size = 'A4'  # Changed to uppercase
        self.orientation = 'portrait'
        self.margins = (72, 72, 72, 72)  # 1 inch margins (72 points)
        
        # Font settings - using built-in fonts
        self.font_family = 'Helvetica'  # Built-in font
        self.font_size = 12
        self.line_height = 1.5
        
        # Header settings
        self.include_header = True
        self.header_title = None
        self.header_logo = None
        self.header_color = colors.HexColor('#0d6efd')  # Bootstrap primary blue
        self.header_alignment = 'center'
        
        # Content settings
        self.include_summary = True
        self.include_visualization = True
        self.max_rows = 1000
        
        # Set default styles
        self._set_default_styles()
    
    def _set_default_styles(self):
        """Set default styles for the report"""
        # Default title style
        self.title_style = ParagraphStyle(
            'CustomTitle',
            parent=self.styles['Title'],
            fontName='Helvetica',  # Built-in font
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
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Built-in font
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f5f5')),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),  # Built-in font
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#808080')),
            ('ROWHEIGHT', (0, 0), (-1, -1), 20),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ])
    
    
    def _normalize_path(self, path):
        """Normalize paths to handle both forward and backslashes"""
        if not path:
            return path
        return path.replace('\\', '/').replace('\\', '/')

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
        """Set formatting configuration for the report"""
        if not format_config or not isinstance(format_config, dict):
            print("Warning: Invalid format_config provided")
            return
            
        print(f"Setting format config: {format_config}")
        
        # Helper function to safely get values handling tuples
        def safe_get(config, key, default=None):
            value = config.get(key, default)
            if isinstance(value, tuple) and len(value) > 0:
                return value[0]
            return value
            
        # Helper function to extract primary font name from CSS font-family
        def extract_primary_font(font_family):
            if not font_family:
                return 'Helvetica'
            # Get the first font name from CSS-style font-family (e.g., "Georgia, serif")
            primary_font = str(font_family).split(',')[0].strip()
            # Remove quotes if present
            if primary_font.startswith('"') and primary_font.endswith('"'):
                primary_font = primary_font[1:-1]
            if primary_font.startswith("'") and primary_font.endswith("'"):
                primary_font = primary_font[1:-1]
            # Map common web fonts to PDF-supported fonts
            font_map = {
                'arial': 'Helvetica',
                'helvetica': 'Helvetica',
                'verdana': 'Helvetica',
                'tahoma': 'Helvetica',
                'times': 'Times-Roman',
                'times new roman': 'Times-Roman',
                'georgia': 'Times-Roman',
                'serif': 'Times-Roman',
                'sans-serif': 'Helvetica',
                'courier': 'Courier',
                'courier new': 'Courier',
                'monospace': 'Courier'
            }
            # Convert to lowercase for case-insensitive lookup
            lowercase_font = primary_font.lower()
            # Return the mapped font or default to Helvetica
            return font_map.get(lowercase_font, 'Helvetica')
        
        # Page settings
        if 'page_size' in format_config:
            self.page_size = str(safe_get(format_config, 'page_size', 'A4'))
            
        if 'orientation' in format_config:
            self.orientation = str(safe_get(format_config, 'orientation', 'portrait'))
            
        if 'margins' in format_config:
            margins = format_config['margins']
            if isinstance(margins, (list, tuple)) and len(margins) == 4:
                self.margins = margins
                
        # Font settings
        if 'font_family' in format_config:
            font_family = safe_get(format_config, 'font_family', 'Helvetica')
            self.font_family = extract_primary_font(font_family)
            print(f"Using font: {self.font_family}")
            
        if 'font_size' in format_config:
            try:
                font_size = safe_get(format_config, 'font_size', 12)
                self.font_size = int(font_size)
            except (ValueError, TypeError):
                print(f"Warning: Invalid font size: {format_config.get('font_size')}")
                
        if 'line_height' in format_config:
            try:
                line_height = safe_get(format_config, 'line_height', 1.2)
                self.line_height = float(line_height)
            except (ValueError, TypeError):
                print(f"Warning: Invalid line height: {format_config.get('line_height')}")
                
        # Header settings
        if 'include_header' in format_config:
            include_header = safe_get(format_config, 'include_header', True)
            self.include_header = bool(include_header)
            
        if 'header_logo' in format_config:
            self.header_logo = str(safe_get(format_config, 'header_logo', ''))
            
        if 'header_title' in format_config:
            self.header_title = str(safe_get(format_config, 'header_title', ''))
            
        if 'header_color' in format_config:
            header_color = safe_get(format_config, 'header_color')
            if isinstance(header_color, str):
                try:
                    self.header_color = colors.HexColor(header_color)
                except:
                    print(f"Warning: Invalid header color: {header_color}")
            elif header_color is not None:
                self.header_color = header_color
                
        if 'header_alignment' in format_config:
            alignment = str(safe_get(format_config, 'header_alignment', 'center')).upper()
            self.header_alignment = ALIGNMENTS.get(alignment, TA_CENTER)
        
        # Content settings
        if 'include_summary' in format_config:
            include_summary = safe_get(format_config, 'include_summary', True)
            self.include_summary = bool(include_summary)
            
        if 'include_visualization' in format_config:
            include_viz = safe_get(format_config, 'include_visualization', False)
            self.include_visualization = bool(include_viz)
            
        if 'max_rows' in format_config:
            try:
                max_rows = safe_get(format_config, 'max_rows', 100)
                self.max_rows = int(max_rows)
            except (ValueError, TypeError):
                print(f"Warning: Invalid max rows: {format_config.get('max_rows')}")
        
        # Column selection
        if 'selected_columns' in format_config:
            selected_cols = format_config.get('selected_columns')
            if isinstance(selected_cols, (list, tuple)) and selected_cols:
                self.selected_columns = list(selected_cols)
            else:
                self.selected_columns = None
        else:
            self.selected_columns = None
    
    def generate_report(self, df: pd.DataFrame, report_title: str = "Data Report",
                       include_row_count: bool = True, include_totals: bool = True,
                       include_averages: bool = True, selected_columns: list = None) -> io.BytesIO:
        """Generate a PDF report from the given DataFrame"""
        buffer = io.BytesIO()
        
        # Filter columns if selected_columns is provided in the method or from format_config
        if selected_columns:
            # Use columns provided directly to the method
            available_columns = [col for col in selected_columns if col in df.columns]
            if available_columns:
                df = df[available_columns]
        elif hasattr(self, 'selected_columns') and self.selected_columns:
            # Use columns from format_config
            available_columns = [col for col in self.selected_columns if col in df.columns]
            if available_columns:
                df = df[available_columns]
        
        # Convert any tuple values to strings before calling upper()
        page_size_value = self.page_size
        if isinstance(page_size_value, tuple) and len(page_size_value) > 0:
            page_size_value = str(page_size_value[0])
        else:
            page_size_value = str(page_size_value)
            
        # Use page size and orientation from format config
        page_size = PAGE_SIZES.get(page_size_value.upper(), letter)
        
        orientation_value = self.orientation
        if isinstance(orientation_value, tuple) and len(orientation_value) > 0:
            orientation_value = str(orientation_value[0])
        else:
            orientation_value = str(orientation_value)
            
        if orientation_value.lower() == 'landscape':
            page_size = landscape(page_size)
        
        # Apply margins
        doc = SimpleDocTemplate(
            buffer,
            pagesize=page_size,
            rightMargin=self.margins[0],
            leftMargin=self.margins[1],
            topMargin=self.margins[2],
            bottomMargin=self.margins[3]
        )
        
        elements = []
        styles = getSampleStyleSheet()
        
        # Handle header alignment as possible tuple
        header_alignment = self.header_alignment
        if isinstance(header_alignment, tuple) and len(header_alignment) > 0:
            header_alignment = str(header_alignment[0])
        else:
            header_alignment = str(header_alignment)
        
        # Create a custom title style using the header color
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            textColor=self.header_color,
            alignment=ALIGNMENTS.get(header_alignment.upper(), TA_CENTER),
            fontSize=self.font_size + 8
        )
        
        # Add logo if provided
        if self.header_logo:
            try:
                # Handle both relative and absolute paths
                logo_path = self._normalize_path(self.header_logo)
                if not os.path.isabs(logo_path):
                    # If it's a relative path, try several common locations
                    possible_paths = []
                    
                    # Simplified approach - just use the path as is
                    # If the path is a relative path without 'static/' prefix, add it
                    if not logo_path.startswith('static/'):
                        possible_paths.append(os.path.join('static', logo_path).replace('\\', '/'))
                    else:
                        possible_paths.append(logo_path)
                    
                    # Remove any None values from the list
                    possible_paths = [p for p in possible_paths if p]
                    
                    for path in possible_paths:
                        if os.path.exists(path):
                            logo_path = path
                            break
                    else:
                        print(f"Warning: Logo file not found in any of the expected locations: {possible_paths}")
                
                if os.path.exists(logo_path):
                    try:
                        # Use PIL to check and resize the image if needed
                        from reportlab.lib.units import inch
                        
                        # Open the image and get dimensions
                        pil_img = PILImage.open(logo_path)
                        img_width, img_height = pil_img.size
                        
                        # Set maximum dimensions for the header logo
                        max_width = 2 * inch
                        max_height = 1 * inch
                        
                        # Calculate aspect ratio
                        aspect = img_width / float(img_height)
                        
                        # Determine new size while maintaining aspect ratio
                        if img_width > max_width or img_height > max_height:
                            if aspect > 1:  # Width > Height
                                new_width = min(img_width, max_width)
                                new_height = new_width / aspect
                            else:  # Height >= Width
                                new_height = min(img_height, max_height)
                                new_width = new_height * aspect
                                
                            print(f"Resizing logo from {img_width}x{img_height} to {new_width:.1f}x{new_height:.1f}")
                            
                            # Process for ReportLab
                            img = Image(logo_path)
                            img.drawHeight = new_height
                            img.drawWidth = new_width
                        else:
                            # Image is already small enough
                            img = Image(logo_path)
                            img.drawHeight = img_height
                            img.drawWidth = img_width
                        
                        elements.append(img)
                        elements.append(Spacer(1, 10))
                    except Exception as e:
                        print(f"Error processing logo image: {str(e)}")
                        print(f"Logo path: {logo_path}")
                else:
                    print(f"Warning: Logo file not found: {logo_path}")
            except Exception as e:
                print(f"Error adding header logo: {str(e)}")
        
        # Add title - use header_title if set, otherwise use report_title
        title_text = str(self.header_title or report_title)
        print(f"Adding title: {title_text}")
        
        try:
            title_paragraph = Paragraph(title_text, title_style)
            elements.append(title_paragraph)
            elements.append(Spacer(1, 12))
        except Exception as e:
            print(f"Error adding title: {str(e)}")
            # Add a simple title as fallback
            elements.append(Paragraph(title_text, styles['Title']))
        
        # Convert all values to strings, properly handling tuples
        # Handle column names (headers)
        string_columns = []
        for col in df.columns:
            if isinstance(col, tuple):
                string_columns.append(str(col[0]))  # Take first element if tuple
            else:
                string_columns.append(str(col))
        
        # Create new DataFrame with string columns
        string_df = pd.DataFrame(columns=string_columns)
        
        # Copy data, converting to strings
        for i, row in df.iterrows():
            new_row = []
            for val in row:
                if isinstance(val, tuple):
                    new_row.append(str(val[0]))  # Take first element if tuple
                else:
                    new_row.append(str(val))
            string_df.loc[i] = new_row
        
        # Replace original DataFrame with string version
        df = string_df
        
        # Add summary information
        if any([include_row_count, include_totals, include_averages]):
            summary_text = "<b>Summary:</b><br/>"
            if include_row_count:
                summary_text += f"Total Records: {len(df)}<br/>"
            
            if include_totals:
                try:
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    if not numeric_cols.empty:
                        total_row = df[numeric_cols].sum()
                        summary_text += "<b>Column Totals:</b><br/>"
                    for col in numeric_cols:
                        total_val = total_row[col]
                        summary_text += f"- {col}: {total_val:,.2f}<br/>"
                except Exception as e:
                    print(f"Warning: Could not calculate totals: {str(e)}")
            
            if include_averages:
                try:
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    if not numeric_cols.empty:
                        avg_row = df[numeric_cols].mean()
                        summary_text += "<b>Column Averages:</b><br/>"
                    for col in numeric_cols:
                        avg_val = avg_row[col]
                        summary_text += f"- {col}: {avg_val:,.2f}<br/>"
                except Exception as e:
                    print(f"Warning: Could not calculate averages: {str(e)}")
            
            elements.append(Paragraph(summary_text, styles['BodyText']))
            elements.append(Spacer(1, 12))
        
        # Create table
        try:
            if len(df) > self.max_rows:
                df = df.head(self.max_rows)
            
            # Convert DataFrame to table data, handling tuples
            table_data = []
            
            # Add headers
            table_data.append(df.columns.tolist())
            
            # Add rows
            for _, row in df.iterrows():
                table_data.append(row.tolist())
            
            # Calculate column widths based on content
            col_widths = []
            for col_idx in range(len(df.columns)):
                col_content = [str(row[col_idx]) for row in table_data]
                max_content_len = max(len(str(content)) for content in col_content)
                col_widths.append(min(max_content_len * 7, 200))  # Scale factor of 7, max width 200
            
            # Create table
            table = Table(table_data, colWidths=col_widths)
            
            # Add style to table using the header color
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.header_color),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), self.font_size + 2),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),  # Use safe default font
                ('FONTSIZE', (0, 1), (-1, -1), self.font_size),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, colors.darkgrey)
            ])
            table.setStyle(style)
            
            elements.append(table)
            
        except Exception as e:
            elements.append(Paragraph(f"Error generating table: {str(e)}", styles['BodyText']))
            print(f"Error generating table: {str(e)}")
        
        try:
            doc.build(elements)
            buffer.seek(0)
            return buffer
        except Exception as e:
            print(f"Error building PDF: {str(e)}")
            raise

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