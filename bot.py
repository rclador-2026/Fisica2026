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

# ── Listas de Datos ───────────────────────────────────────────────────────────
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
        "keyboard": [
            [{"text": "🔬 Cientifico A"}],
            [{"text": "🔬 Cientifico B"}],
            [{"text": "⚙️ Ingenieria"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
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

# ── Lógica de IA (Gemini) ─────────────────────────────────────────────────────

def gemini_generate(prompt):
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=f"Eres un profesor de física uruguayo. Responde DIRECTO, sin saludos ni introducciones. Máximo 2 párrafos. {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        print(f"Error en Gemini: {e}")
        return "Lo siento, tuve un problema al pensar la respuesta. Intenta de nuevo."

def build_prompt(tema, accion, user_text=None):
    if accion == OP_EJERCICIO:
        return f"Crea un ejercicio de nivel bachillerato sobre {tema}. Solo el enunciado."
    elif accion == OP_LECTURA:
        return f"Dime 3 libros o sitios web específicos para estudiar {tema}."
    elif accion == OP_PREGUNTA:
        return f"Explica brevemente esto sobre {tema}: {user_text}"
    return f"Respuesta corta sobre {user_text}"

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
    if not data or "message" not in data:
        return "ok", 200

    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")
    
    if chat_id not in user_state:
        user_state[chat_id] = {}

    # 1. COMANDO INICIAL / RESET
    if user_text == "/start" or user_text == "🔙 Volver a grupos":
        user_state[chat_id] = {}
        send_message(chat_id, "¡Hola! Selecciona tu grupo para comenzar:", reply_markup=keyboard_grupos())
        return "ok", 200

    # 2. SELECCIÓN DE GRUPO
    if user_text in GRUPOS_CIENTIFICO or user_text in GRUPOS_INGENIERIA:
        user_state[chat_id]["grupo"] = user_text
        send_message(chat_id, f"Has elegido {user_text}. Elige un tema:", reply_markup=get_keyboard_temas(chat_id))
        return "ok", 200

    # 3. VOLVER A TEMAS
    if user_text == OP_VOLVER:
        send_message(chat_id, "Elige un tema de la lista:", reply_markup=get_keyboard_temas(chat_id))
        return "ok", 200

    # 4. SELECCIÓN DE TEMAS
    if user_text in TODOS_LOS_TEMAS:
        user_state[chat_id]["tema"] = user_text
        send_message(chat_id, f"Tema: {user_text}. ¿Qué quieres hacer?", reply_markup=keyboard_acciones())
        return "ok", 200

    # 5. ACCIONES (EJERCICIO, LECTURA, PREGUNTA)
    if user_text in ACCIONES:
        tema = user_state[chat_id].get("tema")
        if not tema:
            send_message(chat_id, "Primero selecciona un tema.", reply_markup=get_keyboard_temas(chat_id))
            return "ok", 200
        
        if user_text == OP_PREGUNTA:
            user_state[chat_id]["ultima_accion"] = OP_PREGUNTA
            send_message(chat_id, "Escribe tu duda técnica y te responderé en un momento:")
        else:
            typing(chat_id)
            res = gemini_generate(build_prompt(tema, user_text))
            send_message(chat_id, res, reply_markup=keyboard_acciones())
        return "ok", 200

    # 6. CAPTURAR DUDA LIBRE
    if user_state[chat_id].get("ultima_accion") == OP_PREGUNTA:
        tema = user_state[chat_id].get("tema")
        typing(chat_id)
        res = gemini_generate(build_prompt(tema, OP_PREGUNTA, user_text))
        user_state[chat_id]["ultima_accion"] = None 
        send_message(chat_id, res, reply_markup=keyboard_acciones())
        return "ok", 200

    return "ok", 200

@app.route('/')
def index():
    return "Bot funcionando correctamente", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
