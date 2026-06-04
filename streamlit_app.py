import streamlit as st
import pandas as pd
import math
import time
import random
import re

# ตั้งค่าการแสดงผลหน้าเว็บแบบกว้าง (Wide Layout)
st.set_page_config(page_title="โปรแกรมวิเคราะห์ค่าน้ำและคำนวณราคาบอล", layout="wide")

# =====================================================================
# 1. ฟังก์ชันคำนวณสถิติและถอดค่าน้ำ (De-vigging Mathematical Engine)
# =====================================================================

def remove_margin_basic(odds):
    """
    วิธี Basic (Multiplicative) De-vigging
    สูตรคณิตศาสตร์: p_i = r_i / sum(r) โดยที่ r_i = 1 / O_i
    """
    raw_probs = [1.0 / od for od in odds if od > 0]
    if not raw_probs:
        return []  # คืนลิสต์ว่างแทน None เพื่อป้องกัน loop พัง
    total_sum = sum(raw_probs)
    true_probs = [rp / total_sum for rp in raw_probs]
    return true_probs


def remove_margin_wpo(odds):
    """
    วิธี Margin Weights Proportional to Odds (WPO)
    สูตรคณิตศาสตร์: p_i = (n - M * O_i) / (n * O_i)
    ช่วยชดเชยค่า Favorite-Longshot Bias ของเจ้ามือ
    """
    raw_probs = [1.0 / od for od in odds if od > 0]
    n = len(odds)
    if n == 0:
        return []  # คืนลิสต์ว่างแทน None เพื่อป้องกัน loop พัง
    overround = sum(raw_probs) - 1.0  # ค่า Margin (M)

    true_probs = []
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
# 1.5 ฟังก์ชันแยกข้อมูลดิบ (Raw Data Parser)
# =====================================================================

def parse_raw_match_data(text):
    """
    แยกข้อมูลดิบที่ผู้ใช้วางมา เป็นค่าสำหรับเติมในแต่ละช่อง
    รูปแบบที่รองรับ (เรียงบรรทัด):
        ทีมเหย้า VS ทีมเยือน      -> ชื่อคู่
        เหย้า 1.30                 -> 1X2 เหย้า
        เสมอ 4.77                  -> 1X2 เสมอ
        เยือน 7.00                 -> 1X2 เยือน
        เหย้า 0.90                 -> AH เหย้า (เหย้า ครั้งที่ 2)
        AH 1.5                     -> เส้นแต้มต่อ AH
        เยือน 0.94                 -> AH เยือน (เยือน ครั้งที่ 2)
        สูง 1.02                   -> Over
        สูง/ต่ำ 3                  -> เส้น O/U
        ต่ำ 0.80                   -> Under
    """
    lines = [ln.strip() for ln in text.strip().split("\n") if ln.strip()]
    parsed = {}
    if not lines:
        return parsed

    start = 0
    # บรรทัดแรกถ้ามีคำว่า vs/VS ถือเป็นชื่อคู่แข่งขัน
    if "vs" in lines[0].lower():
        parsed["match_title"] = lines[0]
        start = 1

    home_count = 0  # นับจำนวนครั้งที่เจอ "เหย้า" (ครั้งแรก=1X2, ครั้งสอง=AH)
    away_count = 0  # นับจำนวนครั้งที่เจอ "เยือน"

    for line in lines[start:]:
        # ดึงตัวเลขท้ายบรรทัด รองรับทศนิยมและรูปแบบเส้นครึ่ง เช่น 3/3.5
        m = re.search(r'(\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?)\s*$', line)
        if not m:
            continue
        value = m.group(1)
        label = line[:m.start()].strip().lower()

        if "เสมอ" in label:
            parsed["d_1x2"] = float(value)
        elif "ah" in label:
            parsed["ah_line"] = value           # เก็บเป็น string (อาจเป็น 1.5 / 0.5/1)
        elif "สูง/ต่ำ" in label:
            parsed["ou_line"] = value           # เก็บเป็น string (เช่น 3 หรือ 3/3.5)
        elif "สูง" in label:
            parsed["over_raw"] = float(value)
        elif "ต่ำ" in label:
            parsed["under_raw"] = float(value)
        elif "เหย้า" in label:
            if home_count == 0:
                parsed["h_1x2"] = float(value)
            else:
                parsed["h_ah_raw"] = float(value)
            home_count += 1
        elif "เยือน" in label:
            if away_count == 0:
                parsed["a_1x2"] = float(value)
            else:
                parsed["a_ah_raw"] = float(value)
            away_count += 1

    return parsed


def interpret_ah_line(line_str):
    """
    แปลความเส้นแต้มต่อ Asian Handicap ตามเครื่องหมาย
    - มี '-' นำหน้า  -> ทีมเยือนเป็นฝ่ายต่อ (Away favorite)
    - ไม่มี '-'      -> ทีมเหย้าเป็นฝ่ายต่อ (Home favorite)
    คืนค่า: (favorite, magnitude_str, description)
        favorite = "home" หรือ "away"
        magnitude_str = ค่าตัวเลขเส้น (ตัดเครื่องหมายออก) เช่น "1.5", "0/0.5"
        description = ข้อความอธิบายภาษาไทย
    """
    s = (line_str or "").strip()
    is_away_fav = s.startswith("-")
    magnitude = s.lstrip("+-").strip()
    if magnitude == "":
        magnitude = "0"

    if is_away_fav:
        favorite = "away"
        description = f"🔴 ทีมเยือนเป็นฝ่ายต่อ {magnitude} ลูก (เหย้าเป็นรอง)"
    else:
        favorite = "home"
        description = f"🔵 ทีมเหย้าเป็นฝ่ายต่อ {magnitude} ลูก (เยือนเป็นรอง)"
    return favorite, magnitude, description


def render_market_card(header, margin, labels, offered, probs_wpo, probs_basic):
    """
    แสดงผลตลาดหนึ่งตลาดแบบอ่านง่าย:
    - บรรทัดฟันธงผลที่น่าจะเป็นมากสุด
    - แถบความน่าจะเป็น (probability bar) ของแต่ละฝั่ง
    - ตารางละเอียด Basic vs WPO ซ่อนใน expander
    """
    st.markdown(f"#### {header}")
    st.metric("ค่าน้ำ (Overround)", f"{margin:.2f}%")

    if probs_wpo:
        best_i = max(range(len(probs_wpo)), key=lambda i: probs_wpo[i])
        fair_best = 1.0 / probs_wpo[best_i] if probs_wpo[best_i] > 0 else 0
        st.success(
            f"🎯 ฝั่งที่น่าจะเป็น: **{labels[best_i]}**  ·  "
            f"โอกาส {probs_wpo[best_i]*100:.1f}%  ·  ราคายุติธรรม {fair_best:.2f}"
        )

    # แถบความน่าจะเป็นของแต่ละฝั่ง (อิงวิธี WPO)
    for i, lab in enumerate(labels):
        p = probs_wpo[i] if i < len(probs_wpo) else 0.0
        fair = 1.0 / p if p > 0 else 0.0
        op = offered[i] if i < len(offered) else 0.0
        st.write(f"**{lab}**  ·  โอกาสจริง {p*100:.1f}%  ·  ยุติธรรม {fair:.2f}  ·  เจ้ามือเปิด {op:.2f}")
        st.progress(min(1.0, max(0.0, p)))

    with st.expander("📋 ดูตารางละเอียด (Basic vs WPO)"):
        df = pd.DataFrame({
            "ฝั่ง": labels,
            "ราคาตั้งต้น": [f"{o:.2f}" for o in offered],
            "โอกาส Basic": [f"{p*100:.2f}%" for p in probs_basic],
            "ยุติธรรม Basic": [f"{1.0/p:.3f}" if p > 0 else "N/A" for p in probs_basic],
            "โอกาส WPO": [f"{p*100:.2f}%" for p in probs_wpo],
            "ยุติธรรม WPO": [f"{1.0/p:.3f}" if p > 0 else "N/A" for p in probs_wpo],
        })
        st.table(df)


# =====================================================================
# 2. แบบจำลองสถิติเชิงปริมาณการทำประตู (Poisson & Dixon-Coles)
# =====================================================================

def poisson_pmf(k, lamb):
    """คำนวณ Poisson Probability Mass Function (โอกาสเกิดประตู k ลูก)"""
    if lamb <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lamb) * (lamb ** k)) / math.factorial(k)


def d_coles_tau(x, y, lambda_h, lambda_a, rho):
    """ฟังก์ชันปรับปรุงสหสัมพันธ์ Dixon-Coles tau(x, y) สำหรับสกอร์ต่ำ"""
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
    """คำนวณความน่าจะเป็นชนะ เสมอ แพ้ (1X2) จากค่าคาดหวังการทำประตู (xG)"""
    prob_matrix = [[0.0 for _ in range(max_goals + 1)] for _ in range(max_goals + 1)]

    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            p_x = poisson_pmf(x, lambda_h)
            p_y = poisson_pmf(y, lambda_a)
            tau = d_coles_tau(x, y, lambda_h, lambda_a, rho)
            prob_matrix[x][y] = p_x * p_y * tau

    total_p = sum(sum(row) for row in prob_matrix)
    if total_p == 0:
        return 0.3333, 0.3333, 0.3333
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            prob_matrix[x][y] /= total_p

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
# 3. หน้าจอการกรอกข้อมูลและโต้ตอบ
# =====================================================================

st.title("⚽ Football Betting Math Engine (โปรแกรมคำนวณราคาบอล)")
st.write("ระบบคำนวณส่วนต่างค่าน้ำ (Overround) และสกัดหาความน่าจะเป็นที่แท้จริงจากอัตราต่อรองของเจ้ามือ")

# ส่วนจัดการไฟล์ Excel
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

tab1, tab2, tab3 = st.tabs(["ถอดค่าน้ำของเจ้ามือ", "แบบจำลองสถิติทำนายประตู", "ระบบตรวจรับตั๋วแบบหน่วงเวลา"])

# --- แท็บที่ 1: เครื่องมือถอดค่าน้ำของเจ้ามือ ---
with tab1:
    # ---- กำหนดค่าเริ่มต้นใน session_state (ทำครั้งเดียว) ----
    defaults = {
        "match_title": "ซันไชน์ โค้สท์ วอนเดอร์เรอส์ เอฟซี VS เซนต์ จอร์จ วิลเลวอง เอฟซี",
        "h_1x2": 1.46, "d_1x2": 4.14, "a_1x2": 4.64,
        "ah_line": "1", "h_ah_raw": 0.82, "a_ah_raw": 1.00,
        "ou_line": "3/3.5", "over_raw": 0.80, "under_raw": 1.00,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    st.header("เครื่องมือวิเคราะห์อัตรากำไรและถอดค่าน้ำของเจ้ามือ")

    # ================= ช่องวางข้อมูลดิบ (Raw Data Input) =================
    with st.expander("📋 วางข้อมูลดิบเพื่อเติมค่าอัตโนมัติ (Quick Fill)", expanded=True):
        st.caption("วางข้อมูลตามตัวอย่างด้านล่าง แล้วกดปุ่ม 'แยกข้อมูล' ระบบจะเติมค่าลงช่องต่างๆ ให้")
        example_text = (
            "ฝรั่งเศส VS ไอเวอรี่โคสต์\n"
            "เหย้า 1.30\n"
            "เสมอ 4.77\n"
            "เยือน 7.00\n"
            "เหย้า 0.90\n"
            "AH 1.5\n"
            "เยือน 0.94\n"
            "สูง 1.02\n"
            "สูง/ต่ำ 3\n"
            "ต่ำ 0.80"
        )
        raw_text = st.text_area(
            "ข้อมูลดิบ (Raw Data)",
            height=230,
            placeholder=example_text,
            key="raw_input",
        )
        c_btn1, c_btn2 = st.columns([1, 3])
        with c_btn1:
            if st.button("🔍 แยกข้อมูล / เติมค่าอัตโนมัติ"):
                parsed = parse_raw_match_data(raw_text)
                if parsed:
                    for k, v in parsed.items():
                        st.session_state[k] = v
                    st.success(f"เติมค่าสำเร็จ {len(parsed)} รายการ — เลื่อนลงดูช่องด้านล่างได้เลย")
                else:
                    st.warning("อ่านข้อมูลไม่ได้ กรุณาตรวจสอบรูปแบบให้ตรงกับตัวอย่าง")
        with c_btn2:
            if st.button("📄 ใส่ตัวอย่างให้ดู"):
                st.session_state["raw_input"] = example_text
                st.rerun()

    st.write("ป้อนอัตราต่อรองเพื่อคำนวณหาโอกาสเกิดผลจริงและตรวจสอบราคาที่ยุติธรรม")

    # ตัวเลือกรูปแบบราคา (HK Odds / Decimal Odds)
    odds_format = st.radio(
        "รูปแบบราคากลุ่มแฮนดิแคป (AH) และ สูง/ต่ำ (O/U)",
        options=[
            "ราคาฮ่องกง (HK Odds - แสดงเฉพาะกำไร เช่น 0.82)",
            "ราคายุโรป (Decimal Odds - แสดงทุนรวมกำไร เช่น 1.82)",
        ],
        index=0,
        key="odds_format",
    )

    match_title = st.text_input("คู่แข่งขัน", key="match_title")

    col1, col2, col3 = st.columns(3)

    # 1. ตลาด 1X2
    with col1:
        st.subheader("1. ตลาด 1X2 (ราคาพูล)")
        h_1x2 = st.number_input("เหย้า (Home Odds)", min_value=1.01, step=0.01, key="h_1x2")
        d_1x2 = st.number_input("เสมอ (Draw Odds)", min_value=1.01, step=0.01, key="d_1x2")
        a_1x2 = st.number_input("เยือน (Away Odds)", min_value=1.01, step=0.01, key="a_1x2")

        input_1x2 = [h_1x2, d_1x2, a_1x2]
        raw_1x2_probs = [1.0 / o for o in input_1x2 if o > 0]
        margin_1x2 = (sum(raw_1x2_probs) - 1.0) * 100

        p_1x2_basic = remove_margin_basic(input_1x2)
        p_1x2_wpo = remove_margin_wpo(input_1x2)

    # 2. ตลาด Asian Handicap
    with col2:
        st.subheader("2. ตลาด Asian Handicap")
        ah_line = st.text_input("แต้มต่อ (AH Line)", key="ah_line",
                                help="ใส่ '-' นำหน้าถ้าทีมเยือนเป็นฝ่ายต่อ เช่น -1.5 / ไม่ใส่ถ้าเหย้าต่อ เช่น 1.5")

        # แปลความเส้นแต้มต่อตามเครื่องหมาย (- = เยือนต่อ, ไม่มี = เหย้าต่อ)
        ah_favorite, ah_magnitude, ah_desc = interpret_ah_line(ah_line)
        st.caption(ah_desc)

        h_ah_raw = st.number_input("เหย้า (Home AH Odds)", min_value=0.01, step=0.01, key="h_ah_raw")
        a_ah_raw = st.number_input("เยือน (Away AH Odds)", min_value=0.01, step=0.01, key="a_ah_raw")

        if odds_format.startswith("ราคาฮ่องกง"):
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

    # 3. ตลาด สูง/ต่ำ
    with col3:
        st.subheader("3. ตลาด สูง/ต่ำ (Over/Under)")
        ou_line = st.text_input("เกณฑ์ประตู สูง/ต่ำ (O/U Line)", key="ou_line")
        over_raw = st.number_input("ราคา สูง (Over Odds)", min_value=0.01, step=0.01, key="over_raw")
        under_raw = st.number_input("ราคา ต่ำ (Under Odds)", min_value=0.01, step=0.01, key="under_raw")

        if odds_format.startswith("ราคาฮ่องกง"):
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

    # การแสดงผลลัพธ์เชิงวิเคราะห์
    st.write("---")
    st.subheader(f"📊 ผลการวิเคราะห์ราคายุติธรรม: {match_title}")

    # ป้ายฝั่งแฮนดิแคปเปลี่ยนตามว่าทีมใดเป็นฝ่ายต่อ
    if ah_favorite == "away":
        outcomes_ah = [f"เหย้ารอง (+{ah_magnitude})", f"เยือนต่อ (-{ah_magnitude})"]
    else:
        outcomes_ah = [f"เหย้าต่อ (-{ah_magnitude})", f"เยือนรอง (+{ah_magnitude})"]
    outcomes_1x2 = ["เหย้า (Home)", "เสมอ (Draw)", "เยือน (Away)"]
    outcomes_ou = ["สูง (Over)", "ต่ำ (Under)"]

    out_col1, out_col2, out_col3 = st.columns(3)
    with out_col1:
        render_market_card("ตลาด 1X2", margin_1x2, outcomes_1x2,
                           input_1x2, p_1x2_wpo, p_1x2_basic)
    with out_col2:
        render_market_card(f"ตลาด AH (เส้น {ah_line})", margin_ah, outcomes_ah,
                           input_ah, p_ah_wpo, p_ah_basic)
    with out_col3:
        render_market_card(f"ตลาด สูง/ต่ำ (เส้น {ou_line})", margin_ou, outcomes_ou,
                           input_ou, p_ou_wpo, p_ou_basic)

    # ---------------- เครื่องมือเช็ก Value Bet ----------------
    st.write("---")
    st.subheader("🔎 เครื่องมือเช็ก Value Bet")
    st.caption("เลือกฝั่งที่สนใจ แล้วใส่ราคาที่คุณหาได้จากเจ้าอื่น ระบบจะเทียบกับราคายุติธรรม (WPO) ว่าคุ้มหรือไม่")

    # รวมทุกฝั่งจากทุกตลาด พร้อมราคายุติธรรม WPO
    side_fair = {}
    for lab, p in zip(outcomes_1x2, p_1x2_wpo):
        if p > 0:
            side_fair[f"[1X2] {lab}"] = 1.0 / p
    for lab, p in zip(outcomes_ah, p_ah_wpo):
        if p > 0:
            side_fair[f"[AH] {lab}"] = 1.0 / p
    for lab, p in zip(outcomes_ou, p_ou_wpo):
        if p > 0:
            side_fair[f"[O/U] {lab}"] = 1.0 / p

    vc1, vc2, vc3 = st.columns([3, 2, 4])
    with vc1:
        chosen_side = st.selectbox("เลือกฝั่งที่จะแทง", list(side_fair.keys()))
    with vc2:
        my_odds = st.number_input("ราคาที่หาได้ (Decimal)", min_value=1.01, value=2.00, step=0.01)
    with vc3:
        fair_odds = side_fair[chosen_side]
        edge = (my_odds / fair_odds - 1.0) * 100  # ความได้เปรียบเชิงคาดหวัง (EV %)
        st.write("")  # จัดแนวให้สวยงาม
        if my_odds > fair_odds:
            st.success(f"✅ มีค่า (Value)! ราคาที่ได้ {my_odds:.2f} > ยุติธรรม {fair_odds:.2f} · ความได้เปรียบ +{edge:.2f}%")
        elif abs(my_odds - fair_odds) < 1e-9:
            st.info(f"➖ พอดีราคายุติธรรม ({fair_odds:.2f}) ไม่ได้เปรียบไม่เสียเปรียบ")
        else:
            st.error(f"❌ ไม่คุ้ม ราคาที่ได้ {my_odds:.2f} < ยุติธรรม {fair_odds:.2f} · {edge:.2f}%")

    st.info("💡 **คำแนะนำ:** ใช้ราคายุติธรรมจากวิธี **WPO** เป็นเกณฑ์ เพราะลบค่าความเบี่ยงเบนของเจ้ามือ (Favorite-Longshot Bias) ได้แม่นยำที่สุด · ค่าน้ำ (Overround) ยิ่งต่ำ ราคายิ่งจริง — AH และ สูง/ต่ำ จึงน่าเชื่อถือกว่า 1X2")


# --- แท็บที่ 2: แบบจำลองสถิติทำนายประตู ---
with tab2:
    st.header("แบบจำลองพยากรณ์ความน่าจะเป็นจากการยิงประตูเฉลี่ย")
    st.write("ระบุระดับฟอร์มการเล่นของทีม (Expected Goals - xG) เพื่อเปรียบเทียบผลลัพธ์แบบ Poisson กับ Dixon-Coles")

    col1, col2 = st.columns(2)
    with col1:
        lambda_h = st.slider("ระดับฟอร์มเกมรุกเจ้าบ้าน (Home xG)", min_value=0.0, max_value=5.0, value=1.6, step=0.1)
        lambda_a = st.slider("ระดับฟอร์มเกมรุกทีมเยือน (Away xG)", min_value=0.0, max_value=5.0, value=1.2, step=0.1)
        rho_val = st.slider("ค่าสหสัมพันธ์ประตูน้อย Dixon-Coles (rho)", min_value=-0.30, max_value=0.0, value=-0.11, step=0.01)

    with col2:
        st.subheader("เปรียบเทียบสถิติความน่าจะเป็นของการชนะ เสมอ แพ้")
        p_hw, p_dr, p_aw = calculate_match_odds(lambda_h, lambda_a, rho=0.0)
        dc_hw, dc_dr, dc_aw = calculate_match_odds(lambda_h, lambda_a, rho=rho_val)
        prediction_results = {
            "แบบจำลองทางสถิติ": ["Poisson", "Dixon-Coles"],
            "โอกาสเจ้าบ้านชนะ": [f"{p_hw*100:.2f}%", f"{dc_hw*100:.2f}%"],
            "โอกาสเสมอ (Draw)": [f"{p_dr*100:.2f}%", f"{dc_dr*100:.2f}%"],
            "โอกาสทีมเยือนชนะ": [f"{p_aw*100:.2f}%", f"{dc_aw*100:.2f}%"],
        }
        st.table(prediction_results)
        st.write("📊 **วิเคราะห์เชิงสถิติ:** แบบจำลอง Dixon-Coles ใช้พารามิเตอร์สหสัมพันธ์ $\\rho$ ชดเชยให้สถานการณ์ประตูรวมต่ำ ซึ่งเป็นจุดที่ Poisson ทั่วไปมักมองข้ามโอกาสเสมอ")


# --- แท็บที่ 3: ระบบตรวจรับตั๋วแบบหน่วงเวลา ---
with tab3:
    st.header("ระบบวิเคราะห์ความเสี่ยงและหน่วงเวลารับเดิมพันเรียลไทม์ (Live Bet Delay Simulator)")
    st.write("ทดลองจำลองเหตุการณ์ในสนาม เพื่อศึกษาว่ากระบวนการ Bet Delay ป้องกันความเสี่ยงได้อย่างไร")

    if "live_event_stream" not in st.session_state:
        st.session_state["live_event_stream"] = []
    if "bet_history" not in st.session_state:
        st.session_state["bet_history"] = []

    col_ctrl, col_display = st.columns([7, 8])

    with col_ctrl:
        st.subheader("แผงจำลองการป้อนข้อมูลสนามสด")

        if st.button("🚨 จำลองการยิงประตู (Goal!)"):
            team = random.choice(["Home", "Away"])
            st.session_state["live_event_stream"].append({
                "timestamp": time.time(), "event": "Goal",
                "team": team, "time_str": time.strftime('%H:%M:%S'),
            })
            st.toast(f"⚽ Goal! ฝั่ง {team} ยิงประตูได้เรียบร้อยแล้ว")

        if st.button("🟥 จำลองใบแดง (Red Card)"):
            team = random.choice(["Home", "Away"])
            st.session_state["live_event_stream"].append({
                "timestamp": time.time(), "event": "Red Card",
                "team": team, "time_str": time.strftime('%H:%M:%S'),
            })
            st.toast(f"🟥 Red Card! ฝั่ง {team} ได้รับใบแดง")

        if st.button("🧹 ล้างข้อมูลประวัติและเหตุการณ์ทั้งหมด"):
            st.session_state["live_event_stream"] = []
            st.session_state["bet_history"] = []
            st.rerun()

        st.write("---")
        st.subheader("กล่องส่งใบเดิมพัน (Submit Ticket)")

        bet_selection = st.selectbox(
            "เลือกประเภทการเดิมพัน",
            ["เจ้าบ้านชนะ", "เสมอ", "ทีมเยือนชนะ", "สูง", "ต่ำ"],
        )
        delay_seconds = st.slider("ตั้งค่าระยะเวลาหน่วงตั๋ว (Bet Delay Seconds)", min_value=1, max_value=10, value=6)

        if st.button("📥 ยืนยันการส่งเดิมพัน"):
            submission_time = time.time()
            st.info(f"⏳ ตั๋วถูกส่งเข้าคิวหน่วงเวลาตรวจสอบความเสี่ยง (หน่วงเวลา {delay_seconds} วินาที)...")

            progress_bar = st.progress(0)
            for percent in range(100):
                time.sleep(delay_seconds / 100.0)
                progress_bar.progress(percent + 1)

            is_valid = True
            triggered_event = None
            for event in st.session_state["live_event_stream"]:
                if submission_time <= event["timestamp"] <= (submission_time + delay_seconds):
                    if event["event"] in ["Goal", "Red Card"]:
                        is_valid = False
                        triggered_event = event
                        break

            bet_record = {
                "time": time.strftime('%H:%M:%S'),
                "selection": bet_selection,
                "status": "Accepted" if is_valid else "Rejected",
                "reason": "บิลสะอาด ปราศจากเหตุการณ์แทรกแซงในช่วง Bet Delay" if is_valid
                          else f"ตรวจพบเหตุการณ์สำคัญขัดแย้งขณะรออนุมัติ: {triggered_event['event']} ({triggered_event['team']})",
            }
            st.session_state["bet_history"].insert(0, bet_record)

            if is_valid:
                st.success("✅ ตั๋วเดิมพันของคุณได้รับการยอมรับ (Accepted) สำเร็จ!")
            else:
                st.error(f"❌ ปฏิเสธตั๋วเดิมพัน (Rejected)! - {bet_record['reason']}")

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
