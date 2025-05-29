import streamlit as st
import pandas as pd
import os
import re
import datetime
from io import BytesIO
import tempfile
import requests
from PIL import Image as PILImage
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

def create_instor_logo_embedded():
    """Create Instor logo using embedded base64 data"""
    try:
        # Base64 encoded Instor logo (you'll need to replace this with your actual logo's base64)
        # This is a placeholder - you'll need to convert your logo to base64
        logo_base64 = """
        iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==
        """
        
        # For now, we'll create a simple text placeholder
        # You can replace this with your actual logo base64 data
        from reportlab.graphics.shapes import Drawing, String
        from reportlab.graphics import renderPDF
        from reportlab.graphics.renderPDF import drawToString
        
        # Create a simple text logo as placeholder
        # Replace this section with your actual logo processing
        img_buffer = BytesIO()
        
        # Create a simple logo using ReportLab graphics
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import blue, orange
        
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
                          uploaded_logo=None):
    """Generate sticker labels with QR code and logo from DataFrame"""
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

        # Create logo - prioritize uploaded logo, then use embedded version
        instor_logo = None
        if uploaded_logo is not None:
            instor_logo = create_instor_logo_from_upload(uploaded_logo)
            st.success("✅ Using your uploaded logo in labels")
        
        if instor_logo is None:
            instor_logo = create_instor_logo_embedded()
            st.info("ℹ️ Using default Instor logo design")

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

            # Create ASSLY row with 3 boxes: Logo, "ASSLY", Value
            assly_logo = instor_logo if instor_logo else ""
            
            # Create table data with modified ASSLY row structure
            unified_table_data = [
                [assly_logo, "ASSLY", ASSLY],  # Modified: 3 columns for ASSLY row
                ["PART NO", part_no],          # 2 columns for other rows
                ["PART DESC", desc],
                ["PART PER VEH", Paragraph(str(Part_per_veh), partper_style), qr_cell],
                ["TYPE", Paragraph(str(Type), Type_style), ""],
                ["DATE", Paragraph(today_date, date_style), ""],
                ["LINE LOCATION", location_box_1, location_box_2, location_box_3, location_box_4]
            ]

            # Adjusted column widths for ASSLY row - decreased header width, increased value width
            col_widths_assly = [content_width*0.2, content_width*0.25, content_width*0.55]  # Logo, Header (decreased from 0.3 to 0.25), Value (increased from 0.5 to 0.55)
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
                ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),  # ASSLY header bold
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),  # Logo centered
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),  # Header centered
                ('ALIGN', (2, 0), (2, 0), 'LEFT'),    # Value left aligned
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
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                ('ALIGN', (1, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 2),
                ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]

            # Apply styles to tables
            assly_table.setStyle(TableStyle(assly_style))
            top_table.setStyle(TableStyle(top_style))
            middle_table.setStyle(TableStyle(middle_style))
            bottom_table.setStyle(TableStyle(bottom_style))

            # Add tables to elements
            elements.append(assly_table)
            elements.append(top_table)
            elements.append(middle_table)
            elements.append(bottom_table)

            # Add all elements for this sticker
            all_elements.extend(elements)

            # Add page break except for the last item
            if index < total_rows - 1:
                all_elements.append(PageBreak())

        # Build PDF
        doc.build(all_elements, onFirstPage=draw_border, onLaterPages=draw_border)
        
        # Read the PDF file to return as bytes
        with open(output_pdf_path, 'rb') as f:
            pdf_bytes = f.read()
        
        # Clean up temporary file
        os.unlink(output_pdf_path)
        
        return pdf_bytes, found_columns

    except Exception as e:
        st.error(f"Error generating PDF: {e}")
        return None, None

def main():
    st.set_page_config(
        page_title="Instor Label Generator",
        page_icon="🏷️",
        layout="wide"
    )
    
    st.title("🏷️ INSTOR LABEL GENERATOR")
    st.markdown("---")
    
    # Display the Instor logo in sidebar using the uploaded image
    logo_placeholder = st.sidebar.empty()
    
    # Sidebar for configuration
    st.sidebar.header("Configuration")
    
    # Logo upload section - moved to top for better visibility
    st.sidebar.markdown("### 🖼️ Logo Upload")
    uploaded_logo = st.sidebar.file_uploader(
        "Upload your Instor Logo",
        type=['png', 'jpg', 'jpeg'],
        help="Upload your Instor logo image to use in the labels"
    )
    
    # Display uploaded logo in sidebar
    if uploaded_logo is not None:
        logo_placeholder.image(uploaded_logo, width=200, caption="Your Logo (will be used in labels)")
        st.sidebar.success("✅ Logo uploaded - will be used in labels")
    else:
        st.sidebar.info("📁 Please upload your Instor logo above")
    
    st.sidebar.markdown("### Line Location Box Widths")
    st.sidebar.caption("(proportional values)")
    
    header_width = st.sidebar.number_input("Header Width", value=0.3, step=0.01, format="%.2f")
    box1_width = st.sidebar.number_input("Box 1 Width", value=0.2, step=0.01, format="%.2f")
    box2_width = st.sidebar.number_input("Box 2 Width", value=0.25, step=0.01, format="%.2f")
    box3_width = st.sidebar.number_input("Box 3 Width", value=0.15, step=0.01, format="%.2f")
    box4_width = st.sidebar.number_input("Box 4 Width", value=0.1, step=0.01, format="%.2f")
    
    # Main content
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📁 File Upload")
        uploaded_file = st.file_uploader(
            "Choose an Excel or CSV file",
            type=['xlsx', 'xls', 'csv'],
            help="Upload your data file containing label information"
        )
    
    with col2:
        st.header("📋 Preview & Generate")
        
        if uploaded_file is not None:
            try:
                # Load the data
                if uploaded_file.name.lower().endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                st.success(f"✅ File loaded successfully! ({len(df)} rows)")
                
                # Show file info
                with st.expander("📊 File Information", expanded=False):
                    st.write(f"**Total rows:** {len(df)}")
                    st.write(f"**Columns:** {list(df.columns)}")
                
                # Find columns
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
                
                found_columns = {}
                for key, possible_names in column_mappings.items():
                    found_col = find_column(df, possible_names)
                    if found_col:
                        found_columns[key] = found_col
                
                # Show column mappings
                with st.expander("🔍 Column Mappings", expanded=False):
                    for key, col in found_columns.items():
                        st.write(f"**{key}:** {col}")
                
                # Check for required columns
                required_columns = ['ASSLY', 'part_no', 'description']
                missing_required = [col for col in required_columns if col not in found_columns]
                
                if missing_required:
                    st.error(f"⚠️ Missing required columns: {missing_required}")
                    st.info("Please ensure your file contains columns for Assembly, Part Number, and Description")
                else:
                    st.success("✅ All required columns found!")
                    
                    # Show logo status
                    if uploaded_logo is not None:
                        st.success("🖼Custom logo will be used in labels")
                    else:
                        st.info("🖼️ Default Instor logo design will be used")
                    
                    # Preview data
                    with st.expander("👀 Data Preview", expanded=False):
                        st.dataframe(df.head(10))
                    
                    # Generate labels button
                    if st.button("🏷️ Generate Labels", type="primary", use_container_width=True):
                        with st.spinner("Generating labels... Please wait"):
                            pdf_bytes, found_cols = generate_sticker_labels(
                                df, 
                                header_width, 
                                box1_width, 
                                box2_width, 
                                box3_width, 
                                box4_width,
                                uploaded_logo
                            )
                            
                            if pdf_bytes:
                                st.success("✅ Labels generated successfully!")
                                
                                # Create download button
                                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                filename = f"instor_labels_{timestamp}.pdf"
                                
                                st.download_button(
                                    label="📥 Download Labels PDF",
                                    data=pdf_bytes,
                                    file_name=filename,
                                    mime="application/pdf",
                                    type="primary",
                                    use_container_width=True
                                )
                                
                                # Show generation summary
                                st.info(f"📊 Generated {len(df)} labels")
                                
                                # Show found columns summary
                                with st.expander("📋 Generation Summary", expanded=False):
                                    st.write("**Columns used:**")
                                    for key, col in found_cols.items():
                                        st.write(f"- {key}: {col}")
                            else:
                                st.error("❌ Failed to generate labels. Please check your file format and try again.")
            
            except Exception as e:
                st.error(f"❌ Error loading file: {str(e)}")
                st.info("Please make sure your file is a valid Excel (.xlsx, .xls) or CSV file.")
        else:
            st.info("👆 Please upload a file to get started")
    
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: gray; font-size: 0.8em;'>
            🏷️ Instor Label Generator | Built with Streamlit | 
            Supports Excel and CSV files with QR codes and custom logos
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
