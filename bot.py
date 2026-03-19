import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import from google import genai

# --- CONFIGURACIÓN ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
TEACHER_ID = int(os.environ.get("TEACHER_CHAT_ID", 0))
RENDER_URL = os.environ.get("RENDER_URL")

# Configurar IA de Google
client = genai.Client(api_key="GEMINI_KEY")

# Base de datos temporal (en memoria) para el reporte
# Nota: En Render Free, esto se borra si el bot "duerme" por 15 min.
stats = {"consultas": 0, "alumnos": set(), "temas": []}

# --- LÓGICA DEL BOT ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hola! Soy tu Tutor IA. Preguntame lo que necesites de la materia.\n\nUsa /reiniciar si querés empezar de cero.")

async def reiniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Memoria limpia. ¿En qué puedo ayudarte ahora?")

async def reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == TEACHER_ID:
        resumen = (
            f"📊 **Reporte para el Docente**\n"
            f"- Consultas totales: {stats['consultas']}\n"
            f"- Alumnos activos: {len(stats['alumnos'])}\n"
            f"- Últimos temas: {', '.join(stats['temas'][-5:])}"
        )
        await update.message.reply_text(resumen, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ Comando solo para el docente.")

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # Actualizar estadísticas
    stats["consultas"] += 1
    stats["alumnos"].add(update.effective_user.id)
    stats["temas"].append(user_text[:20]) # Guardamos el inicio del texto como "tema"

      try:
        # Prompt para darle personalidad de tutor
        prompt = f"Actúa como un tutor educativo paciente y claro. Responde a esto: {user_text}"
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
    except Exception as e:
        logging.error(f"Error Gemini: {e}")
        await update.message.reply_text("Lo siento, tuve un problema procesando la respuesta. Reintentá en un momento.")

# --- CONFIGURACIÓN DEL SERVIDOR (WEBHOOK) ---
app = Flask(__name__)
ptb_application = Application.builder().token(TOKEN).build()

@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), ptb_application.bot)
        await ptb_application.process_update(update)
    return "ok", 200

@app.route("/")
def index():
    return "Bot de Tutoría Activo", 200

async def setup_bot():
    # Registrar comandos y mensajes
    ptb_application.add_handler(CommandHandler("start", start))
    ptb_application.add_handler(CommandHandler("reiniciar", reiniciar))
    ptb_application.add_handler(CommandHandler("reporte", reporte))
    ptb_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    
    # Configurar Webhook en Telegram
    await ptb_application.bot.set_webhook(url=f"{RENDER_URL}/{TOKEN}")
    await ptb_application.initialize()
    await ptb_application.start()

# Iniciar procesos
if __name__ == "__main__":
        asyncio.run(main()) # Cambia 'main()' por el nombre de tu función principal
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
