import math

# =====================================================================
# 1. ฟังก์ชันถอดส่วนต่างค่าน้ำ (De-vigging Calculators)
# =====================================================================

def remove_margin_basic(odds):
    """
    วิธี Basic (Multiplicative) De-vigging
    สูตรคณิตศาสตร์: $p_i = \frac{r_i}{\sum r}$ โดยที่ $r_i = \frac{1}{O_i}$
    """
    raw_probs = [1.0 / od for od in odds]
    total_sum = sum(raw_probs)
    true_probs = [rp / total_sum for rp in raw_probs]
    return true_probs


def remove_margin_wpo(odds):
    """
    วิธี Margin Weights Proportional to Odds (WPO/MPTO)
    ช่วยปรับปรุงความคลาดเคลื่อนจากพฤติกรรมของเจ้ามือที่ชอบบวกค่าน้ำฝั่งทีมรอง (Favorite-Longshot Bias)
    สูตรคณิตศาสตร์: $p_i = \frac{n - M \times O_i}{n \times O_i}$ หรือเทียบเท่ากับ $\frac{1}{O_i} - \frac{M}{n}$
    """
    raw_probs = [1.0 / od for od in odds]
    n = len(odds)
    overround = sum(raw_probs) - 1.0  # ค่า M (Margin/Overround)
    
    true_probs =
    for od in odds:
        # ลบส่วนแบ่ง Overround เฉลี่ยออกจากแต่ละฝั่ง
        p_i = (1.0 / od) - (overround / n)
        # ป้องกันไม่ให้ค่าติดลบในกรณีที่ทีมรองมีโอกาสชนะต่ำมาก
        true_probs.append(max(0.0001, p_i))
        
    # Re-normalize อีกครั้งเพื่อป้องกันความคลาดเคลื่อนทางทศนิยม
    total_sum = sum(true_probs)
    return [tp / total_sum for tp in true_probs]


# =====================================================================
# 2. แบบจำลองสถิติทำนายผลประตู (Poisson & Dixon-Coles)
# =====================================================================

def poisson_pmf(k, lamb):
    """สูตรคำนวณ Poisson Probability Mass Function (โอกาสในการเกิดประตู k ประตู)"""
    return (math.exp(-lamb) * (lamb ** k)) / math.factorial(k)


def d_coles_tau(x, y, lambda_h, lambda_a, rho):
    """
    ฟังก์ชันปรับปรุงสหสัมพันธ์ Dixon-Coles $\tau(x, y)$
    เพื่อแก้ปัญหาความไม่เป็นอิสระต่อกันของคู่สกอร์ไลน์ต่ำ (0-0, 1-0, 0-1, 1-1)
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
    """
    คำนวณโอกาสผลชนะ เสมอ แพ้ (1X2 Probabilities) โดยใช้แบบจำลองสถิติ
    """
    prob_matrix = [[0.0 for _ in range(max_goals + 1)] for _ in range(max_goals + 1)]
    
    # สร้างตารางโอกาสสกอร์บอร์ด (Scoreline Probability Grid)
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            p_x = poisson_pmf(x, lambda_h)
            p_y = poisson_pmf(y, lambda_a)
            tau = d_coles_tau(x, y, lambda_h, lambda_a, rho)
            prob_matrix[x][y] = p_x * p_y * tau
            
    # ปรับความสมดุลของตาราง (Normalization)
    total_p = sum(sum(row) for row in prob_matrix)
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            prob_matrix[x][y] /= total_p
            
    # รวมผลลัพธ์เพื่อหาความน่าจะเป็นชนะ, เสมอ, แพ้
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
# 3. ส่วนทดสอบการทำงาน (Execution)
# =====================================================================
if __name__ == "__main__":
    print("=== [1] ทดสอบระบบถอดค่าน้ำของเจ้ามือ (De-vigging) ===")
    # สมมติราคา 1X2 จากหน้าเว็บเจ้ามือ: Lazio (2.32), Draw (3.21), Napoli (3.59)
    bookie_odds = [2.32, 3.21, 3.59]
    print(f"ราคาหน้าเว็บเจ้ามือ: Home={bookie_odds}, Draw={bookie_odds[1]}, Away={bookie_odds[2]}")
    
    # คำนวณหา Overround สะสม [6, 7]
    margin = (sum(1.0/o for o in bookie_odds) - 1.0) * 100
    print(f"ค่า Overround (อัตราส่วนเกินความน่าจะเป็น): {margin:.2f}%")
    
    # ประมวลผลถอดค่าน้ำ
    p_basic = remove_margin_basic(bookie_odds)
    p_wpo = remove_margin_wpo(bookie_odds)
    
    print("\nความน่าจะเป็นจริง (True Probabilities) หลังหักค่าน้ำออก:")
    print("-> วิธี Basic Multiplicative (เฉลี่ยเท่ากันทุกฝั่ง):")
    for outcome, p in zip(, p_basic):
        print(f"   {outcome}: {p*100:.2f}% | ราคายุติธรรม (Fair Odds): {1.0/p:.3f}")
        
    print("\n-> วิธี Margin Proportional to Odds (WPO - ชดเชยแรงบิดของราคาฝั่งทีมรอง):")
    for outcome, p in zip(, p_wpo):
        print(f"   {outcome}: {p*100:.2f}% | ราคายุติธรรม (Fair Odds): {1.0/p:.3f}")
        
    print("\n" + "="*60 + "\n")
    
    print("=== [2] ทดสอบแบบจำลองคณิตศาสตร์ทำนายผลบอล ===")
    # สมมติค่า xG เฉลี่ยย้อนหลังจากการคำนวณฟอร์มทีม:
    # เจ้าบ้านคาดหวังยิงประตูได้ (lambda_h) = 1.6 ลูก, ทีมเยือนยิงได้ (lambda_a) = 1.2 ลูก
    # ค่าสหสัมพันธ์ประตูน้อย (rho) สำหรับ Dixon-Coles ของฟุตบอลลีกปกติจะอยู่ที่ประมาณ -0.10 ถึง -0.15 [2]
    lambda_h = 1.6
    lambda_a = 1.2
    rho = -0.11
    
    print(f"คาดการณ์อัตราทำประตู (Expected Goals): เจ้าบ้าน={lambda_h}, ทีมเยือน={lambda_a}")
    print(f"Dixon-Coles correlation adjustment (rho): {rho}")
    
    # แบบที่ 1: คำนวณผ่าน Poisson ปกติ (ไม่มีการชดเชยสกอร์ต่ำ)
    p_hw, p_dr, p_aw = calculate_match_odds(lambda_h, lambda_a, rho=0.0)
    print("\nผลลัพธ์จากแบบจำลองพัวซองแบบเดิม (Standard Poisson):")
    print(f"  โอกาสเจ้าบ้านชนะ: {p_hw*100:.2f}%")
    print(f"  โอกาสเสมอ:       {p_dr*100:.2f}%")
    print(f"  โอกาสทีมเยือนชนะ: {p_aw*100:.2f}%")
    
    # แบบที่ 2: คำนวณผ่าน Dixon-Coles (เพิ่มตัวแปรสหสัมพันธ์สกอร์ต่ำ)
    dc_hw, dc_dr, dc_aw = calculate_match_odds(lambda_h, lambda_a, rho=rho)
    print("\nผลลัพธ์จากแบบจำลอง Dixon-Coles (ปรับปรุงสหสัมพันธ์แล้ว):")
    print(f"  โอกาสเจ้าบ้านชนะ: {dc_hw*100:.2f}%")
    print(f"  โอกาสเสมอ (Draw): {dc_dr*100:.2f}% (จะเห็นว่ามีการปรับสัดส่วนในแมตช์สกอร์ต่ำให้แม่นยำขึ้น)")
    print(f"  โอกาสทีมเยือนชนะ: {dc_aw*100:.2f}%")
