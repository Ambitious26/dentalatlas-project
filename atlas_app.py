import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import os

# --- إعدادات الاتصال بجوجل ---
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# أسماء الملفات على جوجل (تأكد من مطابقتها لما أنشأته)
SHEET_NAME = "Master_Dental_Data"
DRIVE_FOLDER_NAME = "Dental_Atlas_Uploads"

# --- دوال الاتصال (Backend Functions) ---

def get_google_clients():
    """
    دالة ذكية للاتصال بجوجل:
    1. تحاول القراءة من Streamlit Secrets (عند الرفع على السيرفر).
    2. تحاول القراءة من ملف secrets.json (عند العمل على جهازك).
    """
    creds = None
    
    # المحاولة الأولى: السحابة (Streamlit Cloud)
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    
    # المحاولة الثانية: الملف المحلي (Local)
    elif os.path.exists("secrets.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name("secrets.json", SCOPE)
    
    else:
        st.error("❌ خطأ في الاتصال: لم يتم العثور على مفاتيح الدخول (Secrets)!")
        st.stop()
    
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
        st.error(f"❌ لم يتم العثور على مجلد '{folder_name}' في الدرايف! تأكد من مشاركته مع الإيميل الخدمي.")
        st.stop()
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
    # محاولة فتح الشيت
    try:
        sheet = gc.open(SHEET_NAME).sheet1
    except gspread.SpreadsheetNotFound:
        st.error(f"❌ لم يتم العثور على ملف Google Sheet باسم '{SHEET_NAME}'. تأكد من الاسم والمشاركة.")
        st.stop()
        
    folder_id = find_drive_folder_id(drive_service, DRIVE_FOLDER_NAME)
    st.toast("✅ Connected to Google Services") # رسالة صغيرة تختفي تلقائياً
    
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
    # ملاحظة: يتم حساب الكود بناء على عدد الصفوف الموجودة فعلياً
    try:
        existing_data = sheet.get_all_values()
        count =
