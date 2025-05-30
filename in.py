import streamlit as st
import pandas as pd
import os
import re
import datetime
from io import BytesIO
import tempfile
import requests
from PIL import Image as PILImage, ImageDraw, ImageFont
import base64

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, PageBreak, Image
from reportlab.lib.units import cm, inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# Define sticker dimensions
STICKER_WIDTH = 10 * cm
STICKER_HEIGHT = 15 * cm
STICKER_PAGESIZE = (STICKER_WIDTH, STICKER_HEIGHT)

# Define content box dimensions
CONTENT_BOX_WIDTH = 10 * cm
CONTENT_BOX_HEIGHT = 5 * cm

def normalize_column_name(col_name):
    """Normalize column names by removing all non-alphanumeric characters and converting to lowercase"""
    return re.sub(r'[^a-zA-Z0-9]', '', str(col_name)).lower()

def find_column(df, possible_names):
    """Find a column in the DataFrame that matches any of the possible names"""
    normalized_df_columns = {normalize_column_name(col): col for col in df.columns}
    normalized_possible_names = [normalize_column_name(name) for name in possible_names]

    for norm_name in normalized_possible_names:
        if norm_name in normalized_df_columns:
            return normalized_df_columns[norm_name]

    # Check for partial matches
    for norm_name in normalized_possible_names:
        for df_norm_name, original_name in normalized_df_columns.items():
            if norm_name in df_norm_name or df_norm_name in norm_name:
                return original_name

    # Check for line location keywords
    for df_norm_name, original_name in normalized_df_columns.items():
        if ('line' in df_norm_name and 'location' in df_norm_name) or 'lineloc' in df_norm_name:
            return original_name

    return None

def create_first_box_logo_from_upload(uploaded_logo):
    """Create first box logo from uploaded file"""
    try:
        # Load image from uploaded file
        logo_img = PILImage.open(uploaded_logo)
        
        # Convert to RGB if necessary
        if logo_img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = PILImage.new('RGB', logo_img.size, (255, 255, 255))
            if logo_img.mode == 'P':
                logo_img = logo_img.convert('RGBA')
            background.paste(logo_img, mask=logo_img.split()[-1] if logo_img.mode in ('RGBA', 'LA') else None)
            logo_img = background
        
        # Calculate the first box dimensions to fit properly
        content_width = CONTENT_BOX_WIDTH - 0.2*cm  # 9.8cm
        box_width_cm = content_width * 0.15  # 15% of content width
        box_height_cm = 0.7*cm  # ASSLY_row_height
        
        # Resize logo to fit the first box perfectly
        # Convert cm to pixels for resizing (using 300 DPI)
        dpi = 300
        box_width_px = int(box_width_cm * dpi / 2.54)
        box_height_px = int(box_height_cm * dpi / 2.54)
        
        # Resize with proper aspect ratio handling
        logo_img = logo_img.resize((box_width_px, box_height_px), PILImage.Resampling.LANCZOS)
        
        # Convert to bytes for ReportLab
        img_buffer = BytesIO()
        logo_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Return with exact dimensions for the first box (90% for padding)
        final_width = box_width_cm * 0.9
        final_height = box_height_cm * 0.9
        
        return Image(img_buffer, width=final_width, height=final_height)
        
    except Exception as e:
        st.error(f"Error processing uploaded first box logo: {e}")
        return None

def create_custom_first_box_logo():
    """Create a custom logo programmatically for the first box of sticker labels (FALLBACK ONLY)"""
    try:
        # Calculate the actual first box dimensions
        content_width = CONTENT_BOX_WIDTH - 0.2*cm  # 9.8cm
        box_width_cm = content_width * 0.15 / cm  # Convert to cm value
        box_height_cm = 0.7  # ASSLY_row_height
        
        # Convert to pixels for creating image (using 300 DPI for better quality)
        dpi = 300
        box_width_px = int(box_width_cm * dpi / 2.54)  # cm to pixels
        box_height_px = int(box_height_cm * dpi / 2.54)  # cm to pixels
        
        # Create image with white background
        img = PILImage.new('RGB', (box_width_px, box_height_px), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        # Design 1: Simple geometric logo with company initials
        # Draw a blue rectangle as background
        draw.rectangle([5, 5, box_width_px-5, box_height_px-5], fill=(41, 128, 185), outline=(52, 73, 94), width=2)
        
        # Try to use a font, fallback to default if not available
        try:
            # Try to load a font
            font_size = min(box_width_px // 4, box_height_px // 2)
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            # Fallback to default font
            font = ImageFont.load_default()
        
        # Add company initials or text
        text = "LOGO"  # You can change this to your company initials
        
        # Get text size and center it
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except:
            # Fallback for older PIL versions
            text_width, text_height = draw.textsize(text, font=font)
        
        x = (box_width_px - text_width) // 2
        y = (box_height_px - text_height) // 2
        
        # Draw white text
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        
        # Add some decorative elements
        # Small corner triangles
        draw.polygon([(0, 0), (15, 0), (0, 15)], fill=(231, 76, 60))  # Top-left red triangle
        draw.polygon([(box_width_px, 0), (box_width_px-15, 0), (box_width_px, 15)], fill=(46, 204, 113))  # Top-right green triangle
        
        # Convert to bytes for ReportLab
        img_buffer = BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Return with exact dimensions to fit the first box
        final_width = box_width_cm * 0.9  # 90% of box width for padding
        final_height = box_height_cm * 0.9  # 90% of box height for padding
        
        return Image(img_buffer, width=final_width*cm, height=final_height*cm)
        
    except Exception as e:
        st.error(f"Error creating custom first box logo: {e}")
        return None

def create_instor_logo_from_url():
    """Create Instor logo from the specified URL"""
    try:
        logo_url = "https://th.bing.com/th/id/OIP.94bEOtZbX8bq0cidAShqJwAAAA?rs=1&pid=ImgDetMain"
        
        # Download the image
        response = requests.get(logo_url, timeout=10)
        response.raise_for_status()
        
        # Load image from response content
        logo_img = PILImage.open(BytesIO(response.content))
        
        # Convert to RGB if necessary
        if logo_img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = PILImage.new('RGB', logo_img.size, (255, 255, 255))
            if logo_img.mode == 'P':
                logo_img = logo_img.convert('RGBA')
            background.paste(logo_img, mask=logo_img.split()[-1] if logo_img.mode in ('RGBA', 'LA') else None)
            logo_img = background
        
        # Resize logo to appropriate size for label
        logo_img = logo_img.resize((120, 40), PILImage.Resampling.LANCZOS)
        
        # Convert to bytes for ReportLab
        img_buffer = BytesIO()
        logo_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        return Image(img_buffer, width=2*cm, height=0.8*cm)
        
    except Exception as e:
        st.warning(f"Error loading logo from URL: {e}")
        # Fallback to embedded logo
        return create_instor_logo_embedded()

def create_instor_logo_embedded():
    """Create Instor logo using embedded base64 data (fallback)"""
    try:
        # Create a simple text logo as fallback
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import blue, orange
        
        img_buffer = BytesIO()
        
        # Create a temporary canvas to draw the logo
        logo_canvas = canvas.Canvas(img_buffer, pagesize=(120, 40))
        logo_canvas.setFillColor(blue)
        logo_canvas.setFont("Helvetica-Bold", 12)
        logo_canvas.drawString(5, 20, "instor")
        logo_canvas.setFillColor(orange)
        logo_canvas.rect(0, 0, 20, 5, fill=1)
        logo_canvas.rect(0, 35, 20, 5, fill=1)
        logo_canvas.save()
        
        img_buffer.seek(0)
        return Image(img_buffer, width=2*cm, height=0.8*cm)
        
    except Exception as e:
        st.warning(f"Error creating embedded logo: {e}")
        return None

def create_instor_logo_from_upload(uploaded_logo):
    """Create Instor logo image for PDF from uploaded file"""
    try:
        # Load image from uploaded file
        logo_img = PILImage.open(uploaded_logo)
        
        # Convert to RGB if necessary
        if logo_img.mode in ('RGBA', 'LA', 'P'):
            # Create white background
            background = PILImage.new('RGB', logo_img.size, (255, 255, 255))
            if logo_img.mode == 'P':
                logo_img = logo_img.convert('RGBA')
            background.paste(logo_img, mask=logo_img.split()[-1] if logo_img.mode in ('RGBA', 'LA') else None)
            logo_img = background
        
        # Resize logo to appropriate size for label
        logo_img = logo_img.resize((120, 40), PILImage.Resampling.LANCZOS)
        
        # Convert to bytes for ReportLab
        img_buffer = BytesIO()
        logo_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        return Image(img_buffer, width=2*cm, height=0.8*cm)
    except Exception as e:
        st.error(f"Error processing uploaded logo: {e}")
        return None

def generate_qr_code(data_string):
    """Generate a QR code from the given data string"""
    try:
        import qrcode
        from PIL import Image as PILImage

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )

        qr.add_data(data_string)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")

        img_buffer = BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)

        return Image(img_buffer, width=1.8*cm, height=1.8*cm)
    except Exception as e:
        st.error(f"Error generating QR code: {e}")
        return None

def parse_line_location(location_string):
    """Parse line location string and split into 4 boxes"""
    if not location_string or pd.isna(location_string):
        return ["", "", "", ""]

    parts = str(location_string).split("_")
    result = parts[:4] + [""] * (4 - len(parts))
    return result[:4]

def generate_sticker_labels(df, line_loc_header_width, line_loc_box1_width, 
                          line_loc_box2_width, line_loc_box3_width, line_loc_box4_width, 
                          uploaded_first_box_logo=None, uploaded_instor_logo=None):
    """Generate sticker labels with QR code and logos from DataFrame"""
    try:
        # Define column mappings
        column_mappings = {
            'ASSLY': ['assly', 'ASSY NAME', 'Assy Name', 'assy name', 'assyname',
                     'assy_name', 'Assy_name', 'Assembly', 'Assembly Name', 'ASSEMBLY', 'Assembly_Name'],
            'part_no': ['PARTNO', 'PARTNO.', 'Part No', 'Part Number', 'PartNo',
                       'partnumber', 'part no', 'partnum', 'PART', 'part', 'Product Code',
                       'Item Number', 'Item ID', 'Item No', 'item', 'Item'],
            'description': ['DESCRIPTION', 'Description', 'Desc', 'Part Description',
                           'ItemDescription', 'item description', 'Product Description',
                           'Item Description', 'NAME', 'Item Name', 'Product Name'],
            'Part_per_veh': ['QYT', 'QTY / VEH', 'Qty/Veh', 'Qty Bin', 'Quantity per Bin',
                            'qty bin', 'qtybin', 'quantity bin', 'BIN QTY', 'BINQTY',
                            'QTY_BIN', 'QTY_PER_BIN', 'Bin Quantity', 'BIN'],
            'Type': ['TYPE', 'type', 'Type', 'tyPe', 'Type name'],
            'line_location': ['LINE LOCATION', 'Line Location', 'line location', 'LINELOCATION',
                             'linelocation', 'Line_Location', 'line_location', 'LINE_LOCATION',
                             'LineLocation', 'line_loc', 'lineloc', 'LINELOC', 'Line Loc']
        }

        # Find columns
        found_columns = {}
        for key, possible_names in column_mappings.items():
            found_col = find_column(df, possible_names)
            if found_col:
                found_columns[key] = found_col

        # Check required columns
        required_columns = ['ASSLY', 'part_no', 'description']
        missing_required = [col for col in required_columns if col not in found_columns]

        if missing_required:
            st.error(f"Missing required columns: {missing_required}")
            return None, None

        # Create a temporary file for PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            output_pdf_path = tmp_file.name

        # Create PDF
        def draw_border(canvas, doc):
            canvas.saveState()
            x_offset = (STICKER_WIDTH - CONTENT_BOX_WIDTH) / 3
            y_offset = STICKER_HEIGHT - CONTENT_BOX_HEIGHT - 0.2*cm
            canvas.setStrokeColor(colors.black)
            canvas.setLineWidth(1.5)
            canvas.rect(
                x_offset + doc.leftMargin,
                y_offset,
                CONTENT_BOX_WIDTH - 0.2*cm,
                CONTENT_BOX_HEIGHT
            )
            canvas.restoreState()

        doc = SimpleDocTemplate(output_pdf_path, pagesize=STICKER_PAGESIZE,
                              topMargin=0.2*cm,
                              bottomMargin=(STICKER_HEIGHT - CONTENT_BOX_HEIGHT - 0.2*cm),
                              leftMargin=0.1*cm, rightMargin=0.1*cm)

        # Define styles
        header_style = ParagraphStyle(name='HEADER', fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER, leading=10)
        ASSLY_style = ParagraphStyle(name='ASSLY', fontName='Helvetica', fontSize=10, alignment=TA_LEFT, leading=16, spaceAfter=0, wordWrap='CJK', autoLeading="max")
        Part_style = ParagraphStyle(name='PART NO', fontName='Helvetica-Bold', fontSize=12, alignment=TA_LEFT, leading=46, spaceAfter=0, wordWrap='CJK', autoLeading="max")
        desc_style = ParagraphStyle(name='PART DESC', fontName='Helvetica', fontSize=8, alignment=TA_LEFT, leading=16, spaceAfter=0, wordWrap='CJK', autoLeading="max")
        partper_style = ParagraphStyle(name='Quantity', fontName='Helvetica', fontSize=10, alignment=TA_LEFT, leading=12)
        Type_style = ParagraphStyle(name='Quantity', fontName='Helvetica', fontSize=11, alignment=TA_LEFT, leading=12)
        date_style = ParagraphStyle(name='DATE', fontName='Helvetica', fontSize=10, alignment=TA_LEFT, leading=12)
        location_style = ParagraphStyle(name='Location', fontName='Helvetica', fontSize=9, alignment=TA_CENTER, leading=10)

        content_width = CONTENT_BOX_WIDTH - 0.2*cm
        all_elements = []
        today_date = datetime.datetime.now().strftime("%d-%m-%Y")

        # Handle first box logo (prioritize uploaded, then fallback to programmatic)
        first_box_logo = None
        if uploaded_first_box_logo is not None:
            first_box_logo = create_first_box_logo_from_upload(uploaded_first_box_logo)
            if first_box_logo:
                st.success("✅ Using your uploaded logo for first box")
            else:
                st.error("❌ Failed to process uploaded first box logo")
        
        if first_box_logo is None:
            first_box_logo = create_custom_first_box_logo()
            if first_box_logo:
                st.info("🔧 Using programmatically created logo for first box (no logo uploaded)")
            else:
                st.warning("⚠️ Could not create logo for first box")

        # Handle Instor logo (prioritize uploaded, then URL, then embedded)
        instor_logo = None
        if uploaded_instor_logo is not None:
            instor_logo = create_instor_logo_from_upload(uploaded_instor_logo)
            if instor_logo:
                st.success("✅ Using your uploaded Instor logo for second box")
        
        if instor_logo is None:
            instor_logo = create_instor_logo_from_url()
            if instor_logo:
                st.info("🌐 Using Instor logo from URL for second box")

        # Process each row
        total_rows = len(df)
        progress_bar = st.progress(0)
        
        for index, row in df.iterrows():
            progress_bar.progress((index + 1) / total_rows)
            
            elements = []

            # Extract data
            ASSLY = str(row[found_columns.get('ASSLY', '')]) if 'ASSLY' in found_columns else "N/A"
            part_no = str(row[found_columns.get('part_no', '')]) if 'part_no' in found_columns else "N/A"
            desc = str(row[found_columns.get('description', '')]) if 'description' in found_columns else "N/A"
            Part_per_veh = str(row[found_columns.get('Part_per_veh', '')]) if 'Part_per_veh' in found_columns and pd.notna(row[found_columns['Part_per_veh']]) else ""
            Type = str(row[found_columns.get('Type', '')]) if 'Type' in found_columns and pd.notna(row[found_columns['Type']]) else ""
            line_location_raw = str(row[found_columns.get('line_location', '')]) if 'line_location' in found_columns and pd.notna(row[found_columns['line_location']]) else ""
            location_boxes = parse_line_location(line_location_raw)

            # Generate QR code
            qr_data = f"ASSLY: {ASSLY}\nPart No: {part_no}\nDescription: {desc}\n"
            if Part_per_veh:
                qr_data += f"QTY/BIN: {Part_per_veh}\n"
            if Type:
                qr_data += f"Type: {Type}\n"
            if line_location_raw:
                qr_data += f"Line Location: {line_location_raw}\n"
            qr_data += f"Date: {today_date}"

            qr_image = generate_qr_code(qr_data)
            if qr_image:
                qr_cell = qr_image
            else:
                qr_cell = Paragraph("QR", ParagraphStyle(name='QRPlaceholder', fontName='Helvetica-Bold', fontSize=12, alignment=TA_CENTER))

            # Define row heights
            ASSLY_row_height = 0.7*cm
            part_row_height = 0.7*cm
            desc_row_height = 0.7*cm
            bottom_row_height = 0.6*cm
            location_row_height = 0.6*cm

            # Process line location boxes
            location_box_1 = Paragraph(location_boxes[0], location_style) if location_boxes[0] else ""
            location_box_2 = Paragraph(location_boxes[1], location_style) if location_boxes[1] else ""
            location_box_3 = Paragraph(location_boxes[2], location_style) if location_boxes[2] else ""
            location_box_4 = Paragraph(location_boxes[3], location_style) if location_boxes[3] else ""

            # Create ASSLY row with 4 boxes: First Box Logo, Instor Logo, "ASSLY", Value
            first_box_content = first_box_logo if first_box_logo else ""  # Your uploaded/created logo
            second_box_content = instor_logo if instor_logo else ""       # Instor logo
            
            # Create table data with modified ASSLY row structure (4 columns)
            unified_table_data = [
                [first_box_content, second_box_content, "ASSLY", ASSLY],  # Modified: 4 columns for ASSLY row
                ["PART NO", part_no],                                     # 2 columns for other rows
                ["PART DESC", desc],
                ["PART PER VEH", Paragraph(str(Part_per_veh), partper_style), qr_cell],
                ["TYPE", Paragraph(str(Type), Type_style), ""],
                ["DATE", Paragraph(today_date, date_style), ""],
                ["LINE LOCATION", location_box_1, location_box_2, location_box_3, location_box_4]
            ]

            # Adjusted column widths for ASSLY row - 4 columns
            col_widths_assly = [content_width*0.15, content_width*0.2, content_width*0.2, content_width*0.45]  # First Logo, Instor Logo, Header, Value
            col_widths_top = [content_width*0.3, content_width*0.7]                        # Regular 2-column rows
            col_widths_middle = [content_width*0.3, content_width*0.3, content_width*0.4]   # 3-column with QR
            col_widths_bottom = [
                content_width * line_loc_header_width,
                content_width * line_loc_box1_width,
                content_width * line_loc_box2_width,
                content_width * line_loc_box3_width,
                content_width * line_loc_box4_width
            ]

            row_heights = [ASSLY_row_height, part_row_height, desc_row_height, bottom_row_height, bottom_row_height, bottom_row_height, location_row_height]

            # Create separate tables for different structures
            assly_table = Table([unified_table_data[0]], colWidths=col_widths_assly, rowHeights=[row_heights[0]])
            top_table = Table(unified_table_data[1:3], colWidths=col_widths_top, rowHeights=row_heights[1:3])
            middle_table = Table(unified_table_data[3:6], colWidths=col_widths_middle, rowHeights=row_heights[3:6])
            bottom_table = Table([unified_table_data[6]], colWidths=col_widths_bottom, rowHeights=[row_heights[6]])

            # Apply styles
            assly_style = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),  # ASSLY header bold
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),  # First box logo centered
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),  # Instor logo centered
                ('ALIGN', (2, 0), (2, 0), 'CENTER'),  # Header centered
                ('ALIGN', (3, 0), (3, 0), 'LEFT'),    # Value left aligned
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]

            top_style = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 1), (1, 1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (0, -1), 11),
                ('FONTSIZE', (1, 0), (-1, 0), 10),
                ('FONTSIZE', (1, 1), (-1, 1), 11),
                ('FONTSIZE', (1, 2), (1, 2), 8),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]

            middle_style = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (0, 0), 9),
                ('FONTSIZE', (0, 1), (0, 2), 11),
                ('FONTSIZE', (1, 0), (-1, -1), 11),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('SPAN', (2, 0), (2, 2)),
            ]

            bottom_style = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1),  9),
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                ('ALIGN', (1, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]

            # Apply table styles
            assly_table.setStyle(TableStyle(assly_style))
            top_table.setStyle(TableStyle(top_style))
            middle_table.setStyle(TableStyle(middle_style))
            bottom_table.setStyle(TableStyle(bottom_style))

            # Add tables to elements
            elements.extend([assly_table, top_table, middle_table, bottom_table])
            
            # Add page break after each sticker except the last one
            if index < len(df) - 1:
                elements.append(PageBreak())

            all_elements.extend(elements)

        # Build PDF
        doc.build(all_elements, onFirstPage=draw_border, onLaterPages=draw_border)
        
        progress_bar.empty()
        st.success(f"✅ Successfully generated {total_rows} sticker labels!")

        # Read the generated PDF
        with open(output_pdf_path, 'rb') as pdf_file:
            pdf_data = pdf_file.read()

        # Clean up temporary file
        os.unlink(output_pdf_path)

        return pdf_data, f"sticker_labels_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    except Exception as e:
        st.error(f"Error generating sticker labels: {str(e)}")
        return None, None

def main():
    """Main Streamlit application"""
    st.set_page_config(page_title="Sticker Label Generator", layout="wide")
    
    st.title("🏷️ Sticker Label Generator")
    st.markdown("Generate professional sticker labels with QR codes from your CSV/Excel data")

    # Sidebar for configuration
    st.sidebar.header("📊 Configuration")
    
    # File upload
    uploaded_file = st.sidebar.file_uploader(
        "Upload CSV or Excel file", 
        type=['csv', 'xlsx', 'xls'],
        help="Upload your data file containing part information"
    )
    
    # Logo uploads
    st.sidebar.header("🖼️ Logo Configuration")
    
    uploaded_first_box_logo = st.sidebar.file_uploader(
        "Upload First Box Logo (Optional)",
        type=['png', 'jpg', 'jpeg'],
        help="Upload a logo for the first box in the ASSLY row"
    )
    
    uploaded_instor_logo = st.sidebar.file_uploader(
        "Upload Instor Logo (Optional)",
        type=['png', 'jpg', 'jpeg'],
        help="Upload your company/Instor logo"
    )

    # Line location configuration
    st.sidebar.header("📍 Line Location Layout")
    st.sidebar.markdown("Configure the width distribution for line location boxes:")
    
    line_loc_header_width = st.sidebar.slider(
        "Header Width", 
        min_value=0.1, max_value=0.5, value=0.3, step=0.05,
        help="Width of 'LINE LOCATION' header"
    )
    
    remaining_width = 1.0 - line_loc_header_width
    
    line_loc_box1_width = st.sidebar.slider(
        "Box 1 Width", 
        min_value=0.05, max_value=remaining_width*0.8, value=remaining_width*0.25, step=0.05,
        help="Width of first location box"
    )
    
    remaining_width2 = remaining_width - line_loc_box1_width
    
    line_loc_box2_width = st.sidebar.slider(
        "Box 2 Width", 
        min_value=0.05, max_value=remaining_width2*0.8, value=remaining_width2*0.33, step=0.05,
        help="Width of second location box"
    )
    
    remaining_width3 = remaining_width2 - line_loc_box2_width
    
    line_loc_box3_width = st.sidebar.slider(
        "Box 3 Width", 
        min_value=0.05, max_value=remaining_width3*0.8, value=remaining_width3*0.5, step=0.05,
        help="Width of third location box"
    )
    
    line_loc_box4_width = remaining_width3 - line_loc_box3_width
    
    st.sidebar.write(f"Box 4 Width: {line_loc_box4_width:.2f} (auto-calculated)")

    # Main content area
    if uploaded_file is not None:
        try:
            # Read the uploaded file
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            
            st.success(f"✅ File uploaded successfully! Found {len(df)} rows.")
            
            # Display data preview
            with st.expander("📋 Data Preview", expanded=True):
                st.dataframe(df.head(10), use_container_width=True)
            
            # Show column information
            with st.expander("📝 Column Information"):
                st.write("**Available Columns:**")
                for i, col in enumerate(df.columns, 1):
                    st.write(f"{i}. `{col}`")
            
            # Generate button
            if st.button("🚀 Generate Sticker Labels", type="primary", use_container_width=True):
                with st.spinner("Generating sticker labels... Please wait."):
                    pdf_data, filename = generate_sticker_labels(
                        df,
                        line_loc_header_width,
                        line_loc_box1_width,
                        line_loc_box2_width,
                        line_loc_box3_width,
                        line_loc_box4_width,
                        uploaded_first_box_logo,
                        uploaded_instor_logo
                    )
                
                if pdf_data:
                    # Success message and download button
                    st.success("🎉 Sticker labels generated successfully!")
                    
                    st.download_button(
                        label="📥 Download PDF",
                        data=pdf_data,
                        file_name=filename,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                    
                    # Display PDF info
                    st.info(f"📄 Generated: {filename} ({len(pdf_data)} bytes)")
                
                else:
                    st.error("❌ Failed to generate sticker labels. Please check your data and try again.")
        
        except Exception as e:
            st.error(f"❌ Error processing file: {str(e)}")
            st.info("Please make sure your file is a valid CSV or Excel file with proper formatting.")
    
    else:
        # Instructions when no file is uploaded
        st.info("👆 Please upload a CSV or Excel file to get started.")
        
        with st.expander("📖 Instructions", expanded=True):
            st.markdown("""
            ### How to use this application:
            
            1. **Upload your data file** (CSV or Excel) using the sidebar
            2. **Configure logos** (optional):
               - Upload a logo for the first box in the ASSLY row
               - Upload your company/Instor logo
            3. **Adjust line location layout** if needed
            4. **Click 'Generate Sticker Labels'** to create your PDF
            5. **Download the generated PDF**
            
            ### Required Columns:
            Your file should contain these columns (case-insensitive):
            - **ASSLY/Assembly**: Assembly name or part assembly
            - **Part No/Part Number**: Unique part identifier  
            - **Description**: Part description
            
            ### Optional Columns:
            - **QTY/Part Per Veh**: Quantity per vehicle/bin
            - **Type**: Part type or category
            - **Line Location**: Location information (will be split into 4 boxes)
            
            ### Features:
            - ✅ Automatic QR code generation
            - ✅ Professional sticker layout
            - ✅ Custom logo support
            - ✅ Configurable line location boxes
            - ✅ Date stamping
            - ✅ Batch processing
            """)

if __name__ == "__main__":
    main()
