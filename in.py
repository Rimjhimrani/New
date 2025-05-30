import streamlit as st
import pandas as pd
import os
import re
import datetime
from io import BytesIO
import tempfile
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

# Define content box dimensions - FIXED: Proper content width calculation
CONTENT_BOX_WIDTH = 9.8 * cm  # Reduced to ensure proper margins
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

def process_uploaded_logo(uploaded_logo, target_width_cm, target_height_cm):
    """Process uploaded logo to fit the specified dimensions"""
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
        
        # Convert cm to pixels for resizing (using 300 DPI)
        dpi = 300
        box_width_px = int(target_width_cm * dpi / 2.54)
        box_height_px = int(target_height_cm * dpi / 2.54)
        
        # Resize with proper aspect ratio handling
        logo_img = logo_img.resize((box_width_px, box_height_px), PILImage.Resampling.LANCZOS)
        
        # Convert to bytes for ReportLab
        img_buffer = BytesIO()
        logo_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Return with 90% of target dimensions for padding
        final_width = target_width_cm * 0.9
        final_height = target_height_cm * 0.9
        
        return Image(img_buffer, width=final_width, height=final_height)
        
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
                          uploaded_first_box_logo=None):
    """Generate sticker labels with QR code from DataFrame"""
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

        # Create PDF with adjusted margins
        def draw_border(canvas, doc):
            canvas.saveState()
            # FIXED: Proper border positioning to match content width
            x_offset = (STICKER_WIDTH - CONTENT_BOX_WIDTH) / 2
            y_offset = STICKER_HEIGHT - CONTENT_BOX_HEIGHT - 0.2*cm
            canvas.setStrokeColor(colors.black)
            canvas.setLineWidth(1.5)
            canvas.rect(
                x_offset,
                y_offset,
                CONTENT_BOX_WIDTH,
                CONTENT_BOX_HEIGHT
            )
            canvas.restoreState()

        # FIXED: Adjusted margins to center content properly
        doc = SimpleDocTemplate(output_pdf_path, pagesize=STICKER_PAGESIZE,
                              topMargin=0.2*cm,
                              bottomMargin=(STICKER_HEIGHT - CONTENT_BOX_HEIGHT - 0.2*cm),
                              leftMargin=(STICKER_WIDTH - CONTENT_BOX_WIDTH) / 2, 
                              rightMargin=(STICKER_WIDTH - CONTENT_BOX_WIDTH) / 2)

        # Define styles
        header_style = ParagraphStyle(name='HEADER', fontName='Helvetica-Bold', fontSize=10, alignment=TA_CENTER, leading=10)
        ASSLY_style = ParagraphStyle(name='ASSLY', fontName='Helvetica', fontSize=9, alignment=TA_LEFT, leading=16, spaceAfter=0, wordWrap='CJK', autoLeading="max")
        Part_style = ParagraphStyle(name='PART NO', fontName='Helvetica-Bold', fontSize=12, alignment=TA_LEFT, leading=46, spaceAfter=0, wordWrap='CJK', autoLeading="max")
        desc_style = ParagraphStyle(name='PART DESC', fontName='Helvetica', fontSize=7, alignment=TA_LEFT, leading=14, spaceAfter=0, wordWrap='CJK', autoLeading="max")  # Smaller font for descriptions
        partper_style = ParagraphStyle(name='Quantity', fontName='Helvetica', fontSize=10, alignment=TA_LEFT, leading=12)
        Type_style = ParagraphStyle(name='Quantity', fontName='Helvetica', fontSize=11, alignment=TA_LEFT, leading=12)
        date_style = ParagraphStyle(name='DATE', fontName='Helvetica', fontSize=10, alignment=TA_LEFT, leading=12)
        location_style = ParagraphStyle(name='Location', fontName='Helvetica', fontSize=9, alignment=TA_CENTER, leading=10)

        # FIXED: Use exact content width for calculations
        content_width = CONTENT_BOX_WIDTH  # 9.8cm
        all_elements = []
        today_date = datetime.datetime.now().strftime("%d-%m-%Y")

        # Handle uploaded logo for first box - calculate proper dimensions
        first_box_logo = None
        if uploaded_first_box_logo is not None:
            # Logo box will be 22% of actual content width
            logo_box_width_cm = (content_width * 0.22) / cm  # Convert back to cm for processing
            logo_box_height_cm = 0.7  # ASSLY row height
            
            first_box_logo = process_uploaded_logo(uploaded_first_box_logo, logo_box_width_cm, logo_box_height_cm)
            if first_box_logo:
                st.success("✅ Using your uploaded logo for first box")
            else:
                st.error("❌ Failed to process uploaded logo")

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
                qr_data += f"QTY/VEH: {Part_per_veh}\n"
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

            # Create ASSLY row - Using exact proportions of content width
            first_box_content = first_box_logo if first_box_logo else ""
            
            # Create table data with ASSLY row structure (3 columns only)
            unified_table_data = [
                [first_box_content, "ASSLY", ASSLY],                      # 3 columns for ASSLY row: Logo(22%), Header(15%), Value(63%)
                ["PART NO", Paragraph(part_no, Part_style)],               # Bold part number
                ["PART DESC", Paragraph(desc, desc_style)],                # Smaller font for description
                ["QTY/VEH", Paragraph(str(Part_per_veh), partper_style), qr_cell],  # Changed label to QTY/VEH
                ["TYPE", Paragraph(str(Type), Type_style), ""],
                ["DATE", Paragraph(today_date, date_style), ""],
                ["LINE LOCATION", location_box_1, location_box_2, location_box_3, location_box_4]
            ]

            # UPDATED: Logo 22%, Header 15%, Value 63%
            col_widths_assly = [
                content_width * 0.22,    # Logo: 22% of content width
                content_width * 0.15,    # Header: 15% of content width
                content_width * 0.63     # Value: 63% of content width
            ]                            # Total: 100% of content width
            
            col_widths_top = [content_width*0.3, content_width*0.7]                         # Regular 2-column rows
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
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),  # Logo box centered
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
                ('FONTSIZE', (0, 0), (0, -1), 11),
                ('FONTSIZE', (1, 0), (-1, 0), 10),
                ('FONTSIZE', (1, 1), (-1, 1), 11),
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

    # Create tabs
    tab1, tab2, tab3 = st.tabs(["📊 Upload Data", "🖼️ Upload Logo", "⚙️ Settings"])
    
    # Initialize session state for uploaded files
    if 'uploaded_file' not in st.session_state:
        st.session_state.uploaded_file = None
    if 'uploaded_logo' not in st.session_state:
        st.session_state.uploaded_logo = None
    
    # Tab 1: Data Upload
    with tab1:
        st.header("📊 Upload Your Data File")
        uploaded_file = st.file_uploader(
            "Choose CSV or Excel file", 
            type=['csv', 'xlsx', 'xls'],
            help="Upload your data file containing part information",
            key="data_uploader"
        )
        
        if uploaded_file is not None:
            st.session_state.uploaded_file = uploaded_file
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
                        
            except Exception as e:
                st.error(f"❌ Error processing file: {str(e)}")
                st.info("💡 Please ensure your file is properly formatted and contains the required columns.")
        else:
            st.info("👆 Please upload a CSV or Excel file to get started.")
            
            with st.expander("📖 Instructions", expanded=True):
                st.markdown("""
                ### Required columns in your data:
                - **Assembly** (ASSLY, Assembly, Assembly Name, etc.)
                - **Part Number** (Part No, PartNo, Part Number, etc.)
                - **Description** (Description, Part Description, etc.)
                
                ### Optional columns:
                - **Quantity** (QTY, Qty/Veh, Part per Veh, etc.)
                - **Type** (Type, TYPE, etc.)
                - **Line Location** (Line Location, LINE LOCATION, etc.)
                """)

            with st.expander("📋 Sample Data Format"):
                st.markdown("""
                Your CSV/Excel file should contain columns similar to:
                
                | ASSLY | PARTNO | DESCRIPTION | QTY/VEH | TYPE | LINE LOCATION |
                |-------|---------|-------------|---------|------|---------------|
                | Engine Assembly | P001 | Engine Block | 1 | Main | A1_B2_C3_D4 |
                | Transmission | P002 | Gear Box | 1 | Sub | E5_F6_G7_H8 |
                
                **Note**: Column names are flexible - the app will automatically detect variations.
                """)

    # Tab 2: Logo Upload
    with tab2:
        st.header("🖼️ Upload Your Logo")
        uploaded_logo = st.file_uploader(
            "Choose logo file",
            type=['png', 'jpg', 'jpeg'],
            help="Upload a logo that will appear in the first box (22% width) of the ASSLY row. The logo will be automatically resized to fit perfectly within the content box.",
            key="logo_uploader"
        )
        
        if uploaded_logo is not None:
            st.session_state.uploaded_logo = uploaded_logo
            st.success("✅ Logo uploaded successfully!")
            
            # Show logo preview
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image(uploaded_logo, caption="Uploaded Logo Preview", width=200)
                
            st.info("ℹ️ This logo will be placed in the first box (22% of content width) of each sticker and automatically resized to fit perfectly within the content box.")
        else:
            st.info("👆 Upload a logo file (PNG, JPG, JPEG) to include it in your stickers.")
            st.markdown("""
            ### Logo Guidelines:
            - **Supported formats**: PNG, JPG, JPEG
            - **Responsive dimensions**: Logo will fit in 22% of content width × 0.7cm height
            - **Automatic resizing**: Logo will be automatically resized to fit perfectly within content box
            - **Position**: Logo appears in the first box of the ASSLY row
            - **Optional**: You can generate stickers without a logo too
            """)

    # Tab 3: Settings
    with tab3:
        st.header("⚙️ Configuration Settings")
        
        # Content box info
        st.subheader("📏 Content Box Dimensions")
        st.info(f"**Content Box Width**: {CONTENT_BOX_WIDTH/cm:.1f}cm | **Height**: {CONTENT_BOX_HEIGHT/cm:.1f}cm")
        
        # ASSLY row configuration
        st.subheader("🏷️ ASSLY Row Layout")
        st.markdown("**Updated ASSLY Row Layout:** Logo (22%) | 'ASSLY' Header (15%) | ASSLY Value (63%) = **100% of Content Width**")
        
        # Visual representation
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Logo Box", "22%", help=f"22% of {CONTENT_BOX_WIDTH/cm:.1f}cm = {(CONTENT_BOX_WIDTH*0.22)/cm:.1f}cm")
        with col2:
            st.metric("ASSLY Header", "15%", help=f"15% of {CONTENT_BOX_WIDTH/cm:.1f}cm = {(CONTENT_BOX_WIDTH*0.15)/cm:.1f}cm")
        with col3:
            st.metric("ASSLY Value", "63%", help=f"63% of {CONTENT_BOX_WIDTH/cm:.1f}cm = {(CONTENT_BOX_WIDTH*0.63)/cm:.1f}cm")
            
        st.subheader("📍 Line Location Configuration")
        st.markdown("Configure the width distribution for Line Location boxes:")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            line_loc_header_width = st.slider(
                "Header Width", 
                min_value=0.1, 
                max_value=0.5, 
                value=0.25, 
                step=0.05,
                help="Width percentage for 'LINE LOCATION' header"
            )
        
        with col2:
            line_loc_box1_width = st.slider(
                "Box 1 Width", 
                min_value=0.1, 
                max_value=0.3, 
                value=0.1875, 
                step=0.025,
                help="Width percentage for Line Location Box 1"
            )
            
        with col3:
            line_loc_box2_width = st.slider(
                "Box 2 Width", 
                min_value=0.1, 
                max_value=0.3, 
                value=0.1875, 
                step=0.025,
                help="Width percentage for Line Location Box 2"
            )
            
        with col4:
            line_loc_box3_width = st.slider(
                "Box 3 Width", 
                min_value=0.1, 
                max_value=0.3, 
                value=0.1875, 
                step=0.025,
                help="Width percentage for Line Location Box 3"
            )
            
        with col5:
            line_loc_box4_width = st.slider(
                "Box 4 Width", 
                min_value=0.1, 
                max_value=0.3, 
                value=0.1875, 
                step=0.025,
                help="Width percentage for Line Location Box 4"
            )
        
        # Show total width validation
        total_width = line_loc_header_width + line_loc_box1_width + line_loc_box2_width + line_loc_box3_width + line_loc_box4_width
        
        if abs(total_width - 1.0) > 0.01:
            st.warning(f"⚠️ Total width is {total_width:.3f}. Should be 1.000 for optimal layout.")
        else:
            st.success(f"✅ Total width: {total_width:.3f} - Perfect!")
            
        # Show actual dimensions
        st.markdown("**Actual Dimensions:**")
        dimensions_col1, dimensions_col2, dimensions_col3, dimensions_col4, dimensions_col5 = st.columns(5)
        
        with dimensions_col1:
            st.metric("Header", f"{(CONTENT_BOX_WIDTH * line_loc_header_width / cm):.1f}cm")
        with dimensions_col2:
            st.metric("Box 1", f"{(CONTENT_BOX_WIDTH * line_loc_box1_width / cm):.1f}cm")
        with dimensions_col3:
            st.metric("Box 2", f"{(CONTENT_BOX_WIDTH * line_loc_box2_width / cm):.1f}cm")
        with dimensions_col4:
            st.metric("Box 3", f"{(CONTENT_BOX_WIDTH * line_loc_box3_width / cm):.1f}cm")
        with dimensions_col5:
            st.metric("Box 4", f"{(CONTENT_BOX_WIDTH * line_loc_box4_width / cm):.1f}cm")

    # Generation Section
    st.markdown("---")
    st.header("🚀 Generate Sticker Labels")
    
    if st.session_state.uploaded_file is not None:
        # Read the data again for generation
        try:
            if st.session_state.uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(st.session_state.uploaded_file)
            else:
                df = pd.read_excel(st.session_state.uploaded_file)
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.info(f"📊 Ready to generate labels for {len(df)} records")
                
            with col2:
                generate_button = st.button(
                    "🏷️ Generate Stickers", 
                    type="primary",
                    use_container_width=True
                )
            
            if generate_button:
                with st.spinner("🔄 Generating sticker labels... Please wait."):
                    pdf_data, filename = generate_sticker_labels(
                        df, 
                        line_loc_header_width, 
                        line_loc_box1_width, 
                        line_loc_box2_width, 
                        line_loc_box3_width, 
                        line_loc_box4_width,
                        st.session_state.uploaded_logo
                    )
                    
                    if pdf_data:
                        st.success("🎉 Stickers generated successfully!")
                        
                        # Create download button
                        st.download_button(
                            label="📥 Download PDF",
                            data=pdf_data,
                            file_name=filename,
                            mime="application/pdf",
                            use_container_width=True
                        )
                        
                        # Show file info
                        st.info(f"📄 File: {filename} | Size: {len(pdf_data)/1024:.1f} KB")
                    else:
                        st.error("❌ Failed to generate sticker labels. Please try again.")
                        
        except Exception as e:
            st.error(f"❌ Error processing data: {str(e)}")
            
    else:
        st.warning("⚠️ Please upload a data file first to generate sticker labels.")
        
    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: #666; font-size: 0.9em;'>
            🏷️ Sticker Label Generator | Built with Streamlit | Generate professional labels with QR codes
        </div>
        """, unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
