import os
import sqlite3
import logging
import requests
from datetime import datetime
from flask import Flask, request
import anthropic

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TEACHER_CHAT_ID = os.environ.get("TEACHER_CHAT_ID", "")
RENDER_URL = os.environ["RENDER_URL"]

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
flask_app = Flask(__name__)

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
        "ecuaciones": ["ecuacion", "ecuacion", "primer grado", "segundo grado", "raiz", "discriminante"],
        "trigonometria": ["seno", "coseno", "tangente", "pitagoras", "hipotenusa", "angulo", "triangulo"],
        "vectores": ["vector", "colineal", "coplanar", "resultante", "componente"],
        "leyes de newton": ["newton", "fuerza", "masa", "aceleracion", "inercia", "equilibrio"],
        "cinematica": ["velocidad", "posicion", "tiempo", "desplazamiento", "cinematica", "tiro"],
        "movimiento circular": ["circular", "periodo", "frecuencia", "rpm", "angular"],
        "energia": ["energia", "trabajo", "potencia", "joule", "cinetica", "potencial"],
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
    c.execute("SELECT alumno_nombre, COUNT(*) as total FROM mensajes GROUP BY alumno_id, alumno_nombre ORDER BY total DESC")
    alumnos = c.fetchall()
    c.execute("SELECT tema_detectado, COUNT(*) as total FROM mensajes GROUP BY tema_detectado ORDER BY total DESC LIMIT 8")
    temas = c.fetchall()
    c.execute("SELECT alumno_nombre, mensaje, fecha FROM mensajes ORDER BY fecha DESC LIMIT 8")
    recientes = c.fetchall()
    conn.close()
    return alumnos, temas, recientes

def send_message(chat_id, text, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Error enviando mensaje: {e}")

def send_typing(chat_id):
    try:
        requests.post(f"{TELEGRAM_API}/sendChatAction", json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except:
        pass

def handle_start(chat_id, first_name):
    nombre = first_name or "estudiante"
    send_message(chat_id,
        f"Hola {nombre}! Soy tu tutor de matematica y fisica de 5 anio.\n\n"
        "Puedo ayudarte con:\n"
        "- Ecuaciones de 1 y 2 grado\n"
        "- Trigonometria y Pitagoras\n"
        "- Vectores\n"
        "- Leyes de Newton\n"
        "- Cinematica y movimiento circular\n"
        "- Trabajo y energia\n\n"
        "Contame: con que tema queres trabajar hoy?"
    )

def handle_reporte(chat_id, user_id):
    if TEACHER_CHAT_ID and str(user_id) != TEACHER_CHAT_ID:
        send_message(chat_id, "Este comando es solo para el docente.")
        return

    alumnos, temas, recientes = obtener_reporte()

    if not alumnos:
        send_message(chat_id, "Todavia no hay interacciones registradas.")
        return

    texto = "REPORTE DE ACTIVIDAD\n\n"
    texto += "Consultas por alumno:\n"
    for nombre, total in alumnos:
        texto += f"- {nombre}: {total}\n"

    texto += "\nTemas mas consultados:\n"
    for tema, total in temas:
        texto += f"- {tema}: {total} veces\n"

    texto += "\nUltimas consultas:\n"
    for nombre, mensaje, fecha in recientes:
        fecha_corta = fecha[:10]
        msg_corto = (mensaje[:55] + "...") if len(mensaje) > 55 else mensaje
        texto += f"[{fecha_corta}] {nombre}: {msg_corto}\n"

    send_message(chat_id, texto)

def handle_reiniciar(chat_id, user_id):
    conversation_histories.pop(user_id, None)
    send_message(chat_id, "Listo! Empezamos de cero. Con que tema queres arrancar?")

def handle_text(chat_id, user_id, user_name, text):
    if user_id not in conversation_histories:
        conversation_histories[user_id] = []

    history = conversation_histories[user_id]
    history.append({"role": "user", "content": text})

    if len(history) > 20:
        history = history[-20:]
        conversation_histories[user_id] = history

    send_typing(chat_id)

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=history
        )
        reply = response.content[0].text
        history.append({"role": "assistant", "content": reply})
        guardar_interaccion(user_id, user_name, text, reply)
        send_message(chat_id, reply)
    except Exception as e:
        logging.error(f"Error IA: {e}")
        send_message(chat_id, "Tuve un problema tecnico. Intenta de nuevo en un momento.")

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data or "message" not in data:
        return "OK", 200

    message = data["message"]
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    user_name = message["from"].get("first_name", "Alumno")
    text = message.get("text", "")

    if not text:
        return "OK", 200

    if text == "/start":
        handle_start(chat_id, user_name)
    elif text == "/reporte":
        handle_reporte(chat_id, user_id)
    elif text == "/reiniciar":
        handle_reiniciar(chat_id, user_id)
    else:
        handle_text(chat_id, user_id, user_name, text)

    return "OK", 200

@flask_app.route("/")
def health():
    return "Bot activo", 200

def setup_webhook():
    url = f"{RENDER_URL}/webhook"
    resp = requests.post(f"{TELEGRAM_API}/setWebhook", json={"url": url})
    logging.info(f"Webhook configurado: {resp.json()}")

if __name__ == "__main__":
    init_db()
    setup_webhook()
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)
