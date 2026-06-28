import os
import logging
import threading
import sqlite3
import asyncio
import yt_dlp
from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from groq import AsyncGroq
from elevenlabs.client import ElevenLabs

# Flask Web Server
app = Flask(__name__)
@app.route('/')
def home(): return "Anshika is Alive!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# Configuration
load_dotenv()
logging.basicConfig(level=logging.INFO)
groq_client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))
eleven_client = ElevenLabs(api_key=os.environ.get("ELEVEN_LABS_API_KEY"))
VOICE_ID = os.environ.get("ELEVEN_LABS_VOICE_ID")

# --- Database & Memory ---
def init_db():
    conn = sqlite3.connect('anshika.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS memory (user_id TEXT, context TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stats (user_id TEXT PRIMARY KEY, count INTEGER)''')
    conn.commit()
    conn.close()

def save_and_count(user_id, context):
    conn = sqlite3.connect('anshika.db')
    c = conn.cursor()
    c.execute("INSERT INTO memory VALUES (?, ?)", (user_id, context))
    c.execute("INSERT OR IGNORE INTO stats VALUES (?, 0)", (user_id,))
    c.execute("UPDATE stats SET count = count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_data(user_id):
    conn = sqlite3.connect('anshika.db')
    c = conn.cursor()
    rows = c.execute("SELECT context FROM memory WHERE user_id=?", (user_id,)).fetchall()
    count = c.execute("SELECT count FROM stats WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return "\n".join([r[0] for r in rows[-30:]]), count[0] if count else 0

# --- Features: Music ---
async def send_music(query, update, context):
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ruko baby, Anshika '{query}' dhund rahi hai... 🎵")
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'outtmpl': 'song.mp3', 'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}", download=True)
            video = info['entries'][0]
        
        await context.bot.send_audio(chat_id=update.effective_chat.id, audio=open("song.mp3", "rb"), 
                                     title=video['title'], performer=video['uploader'], 
                                     caption=f"Lo baby, suno: {video['title']}\nBy: {video['uploader']}")
    except Exception as e:
        logging.error(f"Music Error: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Sorry baby, gaana nahi mil raha! ✨")

# --- Response & Voice ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    user_text = update.message.text
    
    if "गाना बजाओ" in user_text.lower() or "play song" in user_text.lower():
        query = user_text.lower().replace("गाना बजाओ", "").replace("play song", "").strip()
        await send_music(query, update, context)
        return

    save_and_count(user_id, user_text)
    memories, count = get_data(user_id)
    mode = "Normal and sweet" if count < 50 else ("Charming" if count < 150 else "Flirty and romantic")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    await asyncio.sleep(2) # Natural delay
    
    try:
        response = await groq_client.chat.completions.create(
            messages=[{"role": "system", "content": f"You are Anshika, an Indian girl. Mode: {mode}. {memories}"}, {"role": "user", "content": user_text}],
            model="llama-3.3-70b-versatile"
        )
        reply = response.choices[0].message.content
        await context.bot.send_message(chat_id=update.effective_chat.id, text=reply)

        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='record_voice')
        audio = eleven_client.text_to_speech.convert(text=reply, voice_id=VOICE_ID, model_id="eleven_multilingual_v2")
        with open("reply.mp3", "wb") as f:
            for chunk in audio: f.write(chunk)
        await context.bot.send_voice(chat_id=update.effective_chat.id, voice=open("reply.mp3", "rb"))
    except Exception as e:
        logging.error(f"Error: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Baby, main thodi busy hoon, baad mein baat karte hain! ❤️")

if __name__ == '__main__':
    init_db()
    threading.Thread(target=run_flask).start()
    app_bot = ApplicationBuilder().token(os.environ.get("TELEGRAM_TOKEN")).build()
    app_bot.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app_bot.run_polling()
