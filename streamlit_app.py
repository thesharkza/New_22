import pandas as pd
import openpyxl
import os

# ล็อกพิกัดโฟลเดอร์อัตโนมัติ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
path_file1 = os.path.join(BASE_DIR, 'test 1.xlsx') # ไฟล์ปลายทาง (ที่จะโดนอัปเดตและเซฟทับ)
path_file2 = os.path.join(BASE_DIR, 'Test 2.xlsx') # ไฟล์ต้นทาง (แหล่งข้อมูล)

# 1. โหลดข้อมูลด้วย Pandas เพื่อใช้คำนวณและจับคู่ข้อมูล
df1 = pd.read_excel(path_file1, header=3) # Target
df2 = pd.read_excel(path_file2, header=3) # Source

# สำรองชื่อคอลัมน์เดิมแบบไม่ตัดแต่งของ test 1 เพื่อใช้หาตำแหน่งคอลลัมน์ใน Excel ตอนเขียนไฟล์
orig_df1_cols = list(df1.columns)

# แปลงชื่อคอลัมน์ทั้งหมดเป็นข้อความ (String) และล้างช่องว่างเพื่อใช้ประมวลผล
df1.columns = df1.columns.astype(str).str.strip()
df2.columns = df2.columns.astype(str).str.strip()

# จัดการชื่อประเทศให้ตรงกันในหน่วยความจำเพื่อใช้จับคู่ข้อมูล
for df in [df1, df2]:
    if 'COUNTRY' in df.columns:
        df['COUNTRY'] = df['COUNTRY'].astype(str).str.strip().str.upper()
        df['COUNTRY'] = df['COUNTRY'].replace({'PHILIPPINE': 'PHILIPPINES'})

# ล้างช่องว่างในคอลัมน์ MODEL CODE
df1['MODEL CODE'] = df1['MODEL CODE'].astype(str).str.strip()
df2['MODEL CODE'] = df2['MODEL CODE'].astype(str).str.strip()

# ตัดคอลัมน์ส่วนเกินของ df1 (ตัวที่จะโดนเขียนทับ) ออกตั้งแต่คำว่า 'case' หรือ 'model' เป็นต้นไป
for idx, col in enumerate(df1.columns):
    if 'case' in col.lower() or col.lower() == 'model':
        df1 = df1.iloc[:, :idx]
        break

# หาคอลัมน์รายเดือนที่มีร่วมกันระหว่างสองไฟล์เพื่อเตรียมดึงข้อมูล
match_keys = ['COUNTRY', 'MODEL CODE']
common_cols = [col for col in df1.columns if col in df2.columns and col not in match_keys]

# ✨ ขั้นตอนสำคัญ: รวมยอด (Sum) ข้อมูลรายเดือนใน Test 2 ที่แตกย่อยตามสี ให้กลับมาเป็น 1 แถวต่อ 1 โมเดล
# ใช้ min_count=1 เพื่อป้องกันไม่ให้ช่องที่ว่างเปล่า (NaN) กลายเป็นเลข 0 (ทำให้รักษาค่าเดิมใน test 1 ได้ถ้าไม่มีข้อมูล)
df2_subset = df2.groupby(match_keys)[common_cols].sum(min_count=1).reset_index()

# ใช้การ Merge แบบ Left Join เพื่อดึงยอดรวมจาก Test 2 มาตั้งรอไว้ตามโครงสร้างแถวของ test 1
df_update_values = df1[match_keys].merge(df2_subset, on=match_keys, how='left')

# สร้าง DataFrame พักข้อมูลที่รวมเสร็จแล้ว
df1_updated_data = df1.copy()
for col in common_cols:
    # ดึงค่าที่รวมได้จาก Test 2 มาใส่ ถ้าไม่มีข้อมูลใน Test 2 ให้ใช้ค่าเดิมของ test 1 (.fillna)
    df1_updated_data[col] = df_update_values[col].fillna(df1[col]).values

# -----------------------------------------------------------------
# ✨ ขั้นตอนนำข้อมูลจาก Test 2 ไปเขียนและบันทึกทับลงในไฟล์ test 1.xlsx ต้นฉบับ
# -----------------------------------------------------------------
print("กำลังนำข้อมูลจาก Test 2 ไปบันทึกทับลงในแบบฟอร์มไฟล์ test 1.xlsx...")

# เปิดไฟล์ test 1 ต้นฉบับขึ้นมาทำงาน (เพื่อรักษา Format สี/ฟอนต์/หัวตารางเดิม)
wb = openpyxl.load_workbook(path_file1)
ws = wb.active 

# กำหนดแถวเริ่มต้นของข้อมูลใน Excel (Header อยู่แถว 4 ข้อมูลเริ่มแถว 5)
START_ROW = 5

# วนลูปเจาะเขียนข้อมูลลงไปในพิกัดเซลล์รายเดือนของไฟล์ test 1
for col_name in common_cols:
    cleaned_orig_cols = [str(c).strip() for c in orig_df1_cols]
    if col_name in cleaned_orig_cols:
        excel_col_idx = cleaned_orig_cols.index(col_name) + 1
        updated_series = df1_updated_data[col_name]
        
        for i, val in enumerate(updated_series):
            excel_row = START_ROW + i
            
            # ถ้าไม่มีค่าให้อัปเดตใหม่ ให้ข้ามไป (เพื่อรักษาค่าดั้งเดิมในช่องนั้นไว้)
            if pd.isna(val):
                continue
                
            # แปลงประเภทข้อมูลให้ถูกต้องก่อนหยอดลงเซลล์ (ไม่ให้ติด .0)
            try:
                if float(val).is_integer():
                    val = int(val)
                else:
                    val = float(val)
            except:
                pass
            
            # สั่งเขียนค่าที่รวมยอดแล้วทับลงไปในช่องเซลล์เดิมของ test 1
            ws.cell(row=excel_row, column=excel_col_idx, value=val)

# บันทึกทับไฟล์ test 1.xlsx ดั้งเดิมทันที
wb.save(path_file1)

print("🎉 สลับฝั่งอัปเดตข้อมูลเรียบร้อย! ข้อมูลจาก Test 2 ถูกบันทึกทับลงในไฟล์ 'test 1.xlsx' สำเร็จแล้วครับ")
