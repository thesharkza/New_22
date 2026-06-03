import streamlit as st
import pandas as pd

# ตั้งค่าการแสดงผลหน้าเว็บ
st.set_page_config(page_title="โปรแกรมวิเคราะห์ค่าน้ำและราคายุติธรรม", layout="wide")

# =====================================================================
# 1. ฟังก์ชันคำนวณสถิติและถอดค่าน้ำ (De-vigging Mathematical Engine)
# =====================================================================

def remove_margin_basic(odds):
    """
    วิธี Basic (Multiplicative) De-vigging [2, 3]
    สูตรคณิตศาสตร์: p_i = r_i / sum(r) โดยที่ r_i = 1 / O_i
    """
    raw_probs = [1.0 / od for od in odds]
    total_sum = sum(raw_probs)
    true_probs = [rp / total_sum for rp in raw_probs]
    return true_probs


def remove_margin_wpo(odds):
    """
    วิธี Margin Weights Proportional to Odds (WPO) [2, 3]
    สูตรคณิตศาสตร์: p_i = (n - M * O_i) / (n * O_i)
    ช่วยชดเชยค่า Favorite-Longshot Bias ของเจ้ามือ
    """
    raw_probs = [1.0 / od for od in odds]
    n = len(odds)
    overround = sum(raw_probs) - 1.0  # ค่า Margin (M)
    
    true_probs =  # ตัวแปรลิสต์ว่างที่ระบุถูกต้องตามหลักไวยากรณ์
    for od in odds:
        # ลบส่วนแบ่ง Overround เฉลี่ยออกจากแต่ละผลลัพธ์
        p_i = (1.0 / od) - (overround / n)
        # ป้องกันค่าติดลบในกลุ่มทีมรองมากๆ
        true_probs.append(max(0.0001, p_i))
        
    # Re-normalize ให้ผลรวมเท่ากับ 1.00 อีกครั้ง
    total_sum = sum(true_probs)
    return [tp / total_sum for tp in total_sum if total_sum > 0 else true_probs]


# =====================================================================
# 2. หน้าจอการแสดงผลผู้ใช้งาน (Streamlit User Interface)
# =====================================================================

st.title("⚽ Football Betting Math Engine (ราคาพูล, เอเชียนแฮนดิแคป, สูง/ต่ำ)")
st.write("ระบบคำนวณส่วนต่างค่าน้ำ (Overround) และสกัดหาความน่าจะเป็นที่แท้จริงจากอัตราต่อรองของเจ้ามือ")

# แผงควบคุมรูปแบบราคาหลัก
st.sidebar.header("⚙️ การตั้งค่ารูปแบบราคา")
odds_format = st.sidebar.radio(
    "รูปแบบราคากลุ่ม AH และ O/U",
   
)

# กรอกข้อมูลคู่แข่งขัน
st.header("📋 ข้อมูลการแข่งขันยื่นคำขอ")
match_title = st.text_input("คู่แข่งขัน", value="ซันไชน์ โค้สท์ วอนเดอร์เรอส์ เอฟซี VS เซนต์ จอร์จ วิลเลวอง เอฟซี")

# จัดสรรคอลัมน์เพื่อรองรับการกรอกข้อมูลแยกตลาด 3 รูปแบบ
col1, col2, col3 = st.columns(3)

# 1. ข้อมูลราคาพูล 1X2
with col1:
    st.subheader("1. ตลาด 1X2 (ราคาพูล)")
    h_1x2 = st.number_input("เหย้า (Home Odds)", min_value=1.01, value=1.46, step=0.01)
    d_1x2 = st.number_input("เสมอ (Draw Odds)", min_value=1.01, value=4.14, step=0.01)
    a_1x2 = st.number_input("เยือน (Away Odds)", min_value=1.01, value=4.64, step=0.01)
    
    # คำนวณตลาด 1X2 [4, 3]
    input_1x2 = [h_1x2, d_1x2, a_1x2]
    raw_1x2_probs = [1.0 / o for o in input_1x2]
    margin_1x2 = (sum(raw_1x2_probs) - 1.0) * 100
    
    p_1x2_basic = remove_margin_basic(input_1x2)
    p_1x2_wpo = remove_margin_wpo(input_1x2)

# 2. ข้อมูลเอเชียนแฮนดิแคป AH
with col2:
    st.subheader("2. ตลาด Asian Handicap")
    ah_line = st.text_input("แต้มต่อ (AH Line)", value="1")
    h_ah_raw = st.number_input("เหย้าต่อ (Home AH Odds)", min_value=0.01, value=0.82, step=0.01)
    a_ah_raw = st.number_input("เยือนรอง (Away AH Odds)", min_value=0.01, value=1.00, step=0.01)
    
    # แปลงอัตราต่อรองตามประเภทที่ผู้ใช้เลือก [1]
    if odds_format == "ราคาฮ่องกง (HK Odds - แสดงเฉพาะกำไร เช่น 0.82)":
        h_ah = h_ah_raw + 1.0
        a_ah = a_ah_raw + 1.0
    else:
        h_ah = h_ah_raw
        a_ah = a_ah_raw
        
    # คำนวณตลาด AH [4, 3]
    input_ah = [h_ah, a_ah]
    raw_ah_probs = [1.0 / o for o in input_ah]
    margin_ah = (sum(raw_ah_probs) - 1.0) * 100
    
    p_ah_basic = remove_margin_basic(input_ah)
    p_ah_wpo = remove_margin_wpo(input_ah)

# 3. ข้อมูลสูงต่ำ O/U
with col3:
    st.subheader("3. ตลาด สูง/ต่ำ (Over/Under)")
    ou_line = st.text_input("เกณฑ์ประตู สูง/ต่ำ (O/U Line)", value="3/3.5")
    over_raw = st.number_input("ราคา สูง (Over Odds)", min_value=0.01, value=0.80, step=0.01)
    under_raw = st.number_input("ราคา ต่ำ (Under Odds)", min_value=0.01, value=1.00, step=0.01)
    
    # แปลงอัตราต่อรองตามประเภทที่ผู้ใช้เลือก [1]
    if odds_format == "ราคาฮ่องกง (HK Odds - แสดงเฉพาะกำไร เช่น 0.82)":
        over_odds = over_raw + 1.0
        under_odds = under_raw + 1.0
    else:
        over_odds = over_raw
        under_odds = under_raw
        
    # คำนวณตลาด O/U [4, 3]
    input_ou = [over_odds, under_odds]
    raw_ou_probs = [1.0 / o for o in input_ou]
    margin_ou = (sum(raw_ou_probs) - 1.0) * 100
    
    p_ou_basic = remove_margin_basic(input_ou)
    p_ou_wpo = remove_margin_wpo(input_ou)

# =====================================================================
# 3. การแสดงผลลัพธ์เชิงวิเคราะห์สถิติ (Analytical Output Tables)
# =====================================================================

st.write("---")
st.subheader(f"📊 ผลวิเคราะห์ราคายุติธรรม: {match_title}")

out_col1, out_col2, out_col3 = st.columns(3)

# แสดงผลการคำนวณตลาด 1X2
with out_col1:
    st.markdown("#### ผลลัพธ์ตลาด 1X2")
    st.metric("ค่าน้ำตลาด 1X2 (Overround)", f"{margin_1x2:.2f}%")
    
    outcomes_1x2 =
    df_1x2 = pd.DataFrame({
        "ผลชนะ": outcomes_1x2,
        "ราคาตั้งต้น": input_1x2,
        "โอกาสจริง (Basic)": [f"{p*100:.2f}%" for p in p_1x2_basic],
        "ราคายุติธรรม (Basic)": [f"{1.0/p:.3f}" for p in p_1x2_basic],
        "โอกาสจริง (WPO)": [f"{p*100:.2f}%" for p in p_1x2_wpo],
        "ราคายุติธรรม (WPO)": [f"{1.0/p:.3f}" for p in p_1x2_wpo]
    })
    st.table(df_1x2)

# แสดงผลการคำนวณตลาด AH
with out_col2:
    st.markdown(f"#### ผลลัพธ์ตลาด AH (ราคาแฮนดิแคป: {ah_line})")
    st.metric("ค่าน้ำตลาด AH (Overround)", f"{margin_ah:.2f}%")
    
    outcomes_ah = ["เหย้าต่อ (Home AH)", "เยือนรอง (Away AH)"]
    df_ah = pd.DataFrame({
        "ฝั่งแฮนดิแคป": outcomes_ah,
        "ราคาสูตรคำนวณ (Decimal)": input_ah,
        "โอกาสจริง (Basic)": [f"{p*100:.2f}%" for p in p_ah_basic],
        "ราคายุติธรรม (Basic)": [f"{1.0/p:.3f}" for p in p_ah_basic],
        "โอกาสจริง (WPO)": [f"{p*100:.2f}%" for p in p_ah_wpo],
        "ราคายุติธรรม (WPO)": [f"{1.0/p:.3f}" for p in p_ah_wpo]
    })
    st.table(df_ah)

# แสดงผลการคำนวณตลาด O/U
with out_col3:
    st.markdown(f"#### ผลลัพธ์ตลาด สูง/ต่ำ (เกณฑ์ประตู: {ou_line})")
    st.metric("ค่าน้ำตลาด สูง/ต่ำ (Overround)", f"{margin_ou:.2f}%")
    
    outcomes_ou = ["สูง (Over)", "ต่ำ (Under)"]
    df_ou = pd.DataFrame({
        "ฝั่งสกอร์รวม": outcomes_ou,
        "ราคาสูตรคำนวณ (Decimal)": input_ou,
        "โอกาสจริง (Basic)": [f"{p*100:.2f}%" for p in p_ou_basic],
        "ราคายุติธรรม (Basic)": [f"{1.0/p:.3f}" for p in p_ou_basic],
        "โอกาสจริง (WPO)": [f"{p*100:.2f}%" for p in p_ou_wpo],
        "ราคายุติธรรม (WPO)": [f"{1.0/p:.3f}" for p in p_ou_wpo]
    })
    st.table(df_ou)

st.info("💡 **คำแนะนำในการประมวลผลข้อมูล:** หากเป้าหมายคือการพัฒนาบอทหรือทำแบบจำลองคำนวณมูลค่าบวก (Value Bets) ให้ใช้ความน่าจะเป็นฝั่งวิธี **WPO (Margin Weights Proportional to Odds)** ไปเปรียบเทียบกับราคาตลาดพินนาเคิลหรือตลาดอื่นๆ เพื่อหาช่องว่างในการทำไรส่วนต่าง เนื่องจากวิธี WPO สามารถระบุค่าเบี่ยงเบนราคา (Favorite-Longshot Bias) ได้อย่างมีประสิทธิภาพสูงสุด [3, 5]")
