import streamlit as st
import speech_recognition as sr
from pythainlp.tokenize import syllable_tokenize, word_tokenize
import db_manager as db
import os

st.set_page_config(page_title="เกมคำต้องเชื่อม", page_icon="🎮", layout="wide")
st.title("เกมคำต้องเชื่อม")

# -------- คะแนนเกม ---------
TOP = 3
TOP_POINT = 1
WINNER_POINT = 3

db.init_db() 

# Inject CSS ย้อมสีปุ่ม (เริ่มรอบใหม่ = น้ำเงิน | New Game = เขียว)
st.markdown("""
<style>
    div[data-testid="stButton"] button:has(div p:contains("เริ่มรอบใหม่")) {
        background-color: #1E3A8A !important; color: white !important;
    }
    div[data-testid="stButton"] button:has(div p:contains("New Game (ล้างระบบ)")) {
        background-color: #065F46 !important; color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# ------ session state ------
if "pause" not in st.session_state:
    st.session_state.paused = False # ใช้เก็บสถานะเกมว่าหยุดชั่วคราวหรือไม่
if "word_to_process" not in st.session_state:
    st.session_state.word_to_process = "" # ใช้เก็บคำที่รอการประมวลผล พิมพ์หรือพูด
if "pending_action" not in st.session_state:
    st.session_state.pending_action = None # ใช้เก็บคำที่รอการยืนยันจาก Moderator
if "game_alert" not in st.session_state:
    st.session_state.game_alert = None # เก็บข้อความบอกรายชื่อ+ผู้ชนะ
if "player_queue" not in st.session_state:
    st.session_state.player_queue = [] # เก็บลิสต์ ID ผู้เล่น ตามคิว
if "current_turn_player" not in st.session_state:
    st.session_state.current_turn_player = None # ปักธงว่า ID ผู้เล่นไหนกำลังเล่นอยู่

# ----------------------------------------
#             players
# ----------------------------------------
with st.sidebar:
    st.header('Players Board')
    # เพิ่มผู้เล่น
    with st.form("add_player_form", clear_on_submit=True):
        new_player_name = st.text_input("ชื่อผู้เล่นใหม่:", placeholder="เช่น: Alice")
        submit_btn = st.form_submit_button("เพิ่มผู้เล่น")
        if submit_btn and new_player_name.strip():
            db.add_player(new_player_name.strip())
            st.rerun()
    
    st.write("---")
    st.subheader("คะแนนและสถานะผู้เล่น")
    players = db.get_all_players()
    if players:
        for p_id, p_name, p_score, p_status in players:
            if p_status == "ALIVE":
                st.write(f"💚 **{p_name}** - คะแนน: {p_score}")
            else:
                st.write(f"💔 **{p_name}** - คะแนน: {p_score}")
    else:
        st.info("ยังไม่มีผู้เล่นในระบบ")
    
    st.write("---")
    # ------ reset, pause game ------
    st.subheader("Moderator Console")
    if st.button("เริ่มรอบใหม่", use_container_width=True):
        db.reset_game_round()
        st.session_state.pending_action = None
        st.session_state.game_alert = None
        st.success("เริ่มรอบใหม่แล้ว! สถานะผู้เล่นถูกรีเซ็ต แต่คะแนนสะสมยังอยู่")
        st.rerun()
    if st.button("new game", use_container_width=True):
        db.clear_all_data()
        st.session_state.pending_action = None
        st.session_state.game_alert = None
        st.success("เริ่มเกมใหม่แล้ว! ข้อมูลทั้งหมดถูกลบและรีเซ็ต")
        st.rerun()
    if st.button("pause/resume", use_container_width=True):
        st.session_state.paused = not st.session_state.paused
        st.rerun()

st.write("---")

if st.session_state.paused:
    st.warning("เกมหยุดชั่วคราวอยู่! กรุณากดปุ่ม 'resume' เพื่อเล่นต่อ")

if st.session_state.game_alert:
    st.success(f"ประกาศผล: {st.session_state.game_alert}")

def handle_text_submit():
    st.session_state.word_to_process = st.session_state.text_input_key # เอาคำที่พิมพ์มาเก็บใน session state
    st.session_state.text_input_key = "" # เคลียร์ช่อง input หลัง submit

def sync_players_turn(shift = False):
    alive_players = db.get_alive_player()
    alive_id = [p[0] for p in alive_players]
    
    if not alive_id:
        st.session_state.player_queue = []
        return None
    
    # ตัดคนที่ตายออก
    st.session_state.player_queue = [pid for pid in st.session_state.player_queue if pid in alive_id]
    for pid in alive_id:
        if pid not in st.session_state.player_queue:
            st.session_state.player_queue.append(pid)
    
    # ถ้า shift=True ให้เลื่อนไปคนถัดไปในคิว
    if shift and st.session_state.player_queue:
        st.session_state.current_turn_player = (st.session_state.current_turn_player + 1) % len(st.session_state.player_queue) if st.session_state.current_turn_player is not None else 0
    
    if st.session_state.player_queue:
        st.session_state.current_turn_player %= len(st.session_state.player_queue)
        return st.session_state.player_queue[st.session_state.current_turn_player]
    return None

active_player_id = sync_players_turn(shift=False) # เริ่มเกมให้คนแรกในคิวเล่นก่อน

st.subheader(f"ลำดับการเล่น")
alive_player = db.get_alive_player()
if alive_player:
    player_dict = {p[0]: (p[1], p[2]) for p in alive_player} # id: (name, score)
    
    queue = [f"{player_dict[pid]}" if pid==active_player_id else player_dict[pid] 
             for pid in st.session_state.player_queue if pid in player_dict]
    st.markdown(" -> ".join(queue))
    
    col_rev, col_order = st.columns([1,2])
    with col_rev:
        if st.button("reverse", use_container_width=True):
            st.session_state.player_queue.reverse()
            st.session_state.current_turn_player = 0 # ปักธงให้คนแรกในคิวเล่นต่อ
            st.rerun()
    # จัดคิวเอง
    with col_order:
        options_map = {p[1]: p[0] for p in alive_player} # name: id
        custom_order = st.multiselect("จัดลำดับผู้เล่นเอง (เลือกเรียงลำดับ 1->2->3):",
                                        options=list(options_map.keys()),
                                        default=[player_dict[pid] for pid in st.session_state.player_queue if pid in player_dict]
                                        )
        new_queue_ids = [options_map[name] for name in custom_order]
        if new_queue_ids != st.session_state.player_queue and len(new_queue_ids) == len(st.session_state.player_queue):
            st.session_state.player_queue = new_queue_ids
            st.session_state.current_turn_player = 0 # ปักธงให้คนแรกในคิวเล่นต่อ
            st.rerun()
    current_player_name = player_dict.get(active_player_id, "Unknown")
else:
    st.warning("ไม่มีผู้เล่นในระบบ")
            
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
              ).strip()

# ------ process new word ----------
if st.session_state.word_to_process and not st.session_state.paused:
    current_word = st.session_state.word_to_process
    st.session_state.word_to_process = "" # เคลียร์คำที่ประมวลผลแล้วออกจาก session state
    
    main_word = current_word.replace(" ", "").strip() # เอาช่องว่างออกทั้งหมดเพื่อประมวลผลคำหลัก
    if main_word:
        syllables = syllable_tokenize(main_word) # แยกพยางค์จากคำใหม่
        st.write(f"คำ: {main_word} | พยางค์: {syllables}")
        
        status, details = db.check_and_save(main_word, syllables)
        if status == "NOT_NOUN":
            word_type = details[0]["word_type"] if details else "UNKNOWN"
            # st.error(f"คำ '{main_word}' ไม่ใช่คำนาม เป็นคำประเภท '{word_type}'")
            st.session_state.pending_action = {
                "word": main_word,
                "syllables": syllables,
                "word_type": word_type,
                "player_id": active_player_id,
                "player_name": current_player_name,
                "details": details
            }
        elif status == "WORD_DUP":
            st.warning(f"คำ '{main_word}' ซ้ำในฐานข้อมูลแล้ว!")
        elif status == "SYLLABLE_DUP":
            for dup in details:
                st.warning(f"พยางค์ '{dup['syllable']}' ซ้ำกับคำเดิม '{dup['from_word']}'")
        else:
            st.session_state.pending_action = None
            sync_players_turn(shift=True) # เลื่อนไปคนถัดไปในคิว
            st.success(f"เพิ่มคำ '{main_word}' และพยางค์ {syllables} ลงฐานข้อมูลเรียบร้อย!")
            st.rerun() # รีเฟรชหน้าเพื่อแสดงคำใหม่ในฐานข้อมูล
 
if st.session_state.pending_action:
    act = st.session_state.pending_action
    st.error(f"คำ '{act['word']}' ไม่ใช่คำนาม เป็นคำประเภท '{act['word_type']}'")
    # ให้ Moderator ตัดสินใจ
    confirm, deny = st.columns(2)
    with confirm:
        if st.button("นี่คือคำนาม", type="secondary", use_container_width=True):
            db.force_save(act["word"], act["syllables"])
            st.success(f"เพิ่มคำ '{act['word']}' ลงฐานข้อมูลแล้ว (แม้จะไม่ใช่คำนาม)")
            st.session_state.pending_action = None
            st.rerun()
    with deny:
        if st.button("นี่ไม่ใช่คำนาม", type="secondary", use_container_width=True):
            res_text = db.killed_check_score(act["player_id"], top=TOP, top_point=TOP_POINT, winner_point=WINNER_POINT)
            st.session_state.game_alert = res_text
            st.session_state.pending_action = None
            sync_players_turn(shift=False) 
            st.rerun()
            
st.write("---")


# ------ แสดงคำทั้งหมดในฐานข้อมูล + แก้ ------
st.subheader("คำทั้งหมดในฐานข้อมูล (แก้ไขคำผิดได้ที่นี่)")
all_words = db.get_all_words()
if not all_words:
    st.info("ยังไม่มีคำใดๆ ในฐานข้อมูล")
else:
    for word_id, word_text in all_words:
        col1, col2, col3 = st.columns([4, 1, 1])
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
        with col3:
            if st.button("ลบ", key=f"delete_{word_id}"):
                db.delete_word(word_id)
                st.success(f"ลบคำที่ {word_id} '{word_text}' เรียบร้อย!")
                st.rerun()