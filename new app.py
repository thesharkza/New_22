import streamlit as st
import math
import time
import random

# ตั้งค่าการแสดงผลแบบกว้าง (Wide Layout) บนหน้าจอ Streamlit
st.set_page_config(page_title="โปรแกรมคำนวณราคาบอลและจำลองระบบ Live Bet", layout="wide")

# =====================================================================
# 1. ฟังก์ชันคำนวณคณิตศาสตร์และถอดค่าน้ำ (De-vigging Engine)
# =====================================================================

def remove_margin_basic(odds):
    """
    วิธี Basic (Multiplicative) De-vigging [3]
    สูตรคณิตศาสตร์: p_i = r_i / sum(r) โดยที่ r_i = 1 / O_i [3]
    """
    raw_probs = [1.0 / od for od in odds]
    total_sum = sum(raw_probs)
    true_probs = [rp / total_sum for rp in raw_probs]
    return true_probs


def remove_margin_wpo(odds):
    """
    วิธี Margin Weights Proportional to Odds (WPO) [3]
    ชดเชยค่าอคติโปรด/รอง (Favorite-Longshot Bias) ในระบบอัตราต่อรองของเจ้ามือ
    สูตรคณิตศาสตร์: p_i = (n - M * O_i) / (n * O_i) [3]
    """
    raw_probs = [1.0 / od for od in odds]
    n = len(odds)
    overround = sum(raw_probs) - 1.0  # ค่า M (Margin/Overround) [3]
    
    true_probs =  # กำหนดลิสต์ว่างเริ่มต้นที่ถูกต้องตามไวยากรณ์เพื่อรอรับข้อมูล
    for od in odds:
        # ลบส่วนแบ่ง Overround เฉลี่ยออกจากแต่ละฝั่ง
        p_i = (1.0 / od) - (overround / n)
        # ป้องกันไม่ให้โอกาสชนะติดลบกรณีที่เป็นฝั่งทีมรองมากๆ
        true_probs.append(max(0.0001, p_i))
        
    # ปรับสมดุลความน่าจะเป็นรวมให้เท่ากับ 1.00 (Normalization)
    total_sum = sum(true_probs)
    return [tp / total_sum for tp in true_probs]


# =====================================================================
# 2. แบบจำลองสถิติเชิงปริมาณการทำประตู (Poisson & Dixon-Coles)
# =====================================================================

def poisson_pmf(k, lamb):
    """คำนวณ Poisson Probability Mass Function (โอกาสเกิดประตู k ลูก) [4, 6]"""
    if lamb <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lamb) * (lamb ** k)) / math.factorial(k)


def d_coles_tau(x, y, lambda_h, lambda_a, rho):
    """
    ฟังก์ชันปรับปรุงสหสัมพันธ์ Dixon-Coles tau(x, y) [4, 6]
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
    """คำนวณความน่าจะเป็นชนะ เสมอ แพ้ (1X2) จากค่าคาดหวังการทำประตู (xG) [4]"""
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
            
    # รวบรวมโอกาสชนะ เสมอ แพ้ [4]
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
# 3. ส่วนควบคุมโครงสร้างหน้าจอผู้ใช้ (Streamlit UI)
# =====================================================================

st.title("⚽ Football Betting Math Engine & Live Delay Simulator")
st.write("แอปพลิเคชันทดสอบระบบคำนวณราคาบอลและกลไกคัดกรองความปลอดภัยของตั๋วแบบเรียลไทม์")

# สร้างแท็บสำหรับแบ่งสัดส่วนเครื่องมือ
tab1, tab2, tab3 = st.tabs()

# --- แท็บที่ 1: เครื่องมือถอดค่าน้ำของเจ้ามือ ---
with tab1:
    st.header("เครื่องมือวิเคราะห์อัตรากำไรและถอดค่าน้ำของเจ้ามือ")
    st.write("ป้อนอัตราต่อรองพูล (1X2) จากหน้าเว็บของเจ้ามือเพื่อคำนวณหาโอกาสเกิดผลจริงและตรวจสอบราคาที่ยุติธรรม")
    
    col1, col2 = st.columns(2)
    with col1:
        h_odds = st.number_input("ราคาเจ้าบ้านชนะ (Home Odds)", min_value=1.01, value=2.32, step=0.01)
        d_odds = st.number_input("ราคาเสมอ (Draw Odds)", min_value=1.01, value=3.21, step=0.01)
        a_odds = st.number_input("ราคาทีมเยือนชนะ (Away Odds)", min_value=1.01, value=3.59, step=0.01)
        input_odds = [h_odds, d_odds, a_odds]
        
    with col2:
        # คำนวณ Overround สะสม
        raw_probs = [1.0 / o for o in input_odds]
        overround_percent = (sum(raw_probs) - 1.0) * 100
        st.metric("ค่า Overround ของเจ้ามือ (ค่าน้ำ)", f"{overround_percent:.2f}%")
        
        p_basic = remove_margin_basic(input_odds)
        p_wpo = remove_margin_wpo(input_odds)
        
        st.subheader("ผลลัพธ์การแปลงความน่าจะเป็นหลังหักค่าน้ำออก")
        
        # ปรับแก้ข้อมูลตารางให้มีความสมบูรณ์ตามไวยากรณ์ Python
        table_data = {
            "ฝั่งผลชนะ":,
            "ราคาหน้าเว็บ": input_odds,
            "ความน่าจะเป็น (วิธี Basic)": [f"{p*100:.2f}%" for p in p_basic],
            "ราคายุติธรรม (วิธี Basic)": [f"{1.0/p:.3f}" for p in p_basic],
            "ความน่าจะเป็น (วิธี WPO)": [f"{p*100:.2f}%" for p in p_wpo],
            "ราคายุติธรรม (วิธี WPO)": [f"{1.0/p:.3f}" for p in p_wpo]
        }
        st.table(table_data)
        st.info("💡 หมายเหตุ: วิธี WPO (Margin Weights Proportional to Odds) ได้รับการวิเคราะห์ทางสถิติแล้วว่ามีความเฉียบคมสูงในการดึงค่าน้ำออกโดยอิงพฤติกรรมการกระจายอัตรากำไรที่ไม่เท่ากันตามน้ำหนักความน่าจะเป็นจริง [3]")

# --- แท็บที่ 2: แบบจำลองทำนายผลการแข่งขัน ---
with tab2:
    st.header("แบบจำลองพยากรณ์ความน่าจะเป็นจากการยิงประตูเฉลี่ย")
    st.write("ระบุระดับฟอร์มการเล่นของทีม (Expected Goals - xG) เพื่อเปรียบเทียบผลลัพธ์ความน่าจะเป็นของผลแข่งขันแบบดั้งเดิมกับแบบจำลอง Dixon-Coles [4]")
    
    col1, col2 = st.columns(2)
    with col1:
        lambda_h = st.slider("ระดับฟอร์มเกมรุกเจ้าบ้าน (Home Expected Goals - xG)", min_value=0.0, max_value=5.0, value=1.6, step=0.1)
        lambda_a = st.slider("ระดับฟอร์มเกมรุกทีมเยือน (Away Expected Goals - xG)", min_value=0.0, max_value=5.0, value=1.2, step=0.1)
        rho_val = st.slider("ค่าสหสัมพันธ์ประตูน้อย Dixon-Coles (rho)", min_value=-0.30, max_value=0.0, value=-0.11, step=0.01)
        
    with col2:
        st.subheader("เปรียบเทียบสถิติความน่าจะเป็นของการชนะ เสมอ แพ้")
        
        p_hw, p_dr, p_aw = calculate_match_odds(lambda_h, lambda_a, rho=0.0)
        dc_hw, dc_dr, dc_aw = calculate_match_odds(lambda_h, lambda_a, rho=rho_val)
        
        # ปรับแก้ข้อมูลตารางแบบจำลองสถิติให้สมบูรณ์
        prediction_results = {
            "แบบจำลองทางสถิติ":,
            "โอกาสเจ้าบ้านชนะ": [f"{p_hw*100:.2f}%", f"{dc_hw*100:.2f}%"],
            "โอกาสเสมอ (Draw)": [f"{p_dr*100:.2f}%", f"{dc_dr*100:.2f}%"],
            "โอกาสทีมเยือนชนะ": [f"{p_aw*100:.2f}%", f"{dc_aw*100:.2f}%"]
        }
        st.table(prediction_results)
        st.write("📊 **วิเคราะห์เชิงสถิติ:** แบบจำลอง Dixon-Coles ใช้พารามิเตอร์สหสัมพันธ์ในการเพิ่มหรือลดสัดส่วนของกลุ่มสกอร์ไลน์ต่ำ (เช่น 0-0 หรือ 1-1) ซึ่งเป็นจุดอ่อนหลักที่แบบจำลองพัวซองแบบดั้งเดิมมักประเมินความน่าจะเป็นต่ำกว่าความเป็นจริง [4, 6]")

# --- แท็บที่ 3: ระบบจำลองการรับตั๋วแบบหน่วงเวลา (Live Bet Delay) ---
with tab3:
    st.header("ระบบวิเคราะห์ความเสี่ยงและหน่วงเวลารับเดิมพันเรียลไทม์ (Live Bet Delay Simulator)")
    st.write("ทดลองจำลองเหตุการณ์ในสนาม เพื่อศึกษาว่ากระบวนการ Bet Delay (คิวพักและตรวจสอบข้อมูลย้อนหลัง) ป้องกันความเสี่ยงแก่ซอฟต์แวร์ผู้ให้บริการได้อย่างไร [5]")
    
    # กำหนดสถานะตัวแปร Session State สำหรับ Streamlit
    if "live_event_stream" not in st.session_state:
        st.session_state["live_event_stream"] =  # แก้ไขกำหนดค่าเริ่มต้นเป็นลิสต์ว่างที่ถูกต้องตามกฎไวยากรณ์
    if "bet_history" not in st.session_state:
        st.session_state["bet_history"] =  # แก้ไขกำหนดค่าเริ่มต้นเป็นลิสต์ว่างที่ถูกต้องตามกฎไวยากรณ์
        
    col_ctrl, col_display = st.columns([1, 2])
    
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
            st.session_state["live_event_stream"] =
            st.session_state["bet_history"] =
            st.rerun()

        st.write("---")
        st.subheader("กล่องส่งใบเดิมพัน (Submit Ticket)")
        
        # แก้ไขอ็อพชันของ Selectbox ให้สมบูรณ์แบบ
        bet_selection = st.selectbox(
            "เลือกประเภทการเดิมพัน", 
           
        )
        delay_seconds = st.slider("ตั้งค่าระยะเวลาหน่วงตั๋ว (Bet Delay Seconds)", min_value=1, max_value=10, value=6)
        
        if st.button("📥 ยืนยันการส่งเดิมพัน"):
            submission_time = time.time()
            st.info(f"⏳ ตั๋วถูกส่งเข้าคิวหน่วงเวลาตรวจสอบความเสี่ยง (หน่วงเวลา {delay_seconds} วินาที)... [5]")
            
            # รัน ProgressBar เพื่อจำลองการหน่วงเวลา (Bet Delay Queue Validation Buffer)
            progress_bar = st.progress(0)
            for percent in range(100):
                time.sleep(delay_seconds / 100.0)
                progress_bar.progress(percent + 1)
            
            # การทำงานแบบเรียลไทม์: ตรวจสอบย้อนหลังในประวัติการสตรีมมิ่งเหตุการณ์ [5]
            is_valid = True
            triggered_event = None
            
            for event in st.session_state["live_event_stream"]:
                # หากมีเหตุการณ์สำคัญเกิดขึ้น "หลัง" วินาทีที่ผู้เล่นกดยื่นตั๋ว แต่อยู่ภายในกรอบเวลาที่โดนกักตั๋วไว้
                if event["timestamp"] >= submission_time and event["timestamp"] <= (submission_time + delay_seconds):
                    # แก้ไขเงื่อนไขตรวจสอบเหตุการณ์รุนแรงที่มีผลขัดแย้งต่ออัตราต่อรอง (Material Events) ให้สมบูรณ์แบบ
                    if event["event"] in:
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
                st.error(f"❌ ปฏิเสธตั๋วเดิมพัน (Rejected)! - {bet_record['reason']} [5]")
                
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
