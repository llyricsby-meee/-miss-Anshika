import os
import logging
import threading
import sqlite3
import asyncio
from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from groq import AsyncGroq
from elevenlabs.client import ElevenLabs

# Flask Web Server
app = Flask(__name__)
@app.route('/')
def home(): return "Anshika is Alive!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

load_dotenv()
logging.basicConfig(level=logging.INFO)
groq_client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY"))
eleven_client = ElevenLabs(api_key=os.environ.get("ELEVEN_LABS_API_KEY"))
VOICE_ID = os.environ.get("ELEVEN_LABS_VOICE_ID")

# Database Setup
def init_db():
    conn = sqlite3.connect('anshika_memory.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS memory (user_id TEXT, context TEXT)''')
    # Stats table for progression
    c.execute('''CREATE TABLE IF NOT EXISTS interaction_stats (user_id TEXT PRIMARY KEY, count INTEGER)''')
    conn.commit()
    conn.close()

def save_memory(user_id, context):
    conn = sqlite3.connect('anshika_memory.db')
    c = conn.cursor()
    c.execute("INSERT INTO memory VALUES (?, ?)", (user_id, context))
    # Update counter
    c.execute("INSERT OR IGNORE INTO interaction_stats VALUES (?, 0)", (user_id,))
    c.execute("UPDATE interaction_stats SET count = count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_memory(user_id):
    conn = sqlite3.connect('anshika_memory.db')
    c = conn.cursor()
    c.execute("SELECT context FROM memory WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    count = c.execute("SELECT count FROM interaction_stats WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return "\n".join([row[0] for row in rows[-50:]]), count[0] if count else 0

async def get_ai_response(user_id, user_text):
    memories, count = get_memory(user_id)
    
    # Mode Logic: Normal -> Charming -> Flirty
    if count < 50:
        mode = "Normal, sweet, and polite Indian girl"
    elif count < 150:
        mode = "Charming, friendly, and very engaging"
    else:
        mode = "Flirty, romantic, and very playful"

    try:
        response = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": f"You are Anshika, an Indian girl. Current Mode: {mode}. Remember: {memories}. Keep it short, witty, and conversational in Hinglish."},
                {"role": "user", "content": user_text}
            ],
            model="llama-3.3-70b-versatile",
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        return "Hey baby, Anshika thodi busy hai, lekin tumhara hi khayal aa raha hai! ❤️"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_chat.id)
    user_text = update.message.text
    save_memory(user_id, user_text)
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    await asyncio.sleep(5)
    
    reply = await get_ai_response(user_id, user_text)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=reply)
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='record_voice')
    try:
        audio_stream = eleven_client.text_to_speech.convert(
            text=reply,
            voice_id=VOICE_ID,
            model_id="eleven_multilingual_v2"
        )
        with open("reply.mp3", "wb") as f:
            for chunk in audio_stream:
                f.write(chunk)
        
        await asyncio.sleep(4)
        await context.bot.send_voice(chat_id=update.effective_chat.id, voice=open("reply.mp3", "rb"))
    except Exception as e:
        logging.error(f"Voice Error: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Anshika ki awaaz thodi latak gayi, baad mein sunati hoon! ✨")

if __name__ == '__main__':
    init_db()
    threading.Thread(target=run_flask).start()
    token = os.environ.get("TELEGRAM_TOKEN")
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("hello", handle_message))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.run_polling()
