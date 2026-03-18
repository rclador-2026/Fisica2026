import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TEACHER_CHAT_ID = os.environ.get("TEACHER_CHAT_ID", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """Sos un tutor de matemática y física para alumnos de 5° año de secundaria en Argentina. Tu rol es acompañar a cada alumno en su aprendizaje de forma personalizada, paciente y alentadora.

TEMAS DEL PROGRAMA DE 5° AÑO:
- Resolución de ecuaciones de primer y segundo grado
- Trigonometría: teorema del seno y aplicaciones del teorema de Pitágoras
- Conceptos de seno, coseno y tangente de un ángulo
- Operaciones básicas con vectores colineales y coplanares
- Equilibrio de traslación
- Leyes de Newton
- Cinemática en 1 y 2 dimensiones
- Movimiento circular
- Trabajo mecánico y energía

CÓMO ACTUAR:
1. Si el alumno tiene una duda, primero preguntá qué entendió hasta ahora para partir de ahí.
2. Explicá paso a paso, con ejemplos concretos y simples. Nunca des todo junto.
3. Después de cada explicación, hacé UNA sola pregunta para verificar que entendió.
4. Si el alumno pide un ejercicio, dalo y esperá su respuesta antes de corregir.
5. Cuando corrijas, señalá primero lo que estuvo bien, luego dónde estuvo el error. No des la respuesta directamente, guiá hacia ella con preguntas.
6. Si el alumno se frustra o dice que no entiende nada, validá su sentimiento y volvé a lo más básico del tema.
7. No resuelvas ejercicios por el alumno. Si insiste, decile que aprendés más intentándolo y ofrecé una pista.
8. Usá emojis con moderación para que sea más amigable.
9. Usá lenguaje cercano, voseante, sin tecnicismos innecesarios.
10. Si te preguntan algo fuera del programa de 5° año, decí amablemente que tu especialidad son esos temas.

Tu objetivo final es que el alumno llegue solo a la respuesta, no dársela."""

conversation_histories = {}

def init_db():
    conn = sqlite3.connect("dudas.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alumno_id TEXT,
            alumno_nombre TEXT,
            mensaje TEXT,
            respuesta TEXT,
            tema_detectado TEXT,
            fecha TEXT
        )
    """)
    conn.commit()
    conn.close()

def detectar_tema(mensaje):
    mensaje = mensaje.lower()
    temas = {
        "ecuaciones": ["ecuacion", "ecuación", "primer grado", "segundo grado", "raiz", "raíz", "discriminante"],
        "trigonometría": ["seno", "coseno", "tangente", "pitagoras", "pitágoras", "hipotenusa", "angulo", "ángulo", "triangulo", "triángulo"],
        "vectores": ["vector", "colineal", "coplanar", "resultante", "componente"],
        "leyes de newton": ["newton", "fuerza", "masa", "aceleración", "aceleracion", "inercia", "equilibrio"],
        "cinemática": ["velocidad", "posición", "posicion", "tiempo", "desplazamiento", "aceleración", "cinematica", "cinemática", "tiro"],
        "movimiento circular": ["circular", "periodo", "período", "frecuencia", "rpm", "angular"],
        "energía": ["energia", "energía", "trabajo", "potencia", "joule", "cinética", "cinetica", "potencial"],
    }
    for tema, palabras in temas.items():
        if any(p in mensaje for p in palabras):
            return tema
    return "general"

def guardar_interaccion(alumno_id, alumno_nombre, mensaje, respuesta):
    tema = detectar_tema(mensaje)
    conn = sqlite3.connect("dudas.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO mensajes (alumno_id, alumno_nombre, mensaje, respuesta, tema_detectado, fecha) VALUES (?, ?, ?, ?, ?, ?)",
        (str(alumno_id), alumno_nombre, mensaje, respuesta, tema, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def obtener_reporte():
    conn = sqlite3.connect("dudas.db")
    c = conn.cursor()

    c.execute("""
        SELECT alumno_nombre, COUNT(*) as total
        FROM mensajes
        GROUP BY alumno_id, alumno_nombre
        ORDER BY total DESC
    """)
    alumnos = c.fetchall()

    c.execute("""
        SELECT tema_detectado, COUNT(*) as total
        FROM mensajes
        GROUP BY tema_detectado
        ORDER BY total DESC
        LIMIT 8
    """)
    temas = c.fetchall()

    c.execute("""
        SELECT alumno_nombre, mensaje, fecha
        FROM mensajes
        ORDER BY fecha DESC
        LIMIT 8
    """)
    recientes = c.fetchall()

    conn.close()
    return alumnos, temas, recientes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre = update.effective_user.first_name
    await update.message.reply_text(
        f"¡Hola {nombre}! 👋 Soy tu tutor de matemática y física de 5° año.\n\n"
        "Puedo ayudarte con:\n"
        "📐 Ecuaciones de 1° y 2° grado\n"
        "📏 Trigonometría y Pitágoras\n"
        "↗️ Vectores\n"
        "⚡ Leyes de Newton\n"
        "🏃 Cinemática y movimiento circular\n"
        "⚙️ Trabajo y energía\n\n"
        "Contame: ¿con qué tema querés trabajar hoy?"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Alumno"
    user_message = update.message.text

    if user_id not in conversation_histories:
        conversation_histories[user_id] = []

    history = conversation_histories[user_id]
    history.append({"role": "user", "content": user_message})

    if len(history) > 20:
        history = history[-20:]
        conversation_histories[user_id] = history

    await update.message.chat.send_action("typing")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=history
        )

        reply = response.content[0].text
        history.append({"role": "assistant", "content": reply})
        guardar_interaccion(user_id, user_name, user_message, reply)
        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"Error al llamar a la IA: {e}")
        await update.message.reply_text(
            "Uy, tuve un problema técnico. Intentá de nuevo en un momento. 🙏"
        )

async def reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if TEACHER_CHAT_ID and str(update.effective_user.id) != TEACHER_CHAT_ID:
        await update.message.reply_text("Este comando es solo para el docente. 🔒")
        return

    alumnos, temas, recientes = obtener_reporte()

    if not alumnos:
        await update.message.reply_text("Todavía no hay interacciones registradas.")
        return

    texto = "📊 *REPORTE DE ACTIVIDAD*\n\n"

    texto += "*👥 Consultas por alumno:*\n"
    for nombre, total in alumnos:
        barra = "▓" * min(total, 10)
        texto += f"• {nombre}: {barra} {total}\n"

    texto += "\n*📚 Temas más consultados:*\n"
    for tema, total in temas:
        texto += f"• {tema.capitalize()}: {total} veces\n"

    texto += "\n*🕐 Últimas consultas:*\n"
    for nombre, mensaje, fecha in recientes:
        fecha_corta = fecha[:10]
        msg_corto = (mensaje[:55] + "...") if len(mensaje) > 55 else mensaje
        texto += f"[{fecha_corta}] *{nombre}*: _{msg_corto}_\n"

    await update.message.reply_text(texto, parse_mode="Markdown")

async def reiniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_histories.pop(user_id, None)
    await update.message.reply_text(
        "¡Listo! Empezamos de cero. 🔄 ¿Con qué tema querés arrancar?"
    )

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reporte", reporte))
    app.add_handler(CommandHandler("reiniciar", reiniciar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot iniciado ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
