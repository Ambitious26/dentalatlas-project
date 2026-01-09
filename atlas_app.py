import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# --- إعدادات الاتصال بجوجل ---
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SECRETS_FILE = "secrets.json"  # تأكد أن الملف بجوار الكود

# أسماء الملفات على جوجل (يجب أن تكون أنشأتها وشاركتها مع إيميل الـ Service Account)
SHEET_NAME = "Master_Dental_Data"
DRIVE_FOLDER_NAME = "Dental_Atlas_Uploads"

# --- دوال الاتصال (Backend Functions) ---

def get_google_clients():
    """الاتصال بجوجل وإرجاع أدوات التحكم"""
    creds = ServiceAccountCredentials.from_json_keyfile_name(SECRETS_FILE, SCOPE)
    
    # 1. عميل Google Sheets
    gc = gspread.authorize(creds)
    
    # 2. عميل Google Drive
    drive_service = build('drive', 'v3', credentials=creds)
    
    return gc, drive_service

def find_drive_folder_id(service, folder_name):
    """البحث عن ID مجلد الصور"""
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    if not items:
        st.error(f"❌ لم يتم العثور على مجلد '{folder_name}' في الدرايف! تأكد من مشاركته.")
        return None
    return items[0]['id']

def upload_to_drive(service, file_obj, filename, folder_id):
    """رفع الملفات إلى جوجل درايف"""
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(file_obj, mimetype=file_obj.type)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    return file.get('webViewLink')

# --- واجهة التطبيق (Frontend) ---

st.set_page_config(page_title="Dental Atlas (Cloud)", page_icon="☁️")
st.title("☁️ Dental Atlas (Live System)")
st.caption("Connected to Google Drive & Sheets")

# محاولة الاتصال عند بدء التطبيق
try:
    gc, drive_service = get_google_clients()
    sheet = gc.open(SHEET_NAME).sheet1
    folder_id = find_drive_folder_id(drive_service, DRIVE_FOLDER_NAME)
    st.success("✅ Connected to Google Services")
except Exception as e:
    st.error(f"⚠️ Connection Failed: {e}")
    st.stop()

with st.form("cloud_form", clear_on_submit=True):
    st.info("📝 Data Entry")
    
    # البيانات الأساسية
    c1, c2 = st.columns(2)
    collector = c1.selectbox("Collector", ["TA 1", "TA 2", "TA 3", "TA 4", "TA 5"])
    source = c2.selectbox("Source", ["University Hospital", "Private Clinic"])
    
    # هوية السن
    st.divider()
    c3, c4, c5 = st.columns(3)
    dentition = c3.radio("Dentition", ["Permanent", "Deciduous"])
    arch = c4.radio("Arch", ["Maxillary", "Mandibular"])
    side = c5.radio("Side", ["Right", "Left"])
    
    c6, c7 = st.columns(2)
    tooth_class = c6.selectbox("Class", ["Incisor", "Canine", "Premolar", "Molar"])
    fdi_code = c7.text_input("FDI Code", max_chars=2)

    # القياسات
    st.divider()
    c8, c9 = st.columns(2)
    crown_h = c8.number_input("Crown H (mm)", step=0.1)
    root_l = c9.number_input("Root L (mm)", step=0.1)
    
    # رفع الميديا
    st.header("📸 Upload to Drive")
    c_img, c_dicom = st.columns(2)
    uploaded_image = c_img.file_uploader("Image", type=['jpg', 'png', 'jpeg'])
    uploaded_dicom = c_dicom.file_uploader("DICOM/Zip", type=['dcm', 'zip'])
    
    # توليد الكود (بناءً على عدد الصفوف في شيت جوجل الحالي)
    # ملاحظة: هذا يتطلب قراءة الشيت، قد يستغرق ثانية
    existing_data = sheet.get_all_values()
    count = len(existing_data)  # عدد الصفوف الحالي (بما فيها العنوان)
    
    d_code = "P" if dentition == "Permanent" else "D"
    a_code = "Mx" if arch == "Maxillary" else "Md"
    s_code = "R" if side == "Right" else "L"
    generated_usid = f"{fdi_code}-{d_code}-{a_code}-{s_code}-{count:03d}"
    
    st.write(f"🔹 New ID: **{generated_usid}**")
    
    submitted = st.form_submit_button("🚀 SAVE TO CLOUD", type="primary")

    if submitted:
        if not fdi_code:
            st.error("Missing FDI Code!")
        else:
            with st.spinner("Uploading to Google Drive..."):
                # 1. رفع الصورة
                img_link = "No Image"
                if uploaded_image:
                    file_ext = uploaded_image.name.split('.')[-1]
                    fname = f"{generated_usid}.{file_ext}"
                    img_link = upload_to_drive(drive_service, uploaded_image, fname, folder_id)
                
                # 2. رفع الأشعة
                dicom_link = "No File"
                if uploaded_dicom:
                    file_ext = uploaded_dicom.name.split('.')[-1]
                    fname = f"{generated_usid}_CBCT.{file_ext}"
                    dicom_link = upload_to_drive(drive_service, uploaded_dicom, fname, folder_id)

                # 3. حفظ البيانات في الشيت
                new_row = [
                    generated_usid, collector, str(datetime.now().date()), source,
                    dentition, arch, side, tooth_class, fdi_code,
                    crown_h, root_l, img_link, dicom_link
                ]
                
                sheet.append_row(new_row)
                st.success(f"🎉 Saved! Data is now on Google Sheet.")
                if img_link != "No Image":
                    st.markdown(f"[View Image on Drive]({img_link})")