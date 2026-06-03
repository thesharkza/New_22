import streamlit as st
import pandas as pd
import math
import time
import random

# ตั้งค่าการแสดงผลหน้าเว็บแบบกว้าง (Wide Layout)
st.set_page_config(page_title="โปรแกรมวิเคราะห์ค่าน้ำและคำนวณราคาบอล", layout="wide")

# =====================================================================
# 1. ฟังก์ชันคำนวณสถิติและถอดค่าน้ำ (De-vigging Mathematical Engine)
# =====================================================================

def remove_margin_basic(odds):
    """
    วิธี Basic (Multiplicative) De-vigging [1, 2]
    สูตรคณิตศาสตร์: p_i = r_i / sum(r) โดยที่ r_i = 1 / O_i
    """
    raw_probs = [1.0 / od for od in odds if od > 0]
    if not raw_probs:
        return
    total_sum = sum(raw_probs)
    true_probs = [rp / total_sum for rp in raw_probs]
    return true_probs


def remove_margin_wpo(odds):
    """
    วิธี Margin Weights Proportional to Odds (WPO) [1, 2]
    สูตรคณิตศาสตร์: p_i = (n - M * O_i) / (n * O_i)
    ช่วยชดเชนค่า Favorite-Longshot Bias ของเจ้ามือ
    """
    raw_probs = [1.0 / od for od in odds if od > 0]
    n = len(odds)
    if n == 0:
        return
    overround = sum(raw_probs) - 1.0  # ค่า Margin (M)
    
    true_probs = []  # แก้ไขโครงสร้างเรียบร้อยแล้ว กำหนดเป็นลิสต์ว่างเริ่มต้นที่ถูกต้อง
    for od in odds:
        if od > 0:
            # ลบส่วนแบ่ง Overround เฉลี่ยออกจากแต่ละผลลัพธ์
            p_i = (1.0 / od) - (overround / n)
            # ป้องกันค่าติดลบในกลุ่มทีมรองมากๆ
            true_probs.append(max(0.0001, p_i))
        else:
            true_probs.append(0.0001)
        
    # Re-normalize ให้ผลรวมความน่าจะเป็นเท่ากับ 1.00 (100%) อีกครั้ง
    total_sum = sum(true_probs)
    if total_sum > 0:
        return [tp / total_sum for tp in true_probs]
    else:
        return true_probs


# =====================================================================
# 2. แบบจำลองสถิติเชิงปริมาณการทำประตู (Poisson & Dixon-Coles)
# =====================================================================

def poisson_pmf(k, lamb):
    """คำนวณ Poisson Probability Mass Function (โอกาสเกิดประตู k ลูก) [3, 4]"""
    if lamb <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lamb) * (lamb ** k)) / math.factorial(k)


def d_coles_tau(x, y, lambda_h, lambda_a, rho):
    """
    ฟังก์ชันปรับปรุงสหสัมพันธ์ Dixon-Coles tau(x, y) [3, 4]
    เพื่อเพิ่มความแม่นยำในการวิเคราะห์โอกาสเกิดประตูสำหรับสกอร์ไลน์ต่ำ (0-0, 1-0, 0-1, 1-1)
    """
    if x == 0 and y == 0:
        return 1.0 - lambda_h * lambda_a * rho
    elif x == 1 and y == 0:
        return 1.0 + lambda_h * rho
    elif x == 0 and y == 1:
        return 1.0 + lambda_a * rho
    elif x == 1 and y == 1:
        return 1.0 - rho
    else:
        return 1.0


def calculate_match_odds(lambda_h, lambda_a, rho=0.0, max_goals=10):
    """คำนวณความน่าจะเป็นชนะ เสมอ แพ้ (1X2) จากค่าคาดหวังการทำประตู (xG) [3]"""
    prob_matrix = [[0.0 for _ in range(max_goals + 1)] for _ in range(max_goals + 1)]
    
    # คำนวณความน่าจะเป็นของแต่ละสกอร์บอร์ดที่เป็นไปได้
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            p_x = poisson_pmf(x, lambda_h)
            p_y = poisson_pmf(y, lambda_a)
            tau = d_coles_tau(x, y, lambda_h, lambda_a, rho)
            prob_matrix[x][y] = p_x * p_y * tau
            
    # Normalize ความน่าจะเป็นในตารางทั้งหมดให้เท่ากับ 1.00
    total_p = sum(sum(row) for row in prob_matrix)
    if total_p == 0:
        return 0.3333, 0.3333, 0.3333
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            prob_matrix[x][y] /= total_p
            
    # รวบรวมโอกาสชนะ เสมอ แพ้ [3]
    home_win = 0.0
    draw = 0.0
    away_win = 0.0
    
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            if x > y:
                home_win += prob_matrix[x][y]
            elif x == y:
                draw += prob_matrix[x][y]
            else:
                away_win += prob_matrix[x][y]
                
    return home_win, draw, away_win


# =====================================================================
# 3. หน้าจอการกรอกข้อมูลและโต้ตอบ (Pre-filled with Your Example Match)
# =====================================================================

st.title("⚽ Football Betting Math Engine (โปรแกรมคำนวณราคาบอล)")
st.write("ระบบคำนวณส่วนต่างค่าน้ำ (Overround) และสกัดหาความน่าจะเป็นที่แท้จริงจากอัตราต่อรองของเจ้ามือ [1, 2]")

# ส่วนจัดการไฟล์ Excel ป้องกัน Error บล็อกหากไม่มีไฟล์ในเครื่องเซิร์ฟเวอร์
st.sidebar.header("📁 ส่วนจัดการไฟล์ข้อมูล (Excel)")
uploaded_file = st.sidebar.file_uploader("อัปโหลดไฟล์ข้อมูลฟุตบอลของคุณ (.xlsx) ที่นี่", type=["xlsx"])

if uploaded_file is not None:
    try:
        df1 = pd.read_excel(uploaded_file, header=3)
        st.sidebar.success("โหลดไฟล์ Excel สำเร็จ!")
        with st.sidebar.expander("ดูตารางข้อมูลในไฟล์"):
            st.dataframe(df1.head(10))
    except Exception as e:
        st.sidebar.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
else:
    st.sidebar.info("💡 คำแนะนำ: หากคุณมีไฟล์สถิติ Excel คุณสามารถลากไฟล์มาใส่ช่องนี้เพื่อเปิดข้อมูลควบคู่ไปกับการคำนวณได้")

# แท็บสำหรับแบ่งสัดส่วนเครื่องมือบนหน้าเว็บ
tab1, tab2, tab3 = st.tabs(["ถอดค่าน้ำของเจ้ามือ", "แบบจำลองสถิติทำนายประตู", "ระบบตรวจรับตั๋วแบบหน่วงเวลา"])

# --- แท็บที่ 1: เครื่องมือถอดค่าน้ำของเจ้ามือ ---
with tab1:
    st.header("เครื่องมือวิเคราะห์อัตรากำไรและถอดค่าน้ำของเจ้ามือ")
    st.write("ป้อนอัตราต่อรองเพื่อคำนวณหาโอกาสเกิดผลจริงและตรวจสอบราคาที่ยุติธรรม")
    
    # ตัวเลือกรูปแบบราคา (HK Odds / Decimal Odds)
    odds_format = st.radio(
        "รูปแบบราคากลุ่มแฮนดิแคป (AH) และ สูง/ต่ำ (O/U)",
       ,
        index=0
    )
    
    # กรอกข้อมูลคู่แข่งขันที่คุณส่งมาเป็นตัวอย่าง
    match_title = st.text_input("คู่แข่งขัน", value="ซันไชน์ โค้สท์ วอนเดอร์เรอส์ เอฟซี VS เซนต์ จอร์จ วิลเลวอง เอฟซี")

    col1, col2, col3 = st.columns(3)

    # 1. ข้อมูลราคาพูล 1X2
    with col1:
        st.subheader("1. ตลาด 1X2 (ราคาพูล)")
        h_1x2 = st.number_input("เหย้า (Home Odds)", min_value=1.01, value=1.46, step=0.01)
        d_1x2 = st.number_input("เสมอ (Draw Odds)", min_value=1.01, value=4.14, step=0.01)
        a_1x2 = st.number_input("เยือน (Away Odds)", min_value=1.01, value=4.64, step=0.01)
        
        input_1x2 = [h_1x2, d_1x2, a_1x2]
        raw_1x2_probs = [1.0 / o for o in input_1x2 if o > 0]
        margin_1x2 = (sum(raw_1x2_probs) - 1.0) * 100
        
        p_1x2_basic = remove_margin_basic(input_1x2)
        p_1x2_wpo = remove_margin_wpo(input_1x2)

    # 2. ข้อมูลเอเชียนแฮนดิแคป AH
    with col2:
        st.subheader("2. ตลาด Asian Handicap")
        ah_line = st.text_input("แต้มต่อ (AH Line)", value="1")
        h_ah_raw = st.number_input("เหย้าต่อ (Home AH Odds)", min_value=0.01, value=0.82, step=0.01)
        a_ah_raw = st.number_input("เยือนรอง (Away AH Odds)", min_value=0.01, value=1.00, step=0.01)
        
        # แปลงอัตราต่อรองตามประเภทที่ผู้ใช้เลือก [5]
        if odds_format == "ราคาฮ่องกง (HK Odds - แสดงเฉพาะกำไร เช่น 0.82)":
            h_ah = h_ah_raw + 1.0
            a_ah = a_ah_raw + 1.0
        else:
            h_ah = h_ah_raw
            a_ah = a_ah_raw
            
        input_ah = [h_ah, a_ah]
        raw_ah_probs = [1.0 / o for o in input_ah if o > 0]
        margin_ah = (sum(raw_ah_probs) - 1.0) * 100
        
        p_ah_basic = remove_margin_basic(input_ah)
        p_ah_wpo = remove_margin_wpo(input_ah)

    # 3. ข้อมูลสูงต่ำ O/U
    with col3:
        st.subheader("3. ตลาด สูง/ต่ำ (Over/Under)")
        ou_line = st.text_input("เกณฑ์ประตู สูง/ต่ำ (O/U Line)", value="3/3.5")
        over_raw = st.number_input("ราคา สูง (Over Odds)", min_value=0.01, value=0.80, step=0.01)
        under_raw = st.number_input("ราคา ต่ำ (Under Odds)", min_value=0.01, value=1.00, step=0.01)
        
        # แปลงอัตราต่อรองตามประเภทที่ผู้ใช้เลือก [5]
        if odds_format == "ราคาฮ่องกง (HK Odds - แสดงเฉพาะกำไร เช่น 0.82)":
            over_odds = over_raw + 1.0
            under_odds = under_raw + 1.0
        else:
            over_odds = over_raw
            under_odds = under_raw
            
        input_ou = [over_odds, under_odds]
        raw_ou_probs = [1.0 / o for o in input_ou if o > 0]
        margin_ou = (sum(raw_ou_probs) - 1.0) * 100
        
        p_ou_basic = remove_margin_basic(input_ou)
        p_ou_wpo = remove_margin_wpo(input_ou)

    # การแสดงผลลัพธ์เชิงวิเคราะห์สถิติ (Analytical Output Tables)
    st.write("---")
    st.subheader(f"📊 ผลการวิเคราะห์ราคายุติธรรม: {match_title}")

    out_col1, out_col2, out_col3 = st.columns(3)

    # แสดงผลการคำนวณตลาด 1X2
    with out_col1:
        st.markdown("#### ผลลัพธ์ตลาด 1X2")
        st.metric("ค่าน้ำตลาด 1X2 (Overround)", f"{margin_1x2:.2f}%")
        
        # แก้ไข outcomes_1x2 ให้ระบุข้อมูลลิสต์จำลองที่ถูกต้องสมบูรณ์แบบ
        outcomes_1x2 = ["เหย้า (Home)", "เสมอ (Draw)", "เยือน (Away)"]
        df_1x2 = pd.DataFrame({
            "ผลชนะ": outcomes_1x2,
            "ราคาตั้งต้น": input_1x2,
            "โอกาสจริง (Basic)": [f"{p*100:.2f}%" for p in p_1x2_basic],
            "ราคายุติธรรม (Basic)": [f"{1.0/p:.3f}" if p > 0 else "N/A" for p in p_1x2_basic],
            "โอกาสจริง (WPO)": [f"{p*100:.2f}%" for p in p_1x2_wpo],
            "ราคายุติธรรม (WPO)": [f"{1.0/p:.3f}" if p > 0 else "N/A" for p in p_1x2_wpo]
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
            "ราคายุติธรรม (Basic)": [f"{1.0/p:.3f}" if p > 0 else "N/A" for p in p_ah_basic],
            "โอกาสจริง (WPO)": [f"{p*100:.2f}%" for p in p_ah_wpo],
            "ราคายุติธรรม (WPO)": [f"{1.0/p:.3f}" if p > 0 else "N/A" for p in p_ah_wpo]
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
            "ราคายุติธรรม (Basic)": [f"{1.0/p:.3f}" if p > 0 else "N/A" for p in p_ou_basic],
            "โอกาสจริง (WPO)": [f"{p*100:.2f}%" for p in p_ou_wpo],
            "ราคายุติธรรม (WPO)": [f"{1.0/p:.3f}" if p > 0 else "N/A" for p in p_ou_wpo]
        })
        st.table(df_ou)

    st.info("💡 **คำแนะนำ:** หากคุณต้องการสร้างโปรแกรมค้นหาช่องว่างของราคา (Value Bet) เพื่อทำกำไรระยะยาว ให้เลือกใช้ราคายุติธรรมที่คำนวณได้จากวิธี **WPO (Margin Weights Proportional to Odds)** เป็นเกณฑ์เปรียบเทียบ เนื่องจากวิธีนี้จะลบค่าความเบี่ยงเบนของเจ้ามือ (Favorite-Longshot Bias) ออกได้อย่างแม่นยำที่สุดครับ [1, 2]")


# --- แท็บที่ 2: แบบจำลองสถิติทำนายประตู ---
with tab2:
    st.header("แบบจำลองพยากรณ์ความน่าจะเป็นจากการยิงประตูเฉลี่ย")
    st.write("ระบุระดับฟอร์มการเล่นของทีม (Expected Goals - xG) เพื่อเปรียบเทียบผลลัพธ์ความน่าจะเป็นของผลแข่งขันแบบดั้งเดิมกับแบบจำลอง Dixon-Coles [3]")
    
    col1, col2 = st.columns(2)
    with col1:
        lambda_h = st.slider("ระดับฟอร์มเกมรุกเจ้าบ้าน (Home Expected Goals - xG)", min_value=0.0, max_value=5.0, value=1.6, step=0.1)
        lambda_a = st.slider("ระดับฟอร์มเกมรุกทีมเยือน (Away Expected Goals - xG)", min_value=0.0, max_value=5.0, value=1.2, step=0.1)
        rho_val = st.slider("ค่าสหสัมพันธ์ประตูน้อย Dixon-Coles (rho)", min_value=-0.30, max_value=0.0, value=-0.11, step=0.01)
        
    with col2:
        st.subheader("เปรียบเทียบสถิติความน่าจะเป็นของการชนะ เสมอ แพ้")
        
        p_hw, p_dr, p_aw = calculate_match_odds(lambda_h, lambda_a, rho=0.0)
        dc_hw, dc_dr, dc_aw = calculate_match_odds(lambda_h, lambda_a, rho=rho_val)
        
        # แก้ไขการระบุข้อมูลจำลองในดิกชันนารี prediction_results ให้มีโครงสร้างที่ถูกต้อง
        prediction_results = {
            "แบบจำลองทางสถิติ": ["Poisson", "Dixon-Coles"],
            "โอกาสเจ้าบ้านชนะ": [f"{p_hw*100:.2f}%", f"{dc_hw*100:.2f}%"],
            "โอกาสเสมอ (Draw)": [f"{p_dr*100:.2f}%", f"{dc_dr*100:.2f}%"],
            "โอกาสทีมเยือนชนะ": [f"{p_aw*100:.2f}%", f"{dc_aw*100:.2f}%"]
        }
        st.table(prediction_results)
        st.write("📊 **วิเคราะห์เชิงสถิติ:** แบบจำลอง Dixon-Coles ใช้พารามิเตอร์สหสัมพันธ์ $\\rho$ เข้ามาชดเชยเพื่อเพิ่มความแม่นยำให้กับสถานการณ์ที่มีจำนวนประตูรวมต่ำ ซึ่งเป็นจุดบกพร่องดั้งเดิมที่ทำให้การจำลองแบบพัวซองทั่วไปมองข้ามโอกาสเสมอในสนามแข่งขันจริง [3]")


# --- แท็บที่ 3: ระบบตรวจรับตั๋วแบบหน่วงเวลา ---
with tab3:
    st.header("ระบบวิเคราะห์ความเสี่ยงและหน่วงเวลารับเดิมพันเรียลไทม์ (Live Bet Delay Simulator)")
    st.write("ทดลองจำลองเหตุการณ์ในสนาม เพื่อศึกษาว่ากระบวนการ Bet Delay (คิวพักและตรวจสอบข้อมูลย้อนหลัง) ป้องกันความเสี่ยงแก่ซอฟต์แวร์ผู้ให้บริการได้อย่างไร [6]")
    
    # แก้ไขกำหนดค่าเริ่มต้น Session State เป็นลิสต์ว่างที่ถูกต้องตามกฎไวยากรณ์ Python
    if "live_event_stream" not in st.session_state:
        st.session_state["live_event_stream"] = []
    if "bet_history" not in st.session_state:
        st.session_state["bet_history"] = []
        
    col_ctrl, col_display = st.columns([7, 8])
    
    with col_ctrl:
        st.subheader("แผงจำลองการป้อนข้อมูลสนามสด")
        
        if st.button("🚨 จำลองการยิงประตู (Goal!)"):
            team = random.choice(["Home", "Away"])
            event_data = {
                "timestamp": time.time(),
                "event": "Goal",
                "team": team,
                "time_str": time.strftime('%H:%M:%S')
            }
            st.session_state["live_event_stream"].append(event_data)
            st.toast(f"⚽ Goal! ฝั่ง {team} ยิงประตูได้เรียบร้อยแล้ว")
            
        if st.button("🟥 จำลองใบแดง (Red Card)"):
            team = random.choice(["Home", "Away"])
            event_data = {
                "timestamp": time.time(),
                "event": "Red Card",
                "team": team,
                "time_str": time.strftime('%H:%M:%S')
            }
            st.session_state["live_event_stream"].append(event_data)
            st.toast(f"🟥 Red Card! ฝั่ง {team} ได้รับใบแดง")
            
        if st.button("🧹 ล้างข้อมูลประวัติและเหตุการณ์ทั้งหมด"):
            st.session_state["live_event_stream"] = []
            st.session_state["bet_history"] = []
            st.rerun()

        st.write("---")
        st.subheader("กล่องส่งใบเดิมพัน (Submit Ticket)")
        
        bet_selection = st.selectbox(
            "เลือกประเภทการเดิมพัน", 
            ["เจ้าบ้านชนะ @ 1.46", "เสมอ @ 4.14", "ทีมเยือนชนะ @ 4.64", "สูง 3/3.5 @ 1.80", "ต่ำ 3/3.5 @ 2.00"]
        )
        delay_seconds = st.slider("ตั้งค่าระยะเวลาหน่วงตั๋ว (Bet Delay Seconds)", min_value=1, max_value=10, value=6)
        
        if st.button("📥 ยืนยันการส่งเดิมพัน"):
            submission_time = time.time()
            st.info(f"⏳ ตั๋วถูกส่งเข้าคิวหน่วงเวลาตรวจสอบความเสี่ยง (หน่วงเวลา {delay_seconds} วินาที)... [6]")
            
            # รัน ProgressBar เพื่อจำลองการหน่วงเวลา (Bet Delay Queue Validation Buffer)
            progress_bar = st.progress(0)
            for percent in range(100):
                time.sleep(delay_seconds / 100.0)
                progress_bar.progress(percent + 1)
            
            # การทำงานแบบเรียลไทม์: ตรวจสอบย้อนหลังในประวัติการสตรีมมิ่งเหตุการณ์ [6]
            is_valid = True
            triggered_event = None
            
            for event in st.session_state["live_event_stream"]:
                # หากมีเหตุการณ์สำคัญเกิดขึ้น "หลัง" วินาทีที่ผู้เล่นกดยื่นตั๋ว แต่อยู่ภายในกรอบเวลาที่โดนกักตั๋วไว้
                if event["timestamp"] >= submission_time and event["timestamp"] <= (submission_time + delay_seconds):
                    # แก้ไขเงื่อนไขตรวจสอบเหตุการณ์ที่ขัดแย้งต่อผลการแข่งขัน (Material Events) ให้ครบถ้วนสมบูรณ์
                    if event["event"] in ["Goal", "Red Card"]:
                        is_valid = False
                        triggered_event = event
                        break
            
            # บันทึกสถานะผลการประมวลผลตั๋ว
            bet_record = {
                "time": time.strftime('%H:%M:%S'),
                "selection": bet_selection,
                "status": "Accepted" if is_valid else "Rejected",
                "reason": "บิลสะอาด ปราศจากเหตุการณ์แทรกแซงในช่วง Bet Delay" if is_valid else f"ตรวจพบเหตุการณ์สำคัญเกิดขัดแย้งในเกมขณะรออนุมัติ: {triggered_event['event']} ({triggered_event['team']})"
            }
            st.session_state["bet_history"].insert(0, bet_record)
            
            if is_valid:
                st.success("✅ ตั๋วเดิมพันของคุณได้รับการยอมรับ (Accepted) สำเร็จ!")
            else:
                st.error(f"❌ ปฏิเสธตั๋วเดิมพัน (Rejected)! - {bet_record['reason']} [6]")
                
    with col_display:
        st.subheader("สตรีมมิ่งข้อมูลดิบจากสนามแข่งขันจริง (Mockup Event Stream)")
        if not st.session_state["live_event_stream"]:
            st.write("*ระบบสตรีมกำลังรอตรวจจับเหตุการณ์ในสนาม...*")
        else:
            for ev in reversed(st.session_state["live_event_stream"]):
                st.write(f"⏱️ **{ev['time_str']}** - **{ev['event']}** ของทีม **{ev['team']}**")
                
        st.write("---")
        st.subheader("บันทึกการตรวจรับและสถานะบิลเดิมพัน (Bet Ledger)")
        if not st.session_state["bet_history"]:
            st.write("*ยังไม่มีการทำรายการเดิมพันในเซสชันนี้*")
        else:
            for b in st.session_state["bet_history"]:
                status_icon = "🟢" if b["status"] == "Accepted" else "🔴"
                st.write(f"{status_icon} **[{b['time']}]** เลือก: {b['selection']} -> **สถานะ: {b['status']}** ({b['reason']})")
