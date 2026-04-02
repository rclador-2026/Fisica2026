import os
from google import genai
from flask import Flask, request
import requests
import json

app = Flask(__name__)

# ── Configuración de Variables de Entorno ─────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)

# ── Estado en memoria ─────────────────────────────────────────────────────────
user_state = {}

# ── Listas de Datos (Temas y Grupos) ──────────────────────────────────────────
GRUPOS_CIENTIFICO = ["🔬 Cientifico A", "🔬 Cientifico B"]
GRUPOS_INGENIERIA = ["⚙️ Ingenieria"]

TEMAS_CIENTIFICO = [
    "📐 Herramientas Matematicas", "🍎 Leyes de Newton", "🚀 Cinematica", 
    "➡️ Movimientos en 1D", "↗️ Movimientos en 2D", "⚡ Trabajo Mecanico y Energia"
]

TEMAS_INGENIERIA = [
    "📐 Herramientas Matematicas", "⚡ Electrostatica", "🔌 Circuitos Electricos", 
    "🧲 Magnetismo", "🔁 Induccion", "⚛️ Fisica Moderna"
]

TODOS_LOS_TEMAS = set(TEMAS_CIENTIFICO + TEMAS_INGENIERIA)

# ── Botones de Acción ─────────────────────────────────────────────────────────
OP_EJERCICIO = "❓ Ponme un ejercicio"
OP_PREGUNTA = "📝 Preguntale al profesor"
OP_LECTURA = "📚 Donde leo de este tema"
OP_VOLVER = "🔙 Volver a temas"

ACCIONES = [OP_EJERCICIO, OP_PREGUNTA, OP_LECTURA]

# ── Funciones de Teclados ─────────────────────────────────────────────────────

def keyboard_grupos():
    return {
        "keyboard": [[{"text": g}] for g in (GRUPOS_CIENTIFICO + GRUPOS_INGENIERIA)],
        "resize_keyboard": True
    }

def get_keyboard_temas(chat_id):
    grupo = user_state.get(chat_id, {}).get("grupo", "")
    temas = TEMAS_CIENTIFICO if grupo in GRUPOS_CIENTIFICO else TEMAS_INGENIERIA
    return {
        "keyboard": [[{"text": t}] for t in temas] + [[{"text": "🔙 Volver a grupos"}]],
        "resize_keyboard": True
    }

def keyboard_acciones():
    return {
        "keyboard": [
            [{"text": OP_EJERCICIO}],
            [{"text": OP_PREGUNTA}],
            [{"text": OP_LECTURA}],
            [{"text": OP_VOLVER}]
        ],
        "resize_keyboard": True
    }

# ── Registro en Google Sheets ─────────────────────────────────────────────────

def guardar_en_sheets(alumno, tema, tipo, consulta):
    # REEMPLAZA ESTO con tu URL de Google Apps Script
    URL_SHEETS = "https://script.google.com/macros/s/TU_ID_AQUI/exec"
    payload = {"alumno": str(alumno), "tema": tema, "tipo": tipo, "consulta": consulta}
    try:
        requests.post(URL_SHEETS, json=payload, timeout=5)
    except:
        pass

# ── Lógica de IA (Gemini 1.5 Flash - Más Estable) ─────────────────────────────

def gemini_generate(prompt):
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=f"Eres un profesor de física uruguayo. Responde DIRECTO, sin saludos ni introducciones. Máximo 2 párrafos. {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        print(f"Error Gemini: {e}")
        return "Lo siento, tuve un problema al pensar la respuesta. Intenta de nuevo."

def build_prompt(tema, accion, user_text=None):
    if accion == OP_EJERCICIO:
        return f"Crea un ejercicio de nivel bachillerato sobre {tema}. Solo el enunciado."
    elif accion == OP_LECTURA:
        return f"Dime 3 recursos específicos para estudiar {tema}."
    elif accion == OP_PREGUNTA:
        return f"Responde esta duda técnica sobre {tema}: {user_text}"
    return f"Explica brevemente: {user_text}"

# ── Helpers de Telegram ───────────────────────────────────────────────────────

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

def typing(chat_id):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction", 
                  json={"chat_id": chat_id, "action": "typing"})

# ── Webhook Principal ─────────────────────────────────────────────────────────

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "
