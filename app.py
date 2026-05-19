import streamlit as st
import speech_recognition as sr
from pythainlp.tokenize import syllable_tokenize, word_tokenize
import db_manager as db
import os

st.set_page_config(page_title="เกมคำต้องเชื่อม", page_icon="🎮", layout="centered")
st.title("เกมคำต้องเชื่อม")

db.init_db() 

# ------ session state ------
if "pause" not in st.session_state:
    st.session_state.paused = False
if "word_to_process" not in st.session_state:
    st.session_state.word_to_process = ""
    
# ------ pause/resume game
col_btn1, col_btn2 = st.columns(2)
with col_btn1: #ปุ่ม restart
    if st.button("restart (clear database)", type="secondary"):
        db.clear_db()
        st.session_state.paused = False
        st.session_state.word_to_process = ""
        st.success("Database cleared! Game restarted.")
        st.rerun()
        
with col_btn2: #ปุ่ม pause/resume
    if st.session_state.paused:
        if st.button("resume"):
            st.session_state.paused = False
            st.rerun()
    else:
        if st.button("pause"):
            st.session_state.paused = True    
            st.rerun()

st.write("---")

if st.session_state.paused:
    st.warning("เกมหยุดชั่วคราวอยู่! กรุณากดปุ่ม 'resume' เพื่อเล่นต่อ")

def handle_text_submit():
    st.session_state.word_to_process = st.session_state.text_input_key # เอาคำที่พิมพ์มาเก็บใน session state
    st.session_state.text_input_key = "" # เคลียร์ช่อง input หลัง submit

# ----------------------------------------
#             input new word 
# ----------------------------------------
# speech recognition 
st.subheader("ป้อนคำใหม่ด้วยเสียง (ภาษาไทยเท่านั้น)")

if st.button("กดเพื่อพูด(พูดเสร็จจะประมวลผลคำให้อัตโนมัติ)", disabled=st.session_state.paused, use_container_width=True):
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        st.toast("กำลังฟัง... กรุณาพูดคำใหม่ของคุณ")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)  # ปรับเสียงรบกวนรอบข้าง
        try:
            audio_data = recognizer.listen(source, timeout=4, phrase_time_limit=3)  # ฟังเสียงจากไมโครโฟน phase_time_limit คือเวลาสูงสุดที่รอให้พูดเสร็จ (วินาที)
            
            recorded_text = recognizer.recognize_google(audio_data, language="th-TH")
            
            st.write(f"คุณพูดว่า: {recorded_text}")
            st.session_state.word_to_process = recorded_text
        except sr.WaitTimeoutError:
            st.error("หมดเวลา คุณไม่ได้พูดอะไร ลองกดปุ่มแล้วพูดใหม่อีกครั้ง")
        except sr.UnknownValueError:
            st.error("ไม่สามารถเข้าใจเสียงที่บันทึกได้ ลองกดอัดเสียงแล้วพูดใหม่อีกครั้งชัดๆ")
        except Exception as e:
            st.error(f"ไมโครโฟนมีปัญหา: {e}")
    
# พิมพ์มือ
st.text_input("ป้อนคำใหม่ (ภาษาไทยเท่านั้น):", 
              placeholder="เช่น: ไบโอเทคโนโลยี", 
              disabled=st.session_state.paused,
              key="text_input_key",
              on_change=handle_text_submit # เมื่อกด enter จะเรียกฟังก์ชันนี้
              )

# ------ process new word ----------
if st.session_state.word_to_process and not st.session_state.paused:
    current_word = st.session_state.word_to_process
    st.session_state.word_to_process = "" # เคลียร์คำที่ประมวลผลแล้วออกจาก session state
    
    main_word = current_word.replace(" ", "").strip() # เอาช่องว่างออกทั้งหมดเพื่อประมวลผลคำหลัก
    if main_word:
        # คำซ้ำ
        syllables = syllable_tokenize(main_word) # แยกพยางค์จากคำใหม่
        st.write(f"คำ: {main_word} | พยางค์: {syllables}")
        
        status, details = db.check_and_save(main_word, syllables)
        if status == "NOT_NOUN":
            word_type = details[0]["word_type"] if details else "UNKNOWN"
            st.error(f"คำ '{main_word}' ไม่ใช่คำนาม เป็นคำประเภท '{word_type}'")
        elif status == "WORD_DUP":
            st.warning(f"คำ '{main_word}' ซ้ำในฐานข้อมูลแล้ว!")
        elif status == "SYLLABLE_DUP":
            for dup in details:
                st.warning(f"พยางค์ '{dup['syllable']}' ซ้ำกับคำเดิม '{dup['from_word']}'")
        else:
            st.success(f"เพิ่มคำ '{main_word}' และพยางค์ {syllables} ลงฐานข้อมูลเรียบร้อย!")
            st.rerun() # รีเฟรชหน้าเพื่อแสดงคำใหม่ในฐานข้อมูล
            
st.write("---")


# ------ แสดงคำทั้งหมดในฐานข้อมูล + แก้ ------
st.subheader("คำทั้งหมดในฐานข้อมูล (แก้ไขคำผิดได้ที่นี่)")
all_words = db.get_all_words()
if not all_words:
    st.info("ยังไม่มีคำใดๆ ในฐานข้อมูล")
else:
    for word_id, word_text in all_words:
        col1, col2 = st.columns([4, 1])
        with col1:
            edited_text = st.text_input(f"คำที่ {word_id}:", value=word_text, key=f"edit_{word_id}", label_visibility="collapsed")
        with col2:
            if st.button("บันทึก", key=f"save_{word_id}"):
                if edited_text != word_text:
                    # อัพเดตคคำ พยางค์ และเช็คซ้ำใหม่
                    new_syls = syllable_tokenize(edited_text)
                    db.update_word(word_id, edited_text, new_syls)
                    st.success(f"อัพเดตคำที่ {word_id} เป็น '{edited_text}' เรียบร้อย!")
                    st.rerun()