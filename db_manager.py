import sqlite3
import os
from sre_constants import SUCCESS
from pythainlp.tokenize import word_tokenize, syllable_tokenize
from pythainlp.tag import pos_tag

DB_PATH = 'data/word.db'

def init_db():
    os.makedirs('data', exist_ok=True) # สร้างโฟลเดอร์ data ถ้ายังไม่มี
    
    con = sqlite3.connect(DB_PATH)
    cursor = con.cursor()
    
    # ตารางเก็บคำ
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_text TEXT UNIQUE
        )
    ''')
    
    # ตารางเก็บพยางค์ เชื่อมกับ id ของคำในตาราง words
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS syllables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER,
            syllable_text TEXT NOT NULL,
            FOREIGN KEY (word_id) REFERENCES words(id)
        )
    ''')

    con.commit()
    con.close()

def check_and_save(word, syllables):
    # เช็คว่าคำนามไหม
    if word.startswith("การ") or word.startswith("ความ"): 
        word_type = "NOUN"
        is_noun = True
    else:
        tagged_words = pos_tag([word], corpus = "pud") # [('ไบโอเทคโนโลยี', 'NOUN')]
        word_type = tagged_words[0][1] if tagged_words else "UNKNOWN"    
        is_noun = word_type in ["NOUN", "PROPN"] # คำนามทั่วไปและคำนามเฉพาะ 
    
    if not is_noun:
        return "NOT_NOUN", [{"word_type": word_type}]

    # เช็คว่าซ้ำไหม
    con = sqlite3.connect(DB_PATH)
    cursor = con.cursor()
    cursor.execute('SELECT id FROM words WHERE word_text = ?', (word,))
    if cursor.fetchone(): # คำซ้ำ ไม่ต้องบันทึก
        con.close()
        return "WORD_DUP", [] 
    
    # คำไม่ซ้ำ มาเช็คพยางค์
    duplicate_syllables = []
    for syl in syllables:
        cursor.execute('''
            SELECT words.word_text
            FROM syllables
            JOIN words ON syllables.word_id = words.id
            WHERE syllables.syllable_text = ?
        ''', (syl,))
        syl_match = cursor.fetchone()
        if syl_match:
            duplicate_syllables.append({
                "syllable": syl,
                "from_word": syl_match[0]
            }) 
    if duplicate_syllables:     
        con.close()
        return "SYLLABLE_DUP", duplicate_syllables
    
    # ไม่มีซ้ำเลย บันทึกคำและพยางค์
    cursor.execute('INSERT INTO words (word_text) VALUES (?)', (word,))
    new_word_id = cursor.lastrowid
    for syl in syllables:
        cursor.execute('INSERT INTO syllables (word_id, syllable_text) VALUES (?, ?)', (new_word_id, syl))
    
    con.commit()
    con.close()
    return SUCCESS, []
    
def clear_db():
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        cursor.execute('DELETE FROM syllables')
        cursor.execute('DELETE FROM words')
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="words"') # รีเซ็ต auto-increment ของ words
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="syllables"') # รีเซ็ต auto-increment ของ syllables
    con.close()
    
def get_all_words():
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        cursor.execute('SELECT id, word_text FROM words ORDER BY id DESC')
        return cursor.fetchall()
    
def update_word(word_id, new_word, new_syllables):
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        cursor.execute('UPDATE words SET word_text = ? WHERE id = ?', (new_word, word_id))
        # ลบพยางค์เก่า
        cursor.execute('DELETE FROM syllables WHERE word_id = ?', (word_id,))
        # เพิ่มพยางค์ใหม่
        for syl in new_syllables:
            cursor.execute('INSERT INTO syllables (word_id, syllable_text) VALUES (?, ?)', (word_id, syl))
    con.close()