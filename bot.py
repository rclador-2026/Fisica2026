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

# ── Funciones de Teclados (Interface) ─────────────────────────────────────────

def keyboard_grupos():
    return {
        "keyboard": [[{"text": g}] for g in (GRUPOS_CIENTIFICO + ["⚙️ Ingenieria"])],
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

# ── Helpers de Registro (Google Sheets) ───────────────────────────────────────

def guardar_en_sheets(alumno, tema, tipo, consulta):
    # REEMPLAZA ESTO con tu URL de Google Apps Script
    URL_SHEETS = "https://script.google.com/macros/s/AKfycbyd7P-N5FmzaO4WBC87vVRTwAKfgYF1SGvLkzdjT4lt0cc-Mm-OYxDpHo3KO1tQloFU/exec"
    
    payload = {
        "alumno": str(alumno),
        "tema": tema,
        "tipo": tipo,
        "consulta": consulta
    }
    try:
        requests.post(URL_SHEETS, json=payload, timeout=5)
    except:
        print("Error de conexión con Sheets")

# ── Lógica de IA (Gemini 2.0 Flash) ───────────────────────────────────────────

def gemini_generate(prompt):
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=f"Eres un profesor de física uruguayo de secundaria. Responde directo al grano, sin saludos innecesarios. {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        return f"Error en la conexión con el profesor virtual: {e}"

def build_prompt(tema, accion, user_text=None):
    if accion == OP_EJERCICIO:
        return f"Genera un ejercicio técnico de {tema} para nivel bachillerato. Solo el enunciado."
    elif accion == OP_LECTURA:
        return f"Recomienda 3 libros o recursos web específicos para estudiar {tema}."
    elif accion == OP_PREGUNTA:
        return f"Explica brevemente este concepto de {tema}: {user_text}"
    return f"Responde sobre {user_text}"

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
    
    state = user_state[chat_id]

    # 1. Comandos de Navegación e Inicio
    if user_text == "/start" or user_text == "🔙 Volver a grupos":
        user_state[chat_id] = {}
        send_message(chat_id, "¡Bienvenido! Selecciona tu grupo:", reply_markup=keyboard_grupos())
        return "ok", 200

    if user_text in GRUPOS_CIENTIFICO or user_text == "⚙️ Ingenieria":
        user_state[chat_id]["grupo"] = user_text
        send_message(chat_id, f"Grupo {user_text}. Elige un tema:", reply_markup=get_keyboard_temas(chat_id))
        return "ok", 200

    if user_text == OP_VOLVER:
        send_message(chat_id, "Elige un tema de la lista:", reply_markup=get_keyboard_temas(chat_id))
        return "ok", 200

    # 2. Selección de Temas
    if user_text in TODOS_LOS_TEMAS:
        user_state[chat_id]["tema"] = user_text
        send_message(chat_id, f"Has elegido {user_text}. ¿Qué quieres hacer?", reply_markup=keyboard_acciones())
        return "ok", 200

    # 3. Acciones de Botón (IA Directa)
    if user_text in ACCIONES:
        tema = state.get("tema")
        if not tema:
            send_message(chat_id, "Primero selecciona un tema.", reply_markup=get_keyboard_temas(chat_id))
            return "ok", 200
        
        if user_text == OP_PREGUNTA:
            user_state[chat_id]["ultima_accion"] = OP_PREGUNTA
            send_message(chat_id, "Dime tu duda técnica sobre este tema:")
        else:
            typing(chat_id)
            res = gemini_generate(build_prompt(tema, user_text))
            # Opcional: guardar que pidió un ejercicio
            guardar_en_sheets(chat_id, tema, user_text, "Solicitud de contenido")
            send_message(chat_id, res, reply_markup=keyboard_acciones())
        return "ok", 200

    # 4. Captura de Duda (Procesamiento de texto libre)
    if state.get("ultima_accion") == OP_PREGUNTA:
        tema = state.get("tema")
        typing(chat_id)
        res = gemini_generate(build_prompt(tema, OP_PREGUNTA, user_text))
        
        # GUARDAR CONSULTA EN GOOGLE SHEETS
        guardar_en_sheets(chat_id, tema, "Duda Alumno", user_text)
        
        user_state[chat_id]["ultima_accion"] = None 
        send_message(chat_id, res, reply_markup=keyboard_acciones())
        return "ok", 200

    return "ok", 200

@app.route('/')
def index():
    return "Bot de Física Activo", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
