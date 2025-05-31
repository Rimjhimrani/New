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
    """Process uploaded logo to fit the specified dimensions - MAXIMUM VISIBILITY"""
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

        # Get original dimensions
        orig_width, orig_height = logo_img.size
        
        # Calculate aspect ratio and resize to fit within bounds while maintaining aspect ratio
        aspect_ratio = orig_width / orig_height
        target_aspect = box_width_px / box_height_px
        
        if aspect_ratio > target_aspect:
            # Image is wider, fit to width
            new_width = box_width_px
            new_height = int(box_width_px / aspect_ratio)
        else:
            # Image is taller, fit to height
            new_height = box_height_px
            new_width = int(box_height_px * aspect_ratio)
        
        # Resize with high quality
        logo_img = logo_img.resize((new_width, new_height), PILImage.Resampling.LANCZOS)

        # Convert to bytes for ReportLab
        img_buffer = BytesIO()
        logo_img.save(img_buffer, format='PNG', quality=100, optimize=False)
        img_buffer.seek(0)

        # CRITICAL FIX: Use actual pixel dimensions converted back to cm for ReportLab
        final_width_cm = new_width * 2.54 / dpi
        final_height_cm = new_height * 2.54 / dpi

        print(f"LOGO DEBUG: Target: {target_width_cm:.2f}cm x {target_height_cm:.2f}cm")
        print(f"LOGO DEBUG: Final: {final_width_cm:.2f}cm x {final_height_cm:.2f}cm")
        print(f"LOGO DEBUG: Pixels: {new_width}px x {new_height}px")
        
        # Create ReportLab Image with actual dimensions
        return Image(img_buffer, width=final_width_cm*cm, height=final_height_cm*cm)

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

        # FIXED: Define styles with better text containment and CENTERED alignment
        header_style = ParagraphStyle(name='HEADER', fontName='Helvetica-Bold', fontSize=8, alignment=TA_CENTER, leading=9)
        # FIXED: ASSLY style with CENTER alignment and proper text wrapping
        ASSLY_style = ParagraphStyle(
            name='ASSLY',
            fontName='Helvetica',
            fontSize=9,  # Increased from 9 for better visibility
            alignment=TA_LEFT,  # FIXED: Changed to CENTER
            leading=11,   # Increased leading for better spacing
            spaceAfter=0,
            wordWrap='CJK',
            autoLeading="max"
        )
        # FIXED: Part No style with CENTER alignment and controlled font size
        Part_style = ParagraphStyle(
            name='PART NO',
            fontName='Helvetica-Bold',
            fontSize= 10,  # Increased from 10 for better visibility
            alignment=TA_LEFT,  # FIXED: Changed to CENTER
            leading=13,   # Increased leading for better spacing
            spaceAfter=0,
            wordWrap='CJK',
            autoLeading="max"
        )
        desc_style = ParagraphStyle(name='PART DESC', fontName='Helvetica', fontSize=7, alignment=TA_LEFT, leading=8, spaceAfter=0, wordWrap='CJK', autoLeading="max")
        partper_style = ParagraphStyle(name='Quantity', fontName='Helvetica', fontSize=10, alignment=TA_LEFT, leading=12)
        Type_style = ParagraphStyle(name='Quantity', fontName='Helvetica', fontSize=10, alignment=TA_LEFT, leading=12)
        date_style = ParagraphStyle(name='DATE', fontName='Helvetica', fontSize=10, alignment=TA_LEFT, leading=12)
        location_style = ParagraphStyle(name='Location', fontName='Helvetica', fontSize=8, alignment=TA_CENTER, leading=10)

        # FIXED: Use exact content width for calculations
        content_width = CONTENT_BOX_WIDTH  # 9.8cm
        all_elements = []
        today_date = datetime.datetime.now().strftime("%d-%m-%Y")

        # Handle uploaded logo for first box - MAXIMUM VISIBILITY LOGO
        first_box_logo = None
        if uploaded_first_box_logo is not None:
            # CRITICAL FIX: Calculate actual available space in the first box
            first_box_width_cm = (content_width * 0.25) / cm  # 25% of content width in cm
            # CRITICAL FIX: Use most of the row height (leaving small margin)
            first_box_height_cm = 0.75  # Use 0.75cm height (leaving 0.1cm margin from 0.85cm row height)

            print(f"CALCULATING LOGO SIZE:")
            print(f"Content width: {content_width/cm:.2f}cm")
            print(f"First box width (25%): {first_box_width_cm:.2f}cm")
            print(f"First box height: {first_box_height_cm:.2f}cm")

            first_box_logo = process_uploaded_logo(uploaded_first_box_logo, first_box_width_cm, first_box_height_cm)
            if first_box_logo:
                st.success(f"✅ Logo processed - Target box: {first_box_width_cm:.2f}cm x {first_box_height_cm:.2f}cm")
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

            # Generate QR code - FIXED: Changed to QTY/VEH
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

            # CRITICAL FIX: Increased row height to accommodate larger logo
            ASSLY_row_height = 0.85*cm  # Keep sufficient height for logo
            part_row_height = 0.8*cm   
            desc_row_height = 0.5*cm
            bottom_row_height = 0.6*cm
            location_row_height = 0.5*cm

            # Process line location boxes
            location_box_1 = Paragraph(location_boxes[0], location_style) if location_boxes[0] else ""
            location_box_2 = Paragraph(location_boxes[1], location_style) if location_boxes[1] else ""
            location_box_3 = Paragraph(location_boxes[2], location_style) if location_boxes[2] else ""
            location_box_4 = Paragraph(location_boxes[3], location_style) if location_boxes[3] else ""

            # Create ASSLY row - Using exact proportions of content width
            first_box_content = first_box_logo if first_box_logo else ""

            # FIXED: Create table data with CENTER aligned paragraph wrapping for ASSLY and Part No
            unified_table_data = [
                [first_box_content, "ASSLY", Paragraph(ASSLY, ASSLY_style)],  # FIXED: Center-aligned ASSLY text
                ["PART NO", Paragraph(f"<b>{part_no}</b>", Part_style)],      # FIXED: Center-aligned Part No text
                ["PART DESC", Paragraph(desc, desc_style)],
                ["QTY/VEH", Paragraph(str(Part_per_veh), partper_style), qr_cell],
                ["TYPE", Paragraph(str(Type), Type_style), ""],
                ["DATE", Paragraph(today_date, date_style), ""],
                ["LINE LOCATION", location_box_1, location_box_2, location_box_3, location_box_4]
            ]

            # FIXED: Standardized column widths - all headers are 25% except ASSLY row
            col_widths_assly = [
                content_width * 0.25,    # Logo: 25% (same as line location header)
                content_width * 0.15,    # Header: 15%
                content_width * 0.60     # Value: 60%
            ]

            col_widths_standard = [content_width * 0.25, content_width * 0.75]              # Standard 2-column rows: Header(25%), Value(75%)
            col_widths_middle = [content_width * 0.25, content_width * 0.35, content_width * 0.40]   # 3-column with QR: Header(25%), Value(35%), QR(40%)
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
            top_table = Table(unified_table_data[1:3], colWidths=col_widths_standard, rowHeights=row_heights[1:3])
            middle_table = Table(unified_table_data[3:6], colWidths=col_widths_middle, rowHeights=row_heights[3:6])
            bottom_table = Table([unified_table_data[6]], colWidths=col_widths_bottom, rowHeights=[row_heights[6]])

            # CRITICAL FIX: Apply styles with MIDDLE vertical alignment and MINIMAL PADDING for maximum logo space
            assly_style = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),  # ASSLY header bold
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),  # Logo box centered
                ('ALIGN', (1, 0), (1, 0), 'CENTER'),  # Header centered
                ('ALIGN', (2, 0), (2, 0), 'CENTER'),  # FIXED: Value CENTER aligned
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # CRITICAL: MIDDLE alignment for vertical centering
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 1),  # MINIMAL padding for maximum logo space
                ('RIGHTPADDING', (0, 0), (-1, -1), 1),
                ('TOPPADDING', (0, 0), (-1, -1), 1),  # MINIMAL top padding
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),  # MINIMAL bottom padding
            ]

            top_style = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),  # Headers bold
                ('FONTSIZE', (0, 0), (0, -1), 8),
                ('FONTSIZE', (1, 0), (-1, 0), 7),
                ('FONTSIZE', (1, 1), (-1, 1), 11),  # Part No larger font
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, 0), 'LEFT'),  # Description left aligned
                ('ALIGN', (1, 1), (1, 1), 'CENTER'),  # FIXED: Part No CENTER aligned
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # FIXED: MIDDLE alignment for vertical centering
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),  # Increased padding
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]

            middle_style = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),  # Headers bold
                ('FONTSIZE', (0, 0), (0, 0), 8),
                ('FONTSIZE', (0, 1), (0, 2), 8),
                ('FONTSIZE', (1, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),  # Increased padding
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('SPAN', (2, 0), (2, 2)),
            ]

            bottom_style = [
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                ('ALIGN', (1, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),  # Increased padding
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
        st.success(f"✅ Successfully generated {total_rows} sticker labels with MAXIMUM VISIBILITY LOGOS!")

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
            help="Upload a logo that will appear with MAXIMUM VISIBILITY in the first box (25% width) of the ASSLY row. Logo will be optimized at 300 DPI and scaled to use the full 0.75cm height for maximum impact.",
            key="logo_uploader"
        )

        if uploaded_logo is not None:
            st.session_state.uploaded_logo = uploaded_logo
            try:
                # Display logo preview
                logo_img = PILImage.open(uploaded_logo)
                st.success("✅ Logo uploaded successfully!")
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.image(logo_img, caption="Uploaded Logo", width=200)
                with col2:
                    st.info(f"""
                    **Logo Information:**
                    - Format: {logo_img.format}
                    - Size: {logo_img.size[0]} x {logo_img.size[1]} pixels
                    - Mode: {logo_img.mode}
                    
                    **Maximum Visibility Features:**
                    - Logo will use the full height of ASSLY row (0.75cm)
                    - Maintains aspect ratio for clear display
                    - Optimized at 300 DPI for crisp printing
                    - Takes 25% width of content box for prominence
                    """)
                    
                    # Show logo positioning preview
                    st.markdown("### 📐 Logo Positioning Preview")
                    st.markdown("""
                    ```
                    ┌─────────────────────────────────────────┐
                    │ [LOGO]  │ ASSLY │     Assembly Name     │ ← Maximum height row
                    ├─────────┼───────┼───────────────────────┤
                    │ PART NO │         Part Number           │
                    ├─────────┼───────────────────────────────┤
                    │ PART DESC │      Description            │
                    └─────────────────────────────────────────┘
                    ```
                    Logo occupies 25% width with maximum vertical space!
                    """)

            except Exception as e:
                st.error(f"❌ Error processing logo: {str(e)}")
        else:
            st.info("🖼️ Upload a logo to enhance your sticker labels with maximum visibility!")
            
            with st.expander("📖 Logo Guidelines", expanded=True):
                st.markdown("""
                ### 🎯 Maximum Logo Visibility Features:
                - **Optimal Size**: Logo will be automatically resized for maximum visibility
                - **High Quality**: Processed at 300 DPI for crisp printing
                - **Smart Scaling**: Maintains aspect ratio while maximizing display area
                - **Prominent Position**: Takes 25% of sticker width in top row
                - **Full Height Usage**: Uses 0.75cm height (85% of ASSLY row)
                
                ### 📋 Supported Formats:
                - PNG (recommended for logos with transparency)
                - JPG/JPEG (good for photographic logos)
                
                ### 💡 Tips for Best Results:
                - Use high-resolution images (300+ DPI)
                - Square or rectangular logos work best
                - Transparent backgrounds are converted to white
                - Logo will be center-aligned in its box
                """)

    # Tab 3: Settings
    with tab3:
        st.header("⚙️ Line Location Box Settings")
        st.markdown("Customize the width distribution of line location boxes (must total 1.0)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            line_loc_header_width = st.slider(
                "Header Width", 
                min_value=0.1, 
                max_value=0.5, 
                value=0.25, 
                step=0.05,
                help="Width of 'LINE LOCATION' header column"
            )
            
            line_loc_box1_width = st.slider(
                "Box 1 Width", 
                min_value=0.1, 
                max_value=0.4, 
                value=0.1875, 
                step=0.0125,
                help="Width of first location box"
            )
        
        with col2:
            line_loc_box2_width = st.slider(
                "Box 2 Width", 
                min_value=0.1, 
                max_value=0.4, 
                value=0.1875, 
                step=0.0125,
                help="Width of second location box"
            )
            
            line_loc_box3_width = st.slider(
                "Box 3 Width", 
                min_value=0.1, 
                max_value=0.4, 
                value=0.1875, 
                step=0.0125,
                help="Width of third location box"
            )
        
        # Calculate box 4 width automatically
        line_loc_box4_width = 1.0 - (line_loc_header_width + line_loc_box1_width + 
                                    line_loc_box2_width + line_loc_box3_width)
        
        st.info(f"**Box 4 Width**: {line_loc_box4_width:.4f} (auto-calculated)")
        
        # Validation
        total_width = (line_loc_header_width + line_loc_box1_width + 
                      line_loc_box2_width + line_loc_box3_width + line_loc_box4_width)
        
        if abs(total_width - 1.0) > 0.001:
            st.error(f"⚠️ Total width must equal 1.0 (currently: {total_width:.4f})")
        else:
            st.success(f"✅ Total width: {total_width:.4f}")

        # Visual preview of layout
        with st.expander("📐 Layout Preview"):
            st.markdown("### Line Location Row Layout:")
            preview_cols = st.columns([
                line_loc_header_width, 
                line_loc_box1_width, 
                line_loc_box2_width, 
                line_loc_box3_width, 
                line_loc_box4_width
            ])
            
            with preview_cols[0]:
                st.markdown("**HEADER**")
            with preview_cols[1]:
                st.markdown("**Box 1**")
            with preview_cols[2]:
                st.markdown("**Box 2**")
            with preview_cols[3]:
                st.markdown("**Box 3**")
            with preview_cols[4]:
                st.markdown("**Box 4**")

    # Generate Button
    st.header("🚀 Generate Sticker Labels")
    
    if st.session_state.uploaded_file is not None:
        if st.button("📄 Generate PDF Labels", type="primary", use_container_width=True):
            with st.spinner("🔄 Processing data and generating labels with maximum logo visibility..."):
                try:
                    # Read the data file again
                    if st.session_state.uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(st.session_state.uploaded_file)
                    else:
                        df = pd.read_excel(st.session_state.uploaded_file)
                    
                    # Generate sticker labels
                    pdf_data, filename = generate_sticker_labels(
                        df, 
                        line_loc_header_width,
                        line_loc_box1_width, 
                        line_loc_box2_width, 
                        line_loc_box3_width, 
                        line_loc_box4_width,
                        uploaded_first_box_logo=st.session_state.uploaded_logo
                    )
                    
                    if pdf_data:
                        # Provide download button
                        st.download_button(
                            label="📥 Download PDF Labels",
                            data=pdf_data,
                            file_name=filename,
                            mime="application/pdf",
                            use_container_width=True
                        )
                        
                        st.success("🎉 PDF generated successfully with maximum logo visibility!")
                        st.balloons()
                        
                        # Show generation summary
                        with st.expander("📊 Generation Summary", expanded=True):
                            st.markdown(f"""
                            **📈 Labels Generated**: {len(df)} stickers
                            **🖼️ Logo Status**: {'✅ Included with maximum visibility' if st.session_state.uploaded_logo else '❌ No logo uploaded'}
                            **📏 Logo Dimensions**: 25% width × 0.75cm height (optimized for visibility)
                            **📄 File Size**: {len(pdf_data) / 1024:.1f} KB
                            **🕒 Generated**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                            
                            **🎯 Maximum Visibility Features Applied:**
                            - High-resolution logo processing (300 DPI)
                            - Optimal positioning in prominent top row
                            - Smart aspect ratio preservation
                            - Minimal padding for maximum logo space
                            - Center alignment for professional appearance
                            """)
                    else:
                        st.error("❌ Failed to generate PDF. Please check your data and try again.")
                        
                except Exception as e:
                    st.error(f"❌ Error during generation: {str(e)}")
                    st.info("💡 Please check your data format and column names.")
    else:
        st.warning("⚠️ Please upload a data file first to generate labels.")
        st.info("👆 Go to the 'Upload Data' tab to get started.")

    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666; padding: 20px;'>
        <h4>🏷️ Sticker Label Generator</h4>
        <p>Professional sticker labels with QR codes and maximum logo visibility</p>
        <p><strong>Features:</strong> Auto column detection • High-quality logos • Custom layouts • QR code generation</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
