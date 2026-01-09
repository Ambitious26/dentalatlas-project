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
            # Create a mutable copy of the secrets dictionary
            creds_dict = dict(st.secrets["gcp_service_account"])
            
            # 🔴 FIX: Handle newline characters properly
            if "private_key" in creds_dict:
                private_key = str(creds_dict["private_key"])
                
                # Check if key has literal \n that need conversion
                if "\\n" in repr(private_key):
                    # This means we have string "\n" not actual newlines
                    # Use encode/decode to properly convert escape sequences
                    try:
                        private_key = private_key.encode().decode('unicode_escape')
                    except:
                        # Fallback to simple replace
                        private_key = private_key.replace("\\n", "\n")
                
                # Ensure proper format
                lines = private_key.strip().split('\n')
                if len(lines) < 3:
                    st.error("❌ Private key format is incorrect - not enough lines")
                    st.info("Expected format with actual line breaks between key sections")
                    st.stop()
                    
                creds_dict["private_key"] = private_key
            
            # Use google.oauth2.service_account instead of oauth2client
            creds = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=SCOPE
            )
            
        except Exception as e:
            st.error(f"❌ Authentication Error: {e}")
            st.exception(e)
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
st.title("🦷 Dental Atlas - Cloud Data Collection System")
st.caption("Connected to Google Drive & Sheets")

# Initialize Connection
try:
    with st.spinner("Connecting to Google Services..."):
        gc, drive_service = get_google_clients()
        
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
    st.stop()

st.divider()

# Data Entry Form
with st.form("cloud_form", clear_on_submit=True):
    st.subheader("📝 New Tooth Entry")
    
    # Section 1: General Information
    st.markdown("### 👤 Collection Details")
    c1, c2 = st.columns(2)
    collector = c1.selectbox("Collector", ["TA 1", "TA 2", "TA 3", "TA 4", "TA 5"])
    source = c2.selectbox("Source", ["University Hospital", "Private Clinic"])
    
    # Section 2: Tooth Identity
    st.markdown("### 🦷 Tooth Identity")
    c3, c4, c5 = st.columns(3)
    dentition = c3.radio("Dentition", ["Permanent", "Deciduous"])
    arch = c4.radio("Arch", ["Maxillary", "Mandibular"])
    side = c5.radio("Side", ["Right", "Left"])
    
    c6, c7 = st.columns(2)
    tooth_class = c6.selectbox("Tooth Class", ["Incisor", "Canine", "Premolar", "Molar"])
    fdi_code = c7.text_input("FDI Code (2 digits)", max_chars=2, placeholder="e.g., 11, 36")

    # Section 3: Measurements
    st.markdown("### 📏 Measurements")
    c8, c9 = st.columns(2)
    crown_h = c8.number_input("Crown Height (mm)", min_value=0.0, step=0.1, format="%.1f")
    root_l = c9.number_input("Root Length (mm)", min_value=0.0, step=0.1, format="%.1f")
    
    # Section 4: File Uploads
    st.markdown("### 📸 File Uploads")
    c_img, c_dicom = st.columns(2)
    uploaded_image = c_img.file_uploader("📷 Tooth Image", type=['jpg', 'png', 'jpeg'])
    uploaded_dicom = c_dicom.file_uploader("📊 CBCT Data", type=['dcm', 'zip'])
    
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
            with st.spinner("📤 Uploading to Google Drive..."):
                try:
                    # Generate final ID
                    final_usid = generate_usid(fdi_code, dentition, arch, side, count)
                    
                    # 1. Upload Image
                    img_link = "No Image"
                    if uploaded_image:
                        file_ext = uploaded_image.name.split('.')[-1]
                        fname = f"{final_usid}.{file_ext}"
                        img_link = upload_to_drive(drive_service, uploaded_image, fname, folder_id)
                        st.success(f"✅ Image uploaded: {fname}")
                    
                    # 2. Upload DICOM
                    dicom_link = "No File"
                    if uploaded_dicom:
                        file_ext = uploaded_dicom.name.split('.')[-1]
                        fname = f"{final_usid}_CBCT.{file_ext}"
                        dicom_link = upload_to_drive(drive_service, uploaded_dicom, fname, folder_id)
                        st.success(f"✅ CBCT uploaded: {fname}")

                    # 3. Save Data to Sheet
                    new_row = [
                        final_usid, 
                        collector, 
                        str(datetime.now().date()), 
                        source,
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
