import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import os
import json

# --- Google Connection Settings ---
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# File Names on Google Drive
SHEET_NAME = "Master_Dental_Data"
DRIVE_FOLDER_NAME = "Dental_Atlas_Uploads"

# --- Backend Functions ---

def get_google_clients():
    """Connect to Google Services using Streamlit Secrets or Local JSON"""
    creds = None
    
    # 1. Try Streamlit Secrets (Cloud)
    if "gcp_service_account" in st.secrets:
        try:
            # Convert secrets to dict directly (no JSON string building)
            creds_dict = {
                "type": st.secrets["gcp_service_account"]["type"],
                "project_id": st.secrets["gcp_service_account"]["project_id"],
                "private_key_id": st.secrets["gcp_service_account"]["private_key_id"],
                "private_key": st.secrets["gcp_service_account"]["private_key"],
                "client_email": st.secrets["gcp_service_account"]["client_email"],
                "client_id": st.secrets["gcp_service_account"]["client_id"],
                "auth_uri": st.secrets["gcp_service_account"]["auth_uri"],
                "token_uri": st.secrets["gcp_service_account"]["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["gcp_service_account"]["auth_provider_x509_cert_url"],
                "client_x509_cert_url": st.secrets["gcp_service_account"]["client_x509_cert_url"],
                "universe_domain": st.secrets["gcp_service_account"].get("universe_domain", "googleapis.com")
            }
            
            # Create credentials
            creds = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=SCOPE
            )
            
        except json.JSONDecodeError as e:
            st.error(f"❌ JSON Parse Error: {e}")
            st.error("The private key format might be corrupted. Try the alternative method below.")
            st.info("💡 Use the 'Upload JSON File' option in the sidebar instead")
            st.stop()
        except Exception as e:
            st.error(f"❌ Authentication Error: {e}")
            st.info("💡 Try using the 'Upload JSON File' option in the sidebar instead")
            st.stop()
    
    # 2. Try Local File (Localhost)
    elif os.path.exists("secrets.json"):
        try:
            creds = service_account.Credentials.from_service_account_file(
                "secrets.json",
                scopes=SCOPE
            )
        except Exception as e:
            st.error(f"❌ Error loading secrets.json: {e}")
            st.stop()
    
    else:
        st.error("❌ Error: Secrets not found.")
        st.stop()
    
    try:
        # Authorize clients
        gc = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        return gc, drive_service
    except Exception as e:
        st.error(f"❌ Failed to authorize Google services: {e}")
        st.exception(e)
        st.stop()

def get_google_clients_from_uploaded_json(json_file):
    """Create credentials from uploaded JSON file"""
    try:
        # Read the uploaded file
        json_content = json.load(json_file)
        
        # Create credentials
        creds = service_account.Credentials.from_service_account_info(
            json_content,
            scopes=SCOPE
        )
        
        # Authorize clients
        gc = gspread.authorize(creds)
        drive_service = build('drive', 'v3', credentials=creds)
        
        return gc, drive_service
    except Exception as e:
        st.error(f"❌ Error loading JSON file: {e}")
        st.exception(e)
        return None, None

def find_drive_folder_id(service, folder_name):
    """Find the Folder ID in Google Drive"""
    try:
        query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        
        if not items:
            st.error(f"❌ Folder '{folder_name}' not found in Drive.")
            st.info(f"💡 Make sure to share the folder with your service account email")
            st.stop()
            
        return items[0]['id']
    except Exception as e:
        st.error(f"❌ Error accessing Drive folder: {e}")
        st.stop()

def upload_to_drive(service, file_obj, filename, folder_id):
    """Upload a file to Google Drive and return link"""
    try:
        file_obj.seek(0)
        
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        
        file_bytes = io.BytesIO(file_obj.read())
        media = MediaIoBaseUpload(file_bytes, mimetype=file_obj.type, resumable=True)
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"❌ Upload failed for {filename}: {e}")
        return "Upload Failed"

def generate_usid(fdi_code, dentition, arch, side, count):
    """Generate unique specimen ID"""
    d_code = "P" if dentition == "Permanent" else "D"
    a_code = "Mx" if arch == "Maxillary" else "Md"
    s_code = "R" if side == "Right" else "L"
    return f"{fdi_code}-{d_code}-{a_code}-{s_code}-{count:03d}"

# --- Frontend App ---

st.set_page_config(page_title="Dental Atlas", page_icon="🦷", layout="wide")

# Sidebar for alternative authentication
with st.sidebar:
    st.header("🔐 Authentication")
    auth_method = st.radio(
        "Choose Method:",
        ["Use Streamlit Secrets", "Upload JSON File"]
    )
    
    if auth_method == "Upload JSON File":
        st.info("Upload your service account JSON file downloaded from Google Cloud Console")
        uploaded_json = st.file_uploader("Service Account JSON", type=['json'])
        use_uploaded = uploaded_json is not None
    else:
        use_uploaded = False
        uploaded_json = None

st.title("🦷 Dental Atlas - Cloud Data Collection System")
st.caption("Connected to Google Drive & Sheets")

# Initialize Connection
gc = None
drive_service = None
sheet = None
folder_id = None

try:
    with st.spinner("Connecting to Google Services..."):
        if use_uploaded and uploaded_json:
            # Use uploaded JSON file
            gc, drive_service = get_google_clients_from_uploaded_json(uploaded_json)
        else:
            # Use secrets
            gc, drive_service = get_google_clients()
        
        if gc is None or drive_service is None:
            st.stop()
        
    # Open or create spreadsheet
    try:
        sheet = gc.open(SHEET_NAME).sheet1
        st.success("✅ Connected to Google Sheet")
    except gspread.SpreadsheetNotFound:
        st.error(f"❌ Google Sheet '{SHEET_NAME}' not found.")
        st.info(f"💡 Create a sheet named '{SHEET_NAME}' and share it with your service account")
        st.stop()
    
    # Find Drive folder
    folder_id = find_drive_folder_id(drive_service, DRIVE_FOLDER_NAME)
    st.success(f"✅ Connected to Drive folder: {DRIVE_FOLDER_NAME}")
    
except Exception as e:
    st.error(f"⚠️ Connection Failed: {e}")
    if not use_uploaded:
        st.warning("💡 Try using 'Upload JSON File' method in the sidebar instead")
    st.stop()

st.divider()

# Only show form if connected
if sheet and folder_id:
    # Data Entry Form
    with st.form("cloud_form", clear_on_submit=True):
        st.subheader("📝 New Tooth Entry")
        
        # Section 1: General Information
        st.markdown("### 👤 Collection Details")
        c1, c2, c3 = st.columns(3)
        collector = c1.selectbox("Collector", [
            "Dr. Doaa", 
            "Dr. Fawzy", 
            "Dr. Liala", 
            "Dr. Mahmoud", 
            "Dr. Aya", 
            "Dr. Sohila", 
            "Dr. Enas", 
            "Dr. Sara", 
            "Dr. Eman"
        ])
        source = c2.selectbox("Source", ["University Hospital", "Private Clinic"])
        patient_gender = c3.selectbox("Patient Gender", ["Male", "Female", "Unknown"])
        
        # Medical History
        medical_history = st.text_area("Medical History (Optional)", 
                                       placeholder="Enter any relevant medical history, conditions, or notes...",
                                       height=100)
        
        # Section 2: Tooth Identity
        st.markdown("### 🦷 Tooth Identity")
        c3, c4, c5 = st.columns(3)
        dentition = c3.radio("Dentition", ["Permanent", "Deciduous"])
        arch = c4.radio("Arch", ["Maxillary", "Mandibular"])
        side = c5.radio("Side", ["Right", "Left"])
        
        c6, c7 = st.columns(2)
        tooth_class = c6.selectbox("Tooth Class", ["Incisor", "Canine", "Premolar", "Molar"])
        fdi_code = c7.text_input("FDI Code (2 digits)", max_chars=2, placeholder="e.g., 11, 36")
        
        # FDI Notation Guide with Image
        with st.expander("📖 FDI Notation Guide (Click to view chart)", expanded=False):
            st.image("https://i.imgur.com/8KX5YJZ.png", 
                    caption="FDI Two-Digit Tooth Numbering System",
                    use_container_width=True)
            st.markdown("""
            **How to read the FDI notation:**
            - **First digit** = Quadrant (1-4 for permanent, 5-8 for deciduous)
            - **Second digit** = Tooth position (1-8 for permanent, 1-5 for deciduous)
            
            **Examples:**
            - `11` = Upper right central incisor (permanent)
            - `36` = Lower left first molar (permanent)
            - `51` = Upper right central incisor (deciduous)
            """)


        # Section 3: Measurements
        st.markdown("### 📏 Measurements")
        c8, c9 = st.columns(2)
        crown_h = c8.number_input("Crown Height (mm)", min_value=0.0, step=0.1, format="%.1f")
        root_l = c9.number_input("Root Length (mm)", min_value=0.0, step=0.1, format="%.1f")
        
        # Section 4: File Uploads
        st.markdown("### 📸 File Uploads")
        st.info("Choose to upload files OR provide links (not both)")
        
        # Image Upload/Link
        st.markdown("**Tooth Image:**")
        img_col1, img_col2 = st.columns(2)
        uploaded_image = img_col1.file_uploader("Upload Image", type=['jpg', 'png', 'jpeg'], key="img_upload")
        image_link = img_col2.text_input("OR paste image link", placeholder="https://...", key="img_link")
        
        # DICOM/CBCT Upload/Link
        st.markdown("**CBCT Data:**")
        dicom_col1, dicom_col2 = st.columns(2)
        uploaded_dicom = dicom_col1.file_uploader("Upload DICOM/Zip", type=['dcm', 'zip'], key="dicom_upload")
        dicom_link_input = dicom_col2.text_input("OR paste CBCT link", placeholder="https://...", key="dicom_link")
        
        st.divider()
        
        # --- ID GENERATION PREVIEW ---
        try:
            existing_data = sheet.get_all_values()
            count = len(existing_data) 
        except:
            count = 1 
        
        if fdi_code:
            generated_usid = generate_usid(fdi_code, dentition, arch, side, count)
            st.info(f"🔹 **Generated ID:** `{generated_usid}`")
        else:
            st.warning("⚠️ Enter FDI Code to preview ID")
        
        # Submit Button
        submitted = st.form_submit_button("🚀 SAVE TO CLOUD", type="primary", use_container_width=True)

        if submitted:
            # Validation
            if not fdi_code or len(fdi_code) != 2:
                st.error("❌ Please enter a valid 2-digit FDI Code")
            else:
                with st.spinner("📤 Processing..."):
                    try:
                        # Generate final ID
                        final_usid = generate_usid(fdi_code, dentition, arch, side, count)
                        
                        # 1. Handle Image - Upload or Link
                        img_link = "No Image"
                        if uploaded_image:
                            file_ext = uploaded_image.name.split('.')[-1]
                            fname = f"{final_usid}.{file_ext}"
                            img_link = upload_to_drive(drive_service, uploaded_image, fname, folder_id)
                            st.success(f"✅ Image uploaded: {fname}")
                        elif image_link.strip():
                            img_link = image_link.strip()
                            st.success(f"✅ Image link saved")
                        
                        # 2. Handle DICOM - Upload or Link
                        dicom_link = "No File"
                        if uploaded_dicom:
                            file_ext = uploaded_dicom.name.split('.')[-1]
                            fname = f"{final_usid}_CBCT.{file_ext}"
                            dicom_link = upload_to_drive(drive_service, uploaded_dicom, fname, folder_id)
                            st.success(f"✅ CBCT uploaded: {fname}")
                        elif dicom_link_input.strip():
                            dicom_link = dicom_link_input.strip()
                            st.success(f"✅ CBCT link saved")

                        # 3. Save Data to Sheet
                        new_row = [
                            final_usid, 
                            collector, 
                            str(datetime.now().date()), 
                            source,
                            patient_gender,
                            medical_history if medical_history.strip() else "None",
                            dentition, 
                            arch, 
                            side, 
                            tooth_class, 
                            fdi_code,
                            crown_h, 
                            root_l, 
                            img_link, 
                            dicom_link
                        ]
                        
                        sheet.append_row(new_row)
                        
                        st.success(f"🎉 **Successfully saved!** Data ID: `{final_usid}`")
                        
                        # Display links
                        col1, col2 = st.columns(2)
                        if img_link != "No Image":
                            col1.markdown(f"[🔗 View Image]({img_link})")
                        if dicom_link != "No File":
                            col2.markdown(f"[🔗 View CBCT]({dicom_link})")
                            
                    except Exception as e:
                        st.error(f"❌ Error saving data: {e}")
                        st.exception(e)

    # Display recent entries
    st.divider()
    st.subheader("📊 Recent Entries")

    try:
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            st.dataframe(df.tail(10), use_container_width=True)
        else:
            st.info("No data yet. Submit the first entry!")
    except Exception as e:
        st.warning(f"Could not load recent data: {e}")
