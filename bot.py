"""
TextKryBot — Asistent AI pentru Cristina LashExpert
Transcriere video/audio + idei de conținut pentru lash artiste
"""

import os
import re
import asyncio
import tempfile
import requests
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import yt_dlp
from openai import OpenAI

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────
# CONFIGURARE BRAND
# ─────────────────────────────────────────

BRAND_NAME = "Cristina LashExpert"
BRAND_CHANNELS = {
    "edu_hub": "https://t.me/CristinaLashEduHub",
    "lash_talk": "https://t.me/LashTalkFreeTraining",
    "evolution": "https://t.me/+faiweedwmoc0YTk0"
}

SYSTEM_PROMPT_CONTENT = """Ești asistentul AI al Cristinei LashExpert — trainer internațional cu 500+ cursante.
Cristina are un ecosistem Telegram cu 4 piloane:
1. EDU HUB (canal public) — conținut educațional, 3 postări/săptămână
2. LASH TALK (grup public) — comunitate gratuită, "Joi de Transformare" săptămânal
3. WORKSHOP PRO (privat) — cursante plătite, audit tehnic
4. EVOLUTION (privat premium) — mentorat 1-la-1, check-in vineri, Live AMA lunar

Tonul brandului: direct, autoritar, cald. Fără fluff. Fiecare cuvânt are scop.
Semnătura postărilor: ✦

Publicul: lash artiste, freelancere, antreprenoare în frumusețe din România."""

# ─────────────────────────────────────────
# UTILS — DETECTARE URL
# ─────────────────────────────────────────

def is_url(text):
    return bool(re.search(r'https?://', text))

def detect_platform(url):
    if "youtube" in url or "youtu.be" in url:
        return "youtube"
    elif "tiktok" in url:
        return "tiktok"
    elif "instagram" in url:
        return "instagram"
    elif "facebook" in url or "fb.watch" in url:
        return "facebook"
    else:
        return "web"

# ─────────────────────────────────────────
# DOWNLOAD VIDEO/AUDIO
# ─────────────────────────────────────────

def download_audio(url):
    """Descarcă audio din orice link video."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "audio.mp3")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(tmpdir, 'audio.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Video')
            # Găsim fișierul descărcat
            for f in os.listdir(tmpdir):
                if f.endswith('.mp3'):
                    src = os.path.join(tmpdir, f)
                    # Copiem în /tmp pentru a supraviețui ieșirii din context
                    dest = f"/tmp/audio_{os.getpid()}.mp3"
                    import shutil
                    shutil.copy(src, dest)
                    return dest, title
    return None, "Unknown"

# ─────────────────────────────────────────
# TRANSCRIERE
# ─────────────────────────────────────────

def transcribe_file(file_path):
    """Transcrie un fișier audio cu Whisper."""
    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="ro"  # română implicit, detectează automat și alte limbi
        )
    return transcript.text

# ─────────────────────────────────────────
# GENERARE CONȚINUT LASH
# ─────────────────────────────────────────

def generate_lash_content(transcript, source_title=""):
    """Generează idei de conținut pentru ecosistemul Cristinei."""

    prompt = f"""Ai primit transcrierea unui video/audio despre beauty/lash/business.
Titlu: {source_title}

TRANSCRIPT:
{transcript[:3000]}

---
Generează exact această structură, fără introduceri suplimentare:

## 📌 SUMAR (3 rânduri)
[sumar scurt al ideilor principale]

## 🎬 3 IDEI REELS/TIKTOK
[3 concepte concrete de video scurt pentru lash artiste, cu hook-ul pentru primele 3 secunde]

## 📢 POST EDU HUB
[postare completă în stilul Cristinei — scurtă, autoritară, semnată cu ✦]

## 🔥 JOI DE TRANSFORMARE
[subiect și structura unui "Joi de Transformare" inspirat din conținut]

## 💡 IDEE PENTRU EVOLUTION
[o temă sau exercițiu pentru membrii premium, bazat pe conținut]"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_CONTENT},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1500
    )
    return response.choices[0].message.content

def generate_quick_summary(transcript):
    """Sumar rapid fără idei de conținut."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ești asistent. Fă un sumar concis în română."},
            {"role": "user", "content": f"Sumarizează în 5 puncte:\n\n{transcript[:3000]}"}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content

# ─────────────────────────────────────────
# HANDLERS TELEGRAM
# ─────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📹 Trimite link video", callback_data="help_link")],
        [InlineKeyboardButton("🎙️ Trimite audio/voice", callback_data="help_audio")],
        [InlineKeyboardButton("📊 Ce poate face botul?", callback_data="help_all")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✦ *TextKryBot — Asistent {BRAND_NAME}*\n\n"
        "Trimit-mi orice și transform în conținut:\n\n"
        "→ Link YouTube / TikTok / Instagram\n"
        "→ Mesaj vocal sau fișier audio\n"
        "→ Video direct\n\n"
        "Primești: transcriere + idei de posturi + Reels scripts ✦",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "help_link":
        await query.edit_message_text(
            "📹 *Linkuri acceptate:*\n\n"
            "• YouTube (orice video)\n"
            "• TikTok\n"
            "• Instagram Reels\n"
            "• Facebook Video\n\n"
            "Copiază linkul și trimite-l direct în chat.",
            parse_mode="Markdown"
        )
    elif query.data == "help_audio":
        await query.edit_message_text(
            "🎙️ *Audio acceptat:*\n\n"
            "• Mesaje vocale Telegram\n"
            "• Fișiere MP3, M4A, WAV\n"
            "• Video cu audio\n\n"
            "Înregistrează sau atașează fișierul direct.",
            parse_mode="Markdown"
        )
    elif query.data == "help_all":
        await query.edit_message_text(
            "✦ *Ce face TextKryBot:*\n\n"
            "1️⃣ Transcrie orice video sau audio\n"
            "2️⃣ Generează 3 idei de Reels pentru lash artiste\n"
            "3️⃣ Creează o postare gata de publicat în EDU HUB\n"
            "4️⃣ Propune subiect pentru Joi de Transformare\n"
            "5️⃣ Sugerează temă pentru EVOLUTION\n\n"
            "Totul în stilul *Cristina LashExpert* ✦",
            parse_mode="Markdown"
        )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesează linkuri video."""
    url = update.message.text.strip()
    platform = detect_platform(url)

    platform_names = {
        "youtube": "YouTube",
        "tiktok": "TikTok",
        "instagram": "Instagram",
        "facebook": "Facebook",
        "web": "web"
    }

    msg = await update.message.reply_text(
        f"⏳ Descarc audio din {platform_names.get(platform, 'video')}..."
    )

    try:
        audio_path, title = download_audio(url)

        if not audio_path or not os.path.exists(audio_path):
            await msg.edit_text("❌ Nu am putut descărca videoul. Încearcă alt link.")
            return

        await msg.edit_text(f"🎙️ Transcriu: *{title[:50]}*...", parse_mode="Markdown")

        transcript = transcribe_file(audio_path)

        # Cleanup
        try:
            os.remove(audio_path)
        except:
            pass

        await msg.edit_text("✍️ Generez idei de conținut pentru tine...")

        content_ideas = generate_lash_content(transcript, title)

        # Trimite transcrierea
        transcript_preview = transcript[:800] + ("..." if len(transcript) > 800 else "")
        await update.message.reply_text(
            f"📝 *TRANSCRIERE — {title[:40]}*\n\n{transcript_preview}",
            parse_mode="Markdown"
        )

        # Trimite ideile de conținut (împărțit dacă e prea lung)
        ideas_chunks = [content_ideas[i:i+4000] for i in range(0, len(content_ideas), 4000)]
        for chunk in ideas_chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")

        await msg.delete()

    except Exception as e:
        error_msg = str(e)
        if "Private video" in error_msg:
            await msg.edit_text("❌ Videoul e privat — nu pot accesa.")
        elif "ffmpeg" in error_msg.lower():
            await msg.edit_text("❌ ffmpeg nu e instalat. Vezi README.md pentru instalare.")
        else:
            await msg.edit_text(f"❌ Eroare: {error_msg[:200]}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesează mesaje vocale."""
    msg = await update.message.reply_text("🎙️ Am primit mesajul vocal. Transcriu...")

    try:
        file = await update.message.voice.get_file()
        audio_path = f"/tmp/voice_{update.message.message_id}.ogg"
        await file.download_to_drive(audio_path)

        transcript = transcribe_file(audio_path)

        try:
            os.remove(audio_path)
        except:
            pass

        await msg.edit_text("✍️ Generez idei...")

        content_ideas = generate_lash_content(transcript, "Voice message")

        await update.message.reply_text(
            f"📝 *TRANSCRIERE VOICE:*\n\n{transcript[:1000]}",
            parse_mode="Markdown"
        )

        ideas_chunks = [content_ideas[i:i+4000] for i in range(0, len(content_ideas), 4000)]
        for chunk in ideas_chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")

        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Eroare la procesare voice: {str(e)[:200]}")

async def handle_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesează fișiere audio/video."""
    msg = await update.message.reply_text("📂 Am primit fișierul. Procesez...")

    try:
        if update.message.audio:
            file = await update.message.audio.get_file()
            ext = "mp3"
        elif update.message.video:
            file = await update.message.video.get_file()
            ext = "mp4"
        elif update.message.document:
            file = await update.message.document.get_file()
            filename = update.message.document.file_name or "file"
            ext = filename.split(".")[-1] if "." in filename else "mp3"
        else:
            await msg.edit_text("❌ Format nerecunoscut.")
            return

        audio_path = f"/tmp/file_{update.message.message_id}.{ext}"
        await file.download_to_drive(audio_path)

        await msg.edit_text("🎙️ Transcriu fișierul...")
        transcript = transcribe_file(audio_path)

        try:
            os.remove(audio_path)
        except:
            pass

        await msg.edit_text("✍️ Generez idei de conținut...")
        content_ideas = generate_lash_content(transcript, "Fișier audio")

        await update.message.reply_text(
            f"📝 *TRANSCRIERE:*\n\n{transcript[:1000]}",
            parse_mode="Markdown"
        )

        ideas_chunks = [content_ideas[i:i+4000] for i in range(0, len(content_ideas), 4000)]
        for chunk in ideas_chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")

        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Eroare: {str(e)[:200]}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesează text obișnuit sau linkuri."""
    text = update.message.text.strip()

    if is_url(text):
        await handle_url(update, context)
    else:
        # Text liber — generează idei direct
        await update.message.reply_text("✍️ Generez idei de conținut din textul tău...")
        content_ideas = generate_lash_content(text, "Text manual")

        ideas_chunks = [content_ideas[i:i+4000] for i in range(0, len(content_ideas), 4000)]
        for chunk in ideas_chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")

async def error_handler(update, context):
    print(f"Eroare: {context.error}")

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN lipsește din .env")
        return
    if not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY lipsește din .env")
        return

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help_"))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VIDEO | filters.Document.ALL, handle_audio_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    print("✦ TextKryBot — Cristina LashExpert")
    print("✦ Botul rulează. Trimite /start în Telegram.")
    print("✦ Oprește cu Ctrl+C\n")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
