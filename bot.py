import logging
import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from google import genai  # Nueva librería

# --- CONFIGURACIÓN ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
API_KEY = os.environ.get("GEMINI_API_KEY")

# Inicializar cliente de Google GenAI
client = genai.Client(api_key=API_KEY)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Diccionario simple para estadísticas (opcional)
stats = {"consultas": 0, "alumnos": set(), "temas": []}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! Soy tu tutor de Física. ¿En qué puedo ayudarte hoy?")

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    # Actualizar estadísticas
    stats["consultas"] += 1
    stats["alumnos"].add(update.effective_user.id)
    stats["temas"].append(user_text[:20])

    try:
        # Prompt con personalidad
        prompt = f"Actúa como un tutor educativo paciente y claro. Responde a esto: {user_text}"
        
        # Nueva forma de llamar a Gemini
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        await update.message.reply_text(response.text)

    except Exception as e:
        logging.error(f"Error Gemini: {e}")
        await update.message.reply_text("Lo siento, tuve un problema procesando la respuesta. Reintentá en un momento.")

# --- CONFIGURACIÓN DEL SERVIDOR (WEBHOOK) ---
app = Flask(__name__)

# Definimos la aplicación de Telegram de forma global
ptb_application = ApplicationBuilder().token(TOKEN).build()

@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), ptb_application.bot)
        await ptb_application.process_update(update)
        return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot de Física en funcionamiento", 200

async def main():
    # Configurar los handlers
    ptb_application.add_handler(CommandHandler("start", start))
    ptb_application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), responder))
    
    # IMPORTANTE: En Render con Webhook, inicializamos la app pero no usamos run_polling
    await ptb_application.initialize()
    
    # Aquí Flask se encarga del servidor, por lo que este async main
    # sirve para preparar el bot de Telegram antes de que entren los requests.
    logging.info("Bot inicializado correctamente.")

# --- ARRANQUE COMPATIBLE CON PYTHON 3.14 ---
if __name__ == "__main__":
    # Primero inicializamos el bot de forma asíncrona
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
    
    # Luego arrancamos Flask en el puerto que pide Render
    if __name__ == "__main__":
    # Esto solo se ejecuta si corres "python bot.py" manualmente
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
