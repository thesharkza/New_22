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


def line_to_float(s):
    """แปลงสตริงเส้น เช่น '3/3.5', '-1.5', '0/0.5' เป็นตัวเลข (ค่าเฉลี่ยถ้าเป็นเส้นครึ่ง)"""
    s = str(s).strip().lstrip('+')
    neg = s.startswith('-')
    s = s.lstrip('-')
    try:
        if '/' in s:
            a, b = s.split('/')
            val = (float(a) + float(b)) / 2.0
        else:
            val = float(s) if s else 0.0
    except ValueError:
        val = 0.0
    return -val if neg else val


def model_full(lh, la, threshold, hcap_home, rho=0.0, mg=10):
    """
    คำนวณจากโมเดล Poisson/Dixon-Coles ในรอบเดียว คืนค่า:
    (home_win, draw, away_win, over_prob, ah_home_cover_prob)
    - threshold: เส้นสูง/ต่ำ (ตัวเลข)
    - hcap_home: แต้มต่อจากมุมเจ้าบ้าน (ติดลบ = เหย้าต่อ, บวก = เหย้ารับแต้ม)
    """
    px = [poisson_pmf(i, lh) for i in range(mg + 1)]
    py = [poisson_pmf(j, la) for j in range(mg + 1)]
    mat = [[px[i] * py[j] * d_coles_tau(i, j, lh, la, rho) for j in range(mg + 1)] for i in range(mg + 1)]
    tot = sum(sum(r) for r in mat)
    if tot <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0

    hw = dr = aw = ov = 0.0
    margin = {}
    for i in range(mg + 1):
        for j in range(mg + 1):
            p = mat[i][j] / tot
            if i > j:
                hw += p
            elif i == j:
                dr += p
            else:
                aw += p
            if (i + j) > threshold:
                ov += p
            m = i - j
            margin[m] = margin.get(m, 0.0) + p

    def single(sub):
        w = pu = 0.0
        for m, p in margin.items():
            adj = m + sub
            if adj > 0:
                w += p
            elif abs(adj) < 1e-9:
                pu += p
        return w + 0.5 * pu  # คืนเงินครึ่งเสมอ ถือเป็นกลาง

    frac = round(hcap_home - math.floor(hcap_home), 2)
    if abs(frac - 0.25) < 1e-6 or abs(frac - 0.75) < 1e-6:
        home_cover = 0.5 * single(hcap_home - 0.25) + 0.5 * single(hcap_home + 0.25)
    else:
        home_cover = single(hcap_home)

    return hw, dr, aw, ov, home_cover


def implied_xg_from_market(home_p, draw_p, away_p, over_p, threshold, rho=0.0):
    """
    ถอดค่า xG (lambda เหย้า/เยือน) จากความน่าจะเป็นในตลาด
    โดยหาคู่ lambda ที่ทำให้โมเดลตรงกับ 1X2 + สูง/ต่ำ มากที่สุด (grid + fine search)
    """
    def err_at(lh, la):
        hw, dr, aw, ov, _ = model_full(lh, la, threshold, 0.0, rho=rho, mg=8)
        return (hw - home_p) ** 2 + (dr - draw_p) ** 2 + (aw - away_p) ** 2 + (ov - over_p) ** 2

    best = (1.3, 1.1)
    best_err = 1e9
    coarse = [x / 20.0 for x in range(2, 71)]  # 0.10 - 3.50 step 0.05
    for lh in coarse:
        for la in coarse:
            e = err_at(lh, la)
            if e < best_err:
                best_err = e
                best = (lh, la)

    # ค้นละเอียดรอบจุดที่ดีที่สุด
    lh0, la0 = best
    fine = [-0.04, -0.02, 0.0, 0.02, 0.04]
    for dh in fine:
        for da in fine:
            lh, la = lh0 + dh, la0 + da
            if 0.05 < lh < 5 and 0.05 < la < 5:
                e = err_at(lh, la)
                if e < best_err:
                    best_err = e
                    best = (lh, la)

    return best, best_err


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

tab1, tab2, tab3, tab4 = st.tabs([
    "ถอดค่าน้ำของเจ้ามือ",
    "แบบจำลองสถิติทำนายประตู",
    "ระบบตรวจรับตั๋วแบบหน่วงเวลา",
    "CLV Tracker (วัดการเอาชนะราคาปิด)",
])

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
    # ค่าเริ่มต้นสไลเดอร์ (ใช้ key เพื่อให้ปุ่มถอด xG เขียนค่าได้)
    for k, v in {"lambda_h": 1.6, "lambda_a": 1.2, "rho_val": -0.11}.items():
        st.session_state.setdefault(k, v)

    st.header("แบบจำลองพยากรณ์ความน่าจะเป็นจากการยิงประตูเฉลี่ย")
    st.write("ระบุระดับฟอร์มการเล่นของทีม (Expected Goals - xG) หรือกดถอดค่าจากราคาในแท็บ 1 อัตโนมัติ")

    # ---------- ฟีเจอร์ 1: ถอดค่า xG จากราคาอัตโนมัติ ----------
    if st.button("🔄 ถอดค่า xG จากราคาในแท็บ 1 อัตโนมัติ"):
        if (p_1x2_wpo and len(p_1x2_wpo) == 3 and p_ou_wpo and len(p_ou_wpo) == 2):
            threshold = line_to_float(ou_line)
            with st.spinner("กำลังคำนวณค่า xG ที่ตรงกับราคา..."):
                (lh, la), fit_err = implied_xg_from_market(
                    p_1x2_wpo[0], p_1x2_wpo[1], p_1x2_wpo[2],
                    p_ou_wpo[0], threshold, rho=st.session_state["rho_val"],
                )
            st.session_state["lambda_h"] = round(lh, 1)
            st.session_state["lambda_a"] = round(la, 1)
            st.success(f"ถอดค่าสำเร็จ → เหย้า xG ≈ {lh:.2f}, เยือน xG ≈ {la:.2f} (ค่าคลาดเคลื่อน {fit_err:.5f})")
        else:
            st.warning("กรุณากรอกราคาในแท็บ 1 (1X2 และ สูง/ต่ำ) ให้ครบก่อน")

    col1, col2 = st.columns(2)
    with col1:
        lambda_h = st.slider("ระดับฟอร์มเกมรุกเจ้าบ้าน (Home xG)", min_value=0.0, max_value=5.0, step=0.1, key="lambda_h")
        lambda_a = st.slider("ระดับฟอร์มเกมรุกทีมเยือน (Away xG)", min_value=0.0, max_value=5.0, step=0.1, key="lambda_a")
        rho_val = st.slider("ค่าสหสัมพันธ์ประตูน้อย Dixon-Coles (rho)", min_value=-0.30, max_value=0.0, step=0.01, key="rho_val")

    with col2:
        st.subheader("เปรียบเทียบความน่าจะเป็น ชนะ/เสมอ/แพ้")
        p_hw, p_dr, p_aw = calculate_match_odds(lambda_h, lambda_a, rho=0.0)
        dc_hw, dc_dr, dc_aw = calculate_match_odds(lambda_h, lambda_a, rho=rho_val)
        prediction_results = {
            "แบบจำลองทางสถิติ": ["Poisson", "Dixon-Coles"],
            "โอกาสเจ้าบ้านชนะ": [f"{p_hw*100:.2f}%", f"{dc_hw*100:.2f}%"],
            "โอกาสเสมอ (Draw)": [f"{p_dr*100:.2f}%", f"{dc_dr*100:.2f}%"],
            "โอกาสทีมเยือนชนะ": [f"{p_aw*100:.2f}%", f"{dc_aw*100:.2f}%"],
        }
        st.table(prediction_results)
        st.caption("Dixon-Coles ใช้ค่า rho ชดเชยสถานการณ์ประตูรวมต่ำ ซึ่ง Poisson ทั่วไปมักมองข้าม")

    # ---------- ฟีเจอร์ 2: สแกนหา Value อัตโนมัติ ----------
    st.write("---")
    st.subheader("🤖 สแกนหา Value อัตโนมัติ (โมเดล vs ราคาเจ้ามือ)")
    st.caption("เทียบความน่าจะเป็นจากโมเดล Dixon-Coles กับราคาที่ถอดค่าน้ำแล้ว (WPO) ทุกฝั่ง แล้วชี้จุดที่โมเดลมองว่าราคาเจ้ามือ 'ใจดีเกินจริง' = อาจมี Value")

    threshold = line_to_float(ou_line)
    fav, mag_str, _ = interpret_ah_line(ah_line)
    mag = line_to_float(mag_str)
    hcap_home = -mag if fav == "home" else mag
    m_hw, m_dr, m_aw, m_ov, m_ah_home = model_full(lambda_h, lambda_a, threshold, hcap_home, rho=rho_val)
    m_ah_away = 1.0 - m_ah_home
    m_un = 1.0 - m_ov

    # ป้ายและคู่ (โอกาสโมเดล, โอกาสตลาด WPO, ราคาเจ้ามือเปิด)
    scan_rows = []
    def add_row(name, model_p, market_p, offered):
        if model_p <= 0 or market_p <= 0:
            return
        edge = (model_p * offered - 1.0) * 100  # EV% ถ้าแทงที่ราคาเจ้ามือเปิด
        scan_rows.append({
            "ฝั่ง": name,
            "โอกาสโมเดล": model_p,
            "โอกาสตลาด": market_p,
            "ส่วนต่าง": (model_p - market_p) * 100,
            "ราคาเปิด": offered,
            "EV%": edge,
        })

    add_row("[1X2] เหย้า", m_hw, p_1x2_wpo[0], input_1x2[0])
    add_row("[1X2] เสมอ", m_dr, p_1x2_wpo[1], input_1x2[1])
    add_row("[1X2] เยือน", m_aw, p_1x2_wpo[2], input_1x2[2])
    if fav == "home":
        add_row(f"[AH] เหย้าต่อ (-{mag_str})", m_ah_home, p_ah_wpo[0], input_ah[0])
        add_row(f"[AH] เยือนรอง (+{mag_str})", m_ah_away, p_ah_wpo[1], input_ah[1])
    else:
        add_row(f"[AH] เหย้ารอง (+{mag_str})", m_ah_home, p_ah_wpo[0], input_ah[0])
        add_row(f"[AH] เยือนต่อ (-{mag_str})", m_ah_away, p_ah_wpo[1], input_ah[1])
    add_row("[O/U] สูง", m_ov, p_ou_wpo[0], input_ou[0])
    add_row("[O/U] ต่ำ", m_un, p_ou_wpo[1], input_ou[1])

    if scan_rows:
        scan_rows.sort(key=lambda r: r["EV%"], reverse=True)
        best = scan_rows[0]
        if best["EV%"] > 0:
            st.success(
                f"🎯 จุดที่น่าสนใจสุด: **{best['ฝั่ง']}** — โมเดลให้โอกาส {best['โอกาสโมเดล']*100:.1f}% "
                f"แต่ตลาดให้แค่ {best['โอกาสตลาด']*100:.1f}% · ราคาเปิด {best['ราคาเปิด']:.2f} · EV +{best['EV%']:.2f}%"
            )
        else:
            st.info("ไม่พบฝั่งที่โมเดลมองว่าได้เปรียบ — ราคาเจ้ามือสอดคล้องกับโมเดลแล้ว")

        df_scan = pd.DataFrame([{
            "ฝั่ง": r["ฝั่ง"],
            "โอกาสโมเดล": f"{r['โอกาสโมเดล']*100:.1f}%",
            "โอกาสตลาด": f"{r['โอกาสตลาด']*100:.1f}%",
            "ส่วนต่าง": f"{r['ส่วนต่าง']:+.1f}%",
            "ราคาเปิด": f"{r['ราคาเปิด']:.2f}",
            "EV%": f"{r['EV%']:+.2f}%",
        } for r in scan_rows])
        st.table(df_scan)
        st.caption("⚠️ EV% บวก = โมเดลมองว่าคุ้ม แต่ขึ้นกับว่าค่า xG ที่ใช้แม่นแค่ไหน (แนะนำกดถอด xG จากราคาก่อน) ไม่ใช่การการันตีกำไร")


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


# --- แท็บที่ 4: CLV Tracker ---
with tab4:
    st.header("📈 CLV Tracker — วัดการเอาชนะราคาปิด (Closing Line Value)")
    st.write(
        "บันทึกราคาที่คุณแทงไว้ พอตลาดปิดค่อยใส่ราคาปิดเข้าไป ระบบจะวัดว่าคุณได้ราคา "
        "**ดีกว่าตอนปิด** หรือไม่ — CLV เป็นตัวชี้วัดว่ากระบวนการหา value ของคุณดีจริงไหม "
        "(น่าเชื่อถือกว่ากำไร/ขาดทุนระยะสั้น แต่ไม่ใช่การการันตีกำไร)"
    )

    if "clv_log" not in st.session_state:
        st.session_state["clv_log"] = []

    # ---------- บันทึกตั๋วใหม่ ----------
    with st.form("clv_add_form", clear_on_submit=True):
        st.subheader("➕ บันทึกตั๋วใหม่ (ตอนที่แทง)")
        f1, f2 = st.columns(2)
        with f1:
            in_match = st.text_input("คู่แข่งขัน", value=st.session_state.get("match_title", ""))
            in_sel = st.text_input("ฝั่งที่แทง (เช่น เหย้า -1.5 / สูง 3.5)")
        with f2:
            in_odds = st.number_input("ราคาที่แทงได้ (Decimal)", min_value=1.01, value=2.00, step=0.01)
            in_stake = st.number_input("เงินเดิมพัน (หน่วย)", min_value=0.0, value=1.0, step=0.5)
        if st.form_submit_button("📥 บันทึกตั๋ว"):
            st.session_state["clv_log"].append({
                "เวลา": time.strftime("%m-%d %H:%M"),
                "คู่": in_match,
                "ฝั่ง": in_sel,
                "ราคาแทง": float(in_odds),
                "ทุน": float(in_stake),
                "ราคาปิด": 0.0,
                "ปิดฝั่งตรงข้าม": 0.0,
            })
            st.success("บันทึกแล้ว — เลื่อนลงไปกรอกราคาปิดในตารางเมื่อตลาดปิด")

    # ---------- ตารางแก้ไข + ผล CLV ----------
    st.write("---")
    st.subheader("📋 ตารางตั๋ว + ใส่ราคาปิด")

    if not st.session_state["clv_log"]:
        st.info("ยังไม่มีตั๋วในบันทึก เพิ่มด้านบนได้เลย")
    else:
        df_log = pd.DataFrame(st.session_state["clv_log"])
        st.caption("แก้ไขช่อง 'ราคาปิด' (และ 'ปิดฝั่งตรงข้าม' ถ้ามี เพื่อคำนวณแบบถอดค่าน้ำ) ได้ในตารางเลย · ลบแถวได้ด้วยปุ่มถังขยะ")
        edited = st.data_editor(
            df_log,
            key="clv_editor",
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "ราคาแทง": st.column_config.NumberColumn("ราคาแทง", min_value=1.01, step=0.01, format="%.2f"),
                "ทุน": st.column_config.NumberColumn("ทุน", min_value=0.0, step=0.5, format="%.1f"),
                "ราคาปิด": st.column_config.NumberColumn("ราคาปิด", min_value=0.0, step=0.01, format="%.2f", help="ใส่ 0 ถ้ายังไม่ปิด"),
                "ปิดฝั่งตรงข้าม": st.column_config.NumberColumn("ปิดฝั่งตรงข้าม", min_value=0.0, step=0.01, format="%.2f", help="ราคาปิดของฝั่งตรงข้าม (ไม่ใส่ก็ได้)"),
            },
        )
        # เขียนค่ากลับเข้า session_state
        st.session_state["clv_log"] = edited.fillna(0).to_dict("records")

        # คำนวณ CLV ของแต่ละตั๋ว
        rows = edited.fillna(0).to_dict("records")
        clv_odds_list = []
        clv_novig_list = []
        beat_count = 0
        settled = 0
        display_rows = []
        for r in rows:
            bo = float(r.get("ราคาแทง", 0) or 0)
            close = float(r.get("ราคาปิด", 0) or 0)
            other = float(r.get("ปิดฝั่งตรงข้าม", 0) or 0)
            clv_odds = clv_novig = None
            if bo > 1 and close > 1:
                settled += 1
                clv_odds = (bo / close - 1.0) * 100
                clv_odds_list.append(clv_odds)
                if clv_odds > 0:
                    beat_count += 1
                if other > 1:
                    true_p = (1.0 / close) / ((1.0 / close) + (1.0 / other))
                    clv_novig = (true_p * bo - 1.0) * 100
                    clv_novig_list.append(clv_novig)
            display_rows.append({
                "เวลา": r.get("เวลา", ""),
                "ฝั่ง": r.get("ฝั่ง", ""),
                "ราคาแทง": f"{bo:.2f}" if bo else "-",
                "ราคาปิด": f"{close:.2f}" if close > 1 else "ยังไม่ปิด",
                "CLV (ราคา)": f"{clv_odds:+.2f}%" if clv_odds is not None else "-",
                "CLV (ถอดค่าน้ำ)": f"{clv_novig:+.2f}%" if clv_novig is not None else "-",
            })

        st.write("---")
        st.subheader("📊 ผลการวัด CLV")
        if settled == 0:
            st.info("ยังไม่มีตั๋วที่ใส่ราคาปิด — กรอกราคาปิดในตารางด้านบนเพื่อดูผล")
        else:
            avg_clv = sum(clv_odds_list) / len(clv_odds_list)
            beat_pct = beat_count / settled * 100
            avg_novig = (sum(clv_novig_list) / len(clv_novig_list)) if clv_novig_list else None

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("CLV เฉลี่ย (ราคา)", f"{avg_clv:+.2f}%")
            mc2.metric("ตั๋วที่ชนะราคาปิด", f"{beat_count}/{settled}", f"{beat_pct:.0f}%")
            mc3.metric("CLV เฉลี่ย (ถอดค่าน้ำ)", f"{avg_novig:+.2f}%" if avg_novig is not None else "—")

            if avg_clv > 0:
                st.success("✅ โดยรวมคุณได้ราคาดีกว่าตอนปิด — เป็นสัญญาณว่ากระบวนการหา value ของคุณมีแนวโน้มดี")
            else:
                st.warning("⚠️ โดยรวมคุณได้ราคาแย่กว่าตอนปิด — ลองทบทวนจังหวะแทงหรือเกณฑ์ที่ใช้")

            st.table(pd.DataFrame(display_rows))

            # กราฟ CLV ต่อตั๋ว
            if clv_odds_list:
                st.caption("CLV (ราคา) รายตั๋ว — แท่งบวก = ชนะราคาปิด")
                st.bar_chart(pd.DataFrame({"CLV %": clv_odds_list}))

        # ดาวน์โหลด / นำเข้า เพื่อเก็บข้ามเซสชัน
        st.write("---")
        st.subheader("💾 บันทึก/โหลดข้อมูล (กันข้อมูลหายเมื่อปิดแอป)")
        dl1, dl2 = st.columns(2)
        with dl1:
            csv_bytes = edited.fillna(0).to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ ดาวน์โหลด log (CSV)", csv_bytes, "clv_log.csv", "text/csv")
        with dl2:
            up = st.file_uploader("⬆️ โหลด log เก่า (CSV)", type=["csv"], key="clv_upload")
            if up is not None:
                if st.button("นำเข้าข้อมูลจากไฟล์นี้"):
                    try:
                        df_up = pd.read_csv(up)
                        st.session_state["clv_log"] = df_up.fillna(0).to_dict("records")
                        st.success("นำเข้าข้อมูลสำเร็จ")
                        st.rerun()
                    except Exception as e:
                        st.error(f"อ่านไฟล์ไม่สำเร็จ: {e}")

    with st.expander("ℹ️ CLV คืออะไร และอ่านผลยังไง"):
        st.markdown(
            "- **CLV (ราคา)** = ราคาที่คุณแทงได้ดีกว่าราคาปิดกี่ % — สูตร `(ราคาแทง / ราคาปิด − 1) × 100`\n"
            "- **บวก** = คุณล็อกราคาก่อนที่มันจะไหลลง = จับ value ได้จริง · **ลบ** = คุณได้ราคาแย่กว่าตอนปิด\n"
            "- **CLV (ถอดค่าน้ำ)** = แม่นกว่า เพราะเอาราคาปิดสองฝั่งมาถอดค่าน้ำก่อน แล้ววัด EV เทียบราคาที่คุณแทง (ต้องกรอก 'ปิดฝั่งตรงข้าม')\n"
            "- เป้าหมายระยะยาว: ให้ **CLV เฉลี่ยเป็นบวก** และสัดส่วนตั๋วที่ชนะราคาปิด > 50% สม่ำเสมอ\n"
            "- ข้อควรจำ: CLV วัดว่า *กระบวนการ* ดีไหม ไม่ได้แปลว่าตั๋วนั้นถูกเสมอ และไม่การันตีกำไร"
        )
