import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from openai import OpenAI
import requests
import base64
import json
from datetime import date

# ========================
# CONFIG
# ========================
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
REPO = st.secrets["GITHUB_REPO"]
CSV_PATH = st.secrets["CSV_PATH"]

API_URL = f"https://api.github.com/repos/{REPO}/contents/{CSV_PATH}"

# ========================
# PAGE
# ========================
st.set_page_config(page_title="Telemedicine", layout="wide")
st.title("🏥 ระบบนัดหมายแพทย์ทางไกล สถานพยาบาล KU KPS")

# ========================
# FUNCTIONS
# ========================
def calculate_age(dob):
    today = datetime.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

def generate_slots():
    slots = []
    start_date = datetime.today()
    for i in range(30):
        day = start_date + timedelta(days=i)
        for hour in range(9, 17):
            slots.append(f"{day.strftime('%Y-%m-%d')} {hour}:00")
    return slots

# ===== GitHub CSV =====
def get_csv_from_github():
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(API_URL, headers=headers)

    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"]).decode("utf-8")
        df = pd.read_csv(pd.io.common.StringIO(content))
        sha = r.json()["sha"]
        return df, sha
    else:
        # file not exist → create new
        df = pd.DataFrame(columns=[
            "citizen_id","dob","age","gender","province",
            "postal_code","symptoms","slot","created_at"
        ])
        return df, None

def push_csv_to_github(df, sha=None):
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    csv_string = df.to_csv(index=False)
    encoded = base64.b64encode(csv_string.encode()).decode()

    data = {
        "message": "update appointments",
        "content": encoded
    }

    if sha:
        data["sha"] = sha

    requests.put(API_URL, headers=headers, data=json.dumps(data))

# ========================
# INPUT
# ========================
st.header("📋 ข้อมูลนักศึกษา")

col1, col2 = st.columns(2)

with col1:
    citizen_id = st.text_input("เลขบัตรประชาชน")
    

    # จำกัดช่วงวันเกิด
    min_dob = date(1980, 1, 1)
    max_dob = date(2015, 12, 31)

    dob = st.date_input(
        "วันเดือนปีเกิด (dd/mm/yyyy)",
        min_value=min_dob,
        max_value=max_dob,
        format="DD/MM/YYYY"  # 👈 display format
    )
    gender = st.selectbox("เพศ", ["ชาย","หญิง","อื่นๆ"])

with col2:
    province = st.text_input("จังหวัด")
    postal_code = st.text_input("รหัสไปรษณีย์")

age = calculate_age(dob) if dob else None
if age:
    st.success(f"อายุ: {age} ปี")

# ========================
# SYMPTOMS
# ========================
st.header("🩺 อาการ")
symptoms = st.text_area("อธิบายอาการ")

# ========================
# AI TRIAGE
# ========================
def ai_triage(symptoms, age):
    prompt = f"""
    คุณเป็นแพทย์คัดกรอง

    อายุ: {age}
    อาการ: {symptoms}

    ตอบ JSON:
    {{
        "level": "RED/YELLOW/GREEN",
        "advice": "คำแนะนำ"
    }}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return response.choices[0].message.content

if "triage" not in st.session_state:
    st.session_state.triage = None

if st.button("🔍 ประเมิน"):
    result = ai_triage(symptoms, age)
    st.code(result)

    if "RED" in result:
        st.error("🚨 โปรดติดต่อสถานพยาบาลใกล้บ้าน หรือโทร 1669 ด่วน")
        st.session_state.triage = "RED"

    elif "GREEN" in result:
        st.success("ดูแลตนเองได้")
        st.session_state.triage = "GREEN"

    else:
        st.warning("สามารถนัด Telemedicine ได้")
        st.session_state.triage = "YELLOW"

# ========================
# BOOKING
# ========================
if st.session_state.triage == "YELLOW":

    df, sha = get_csv_from_github()

    slots = generate_slots()

    if "slot" in df.columns:
        booked_slots = df["slot"].dropna().tolist()
    else:
        booked_slots = []

    available_slots = [s for s in slots if s not in booked_slots]

    selected_slot = st.selectbox("เลือกเวลา", available_slots)

    if st.button("✅ ยืนยันนัด"):
        new_row = {
            "citizen_id": citizen_id,
            "dob": dob.strftime("%d/%m/%Y") if dob else None,
            "age": age,
            "gender": gender,
            "province": province,
            "postal_code": postal_code,
            "symptoms": symptoms,
            "slot": selected_slot,
            "created_at": datetime.utcnow()
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        headers = {"Authorization": f"token {GITHUB_TOKEN}"}

        csv_string = df.to_csv(index=False)
        encoded = base64.b64encode(csv_string.encode()).decode()

        data = {
            "message": "update appointments",
            "content": encoded
        }

        if sha:
            data["sha"] = sha

        response = requests.put(API_URL, headers=headers, data=json.dumps(data))

        if response.status_code in [200, 201]:
            st.success(f"นัดสำเร็จ: {selected_slot}")
        else:
            st.error(f"GitHub error: {response.text}")

# ========================
# ADMIN VIEW
# ========================
st.header("📊 นัดทั้งหมด")

df, _ = get_csv_from_github()
st.dataframe(df)
