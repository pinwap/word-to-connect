import sqlite3
import os
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
    
    # ตารางเก็บคะแนน
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            score INTEGER,
            status TEXT DEFAULT 'ALIVE' -- สถานะผู้เล่น (ALIVE, ELIMINATED, WINNER)
        )
    ''')

    con.commit()
    con.close()

# ---------- คำศัพท์ ----------
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
    return "SUCCESS", []

def force_save(word, syllables):
    # ให้ moderator ตัดสินว่าคำนั้นถูกไหม
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute('INSERT OR IGNORE INTO words (word_text) VALUES (?)', (word,))
        cur.execute('SELECT id FROM words WHERE word_text = ?', (word,))
        word_id = cur.fetchone()[0]
        
        for syl in syllables:
            cur.execute('INSERT INTO syllables (word_id, syllable_text) VALUES (?, ?)', (word_id, syl))
        con.commit()
    
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
        con.commit()

def delete_word(word_id):
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        cursor.execute('DELETE FROM words WHERE id = ?', (word_id,))
        cursor.execute('DELETE FROM syllables WHERE word_id = ?', (word_id,))
        con.commit()
    
# ---------- ผู้เล่น ----------
def add_player(name):
    try:
        with sqlite3.connect(DB_PATH) as con:
            cursor = con.cursor()
            cursor.execute('INSERT INTO players (name) VALUES (?)', (name.strip(),))
            con.commit()
        return True
    except sqlite3.IntegrityError:
        return False # ชื่อซ้ำ

def get_all_players():
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute('SELECT id, name, score, status FROM players ORDER BY id ASC')
        return cur.fetchall()
    
def get_alive_player():
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute('SELECT id, name, score FROM players WHERE status = "ALIVE"')
        return cur.fetchall()

def add_point(player_id, points):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute('UPDATE players SET score = score + ? WHERE id = ?', (points, player_id))
        con.commit()

def eliminate_player(player_id):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute('UPDATE players SET status = "ELIMINATED" WHERE id = ?', (player_id,))
        con.commit()
        
def killed_check_score(player_id,top,top_point,winner_point):
    eliminate_player(player_id)
    alive_players = get_alive_player()
    
    if(len(alive_players)==top):
        for p_id,_,p_score in alive_players:
            add_point(p_id, top_point)
        return f"TOP {top}:", alive_players
    elif(len(alive_players)==1):
        winner_id, winner_name, winner_score = alive_players[0]
        add_point(winner_id, winner_point)
        return f"WINNER: {winner_name}", alive_players
    return f"CONTINUED:", alive_players
        
# -------- clear ----------
def reset_game_round():
    # เริ่มเกมใหม่ รีเซ็ตสถานะทุกคน แต่เก็บคะแนนสะสมไว้
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        cursor.execute('DELETE FROM syllables')
        cursor.execute('DELETE FROM words')
        cursor.execute('DELETE FROM sqlite_sequence WHERE name IN ("words", "syllables")') # รีเซ็ต auto-increment ของ words และ syllables
        cursor.execute('UPDATE players SET status = "ALIVE"') 
        con.commit()
    con.close()
    
def clear_all_data():
    # ลบทุกอย่างจริงๆ รวมผู้เล่นและคะแนน
    reset_game_round()
    with sqlite3.connect(DB_PATH) as con:
        cursor = con.cursor()
        cursor.execute('DELETE FROM players')
        cursor.execute('DELETE FROM sqlite_sequence WHERE name = "players"') # รีเซ็ต auto-increment ของทุกตาราง
        con.commit()