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

# ── CONFIGURACIÓN DE GOOGLE SHEETS ────────────────────────────────────────────
# Pega aquí la URL que termina en /exec
URL_SHEETS = "https://script.google.com/macros/s/AKfycbxsNPbeJH4OoFb78cwtRERAfiJ64yeRpd4WpR2ceqX1kEjtuQT8sc0Ynu3BFcuAbnaN/exec"

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
    # Validamos que la URL no sea la de ejemplo
    if "TU_URL_AQUI" in URL_SHEETS:
        print("Error: No se ha configurado la URL de Google Sheets.")
        return

    payload = {
        "alumno": str(alumno), 
        "tema": tema, 
        "tipo": tipo, 
        "consulta": consulta
    }
    try:
        # Enviamos como JSON para que el Apps Script lo reciba correctamente
        r = requests.post(URL_SHEETS, json=payload, timeout=10)
        print(f"Sheets Response: {r.status_code}")
    except Exception as e:
        print(f"Error al enviar a Sheets: {e}")

# ── Lógica de IA (Gemini 2.5) ─────────────────────────────────────────────────

def gemini_generate(prompt):
    try:
        # Corregido: Usamos el modelo que te funciona (2.5)
        response = client.models.generate_content(
            model="gemini-2.5", 
            contents=f"Eres un profesor de física uruguayo. Responde DIRECTO, sin saludos ni introducciones. Máximo 2 párrafos. {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        print(f"Error Gemini: {e}")
        return "Lo siento, tuve un problema al conectar con mi cerebro virtual. Intenta de nuevo."

def build_prompt(tema, accion, user_text=None):
    if accion == OP_EJERCICIO:
        return f"Crea un ejercicio de nivel bachillerato sobre {tema}. Solo el enunciado."
    elif accion == OP_LECTURA:
        return f"Dime 3 recursos específicos (libros o webs) para estudiar {tema}."
    elif accion == OP_PREGUNTA:
        return f"Responde esta duda técnica de un alumno sobre {tema}: {user_text}"
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
    if not data or "message" not in data:
        return "ok", 200

    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")
    
    if chat_id not in user_state:
        user_state[chat_id] = {}

    # 1. COMANDOS DE INICIO / RESET
    if user_text == "/start" or user_text == "🔙 Volver a grupos":
        user_state[chat_id] = {} 
        send_message(chat_id, "¡Bienvenido, Profe! Selecciona tu grupo:", reply_markup=keyboard_grupos())
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

    # 4. SELECCIÓN DE TEMAS (Detección Blindada)
    tema_encontrado = None
    for t in TODOS_LOS_TEMAS:
        if t in user_text:
            tema_encontrado = t
            break
            
    if tema_encontrado:
        user_state[chat_id]["tema"] = tema_encontrado
        send_message(chat_id, f"Has elegido {tema_encontrado}. ¿Qué quieres hacer?", reply_markup=keyboard_acciones())
        return "ok", 200

    # 5. ACCIONES DE BOTÓN
    if user_text in ACCIONES:
        tema_actual = user_state[chat_id].get("tema")
        
        if not tema_actual:
            send_message(chat_id, "Primero selecciona un tema de la lista.", reply_markup=get_keyboard_temas(chat_id))
            return "ok", 200
        
        if user_text == OP_PREGUNTA:
            user_state[chat_id]["ultima_accion"] = OP_PREGUNTA
            send_message(chat_id, "Dime tu duda técnica sobre este tema:")
        else:
            typing(chat_id)
            res = gemini_generate(build_prompt(tema_actual, user_text))
            # Opcional: Registrar también cuando piden ejercicios
            guardar_en_sheets(chat_id, tema_actual, user_text, "Consulta Generada")
            send_message(chat_id, res, reply_markup=keyboard_acciones())
        return "ok", 200

    # 6. CAPTURA DE PREGUNTA LIBRE
    if user_state[chat_id].get("ultima_accion") == OP_PREGUNTA:
        tema_actual = user_state[chat_id].get("tema", "General")
        typing(chat_id)
        res = gemini_generate(build_prompt(tema_actual, OP_PREGUNTA, user_text))
        
        # Guardamos en Sheets
        guardar_en_sheets(chat_id, tema_actual, "Duda Alumno", user_text)
        
        user_state[chat_id]["ultima_accion"] = None 
        send_message(chat_id, res, reply_markup=keyboard_acciones())
        return "ok", 200

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
