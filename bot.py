import os
from google import genai
from flask import Flask, request
import requests
import json

app = Flask(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)

# URL de tu Google Apps Script (Debe terminar en /exec)
URL_SHEETS = "https://script.google.com/macros/s/AKfycbxsNPbeJH4OoFb78cwtRERAfiJ64yeRpd4WpR2ceqX1kEjtuQT8sc0Ynu3BFcuAbnaN/exec"

# ── Listas de Datos ───────────────────────────────────────────────────────────
GRUPOS = ["🔬 Cientifico A", "🔬 Cientifico B", "⚙️ Ingenieria"]
TEMAS_CIENTIFICO = [
    "📐 Herramientas Matematicas", "🍎 Leyes de Newton", "🚀 Cinematica", 
    "➡️ Movimientos en 1D", "↗️ Movimientos en 2D", "⚡ Trabajo Mecanico y Energia"
]
TEMAS_INGENIERIA = [
    "📐 Herramientas Matematicas", "⚡ Electrostatica", "🔌 Circuitos Electricos", 
    "🧲 Magnetismo", "🔁 Induccion", "⚛️ Fisica Moderna"
]
TODOS_LOS_TEMAS = list(set(TEMAS_CIENTIFICO + TEMAS_INGENIERIA))

# Estado temporal solo para el proceso de registro inicial
user_state = {}

# ── Funciones Core ────────────────────────────────────────────────────────────

def verificar_registro(chat_id):
    try:
        # Consulta al doGet del Script de Google
        r = requests.get(f"{URL_SHEETS}?id={chat_id}", timeout=5)
        return r.json() 
    except:
        return {"existe": False}

def gemini_generate(prompt):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=f"Eres un profesor de física uruguayo. Responde directo y breve. {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except:
        return "El profesor está ocupado. Intenta en un momento."

def guardar_en_sheets(alumno_id, grupo, tema, tipo, consulta):
    payload = {
        "accion": "consulta",
        "alumno": str(alumno_id),
        "grupo": grupo,
        "tema": tema,
        "tipo": tipo,
        "consulta": consulta
    }
    try:
        requests.post(URL_SHEETS, json=payload, timeout=5)
    except:
        pass

# ── Webhook Principal ─────────────────────────────────────────────────────────

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data: return "ok", 200

    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")

    # 1. VERIFICAR SI EL ALUMNO YA ESTÁ REGISTRADO
    registro = verificar_registro(chat_id)

    # --- FLUJO DE REGISTRO (SI NO EXISTE) ---
    if not registro.get("existe"):
        if chat_id not in user_state: user_state[chat_id] = {}

        # Paso A: Pedir Nombre
        if "esperando_nombre" not in user_state[chat_id] and user_text != "/start":
            user_state[chat_id]["esperando_nombre"] = True
            send_message(chat_id, "¡Hola! Soy tu tutor de Física. No te encuentro registrado. ¿Cuál es tu nombre completo?")
            return "ok", 200

        # Paso B: Guardar Nombre y Pedir Grupo
        if user_state[chat_id].get("esperando_nombre"):
            user_state[chat_id]["nombre"] = user_text
            user_state[chat_id]["esperando_nombre"] = False
            send_message(chat_id, f"Gracias, {user_text}. Ahora selecciona tu grupo:", 
                         reply_markup={"keyboard": [[{"text": g}] for g in GRUPOS], "resize_keyboard": True})
            return "ok", 200

        # Paso C: Guardar Grupo y Finalizar Registro en Google
        if user_text in GRUPOS:
            nombre = user_state[chat_id].get("nombre")
            payload = {"accion": "registro", "alumno": str(chat_id), "nombre": nombre, "grupo": user_text}
            requests.post(URL_SHEETS, json=payload)
            
            send_message(chat_id, f"¡Registro exitoso, {nombre}! Ya puedes usar el bot. Escribe /start para ver los temas.")
            user_state.pop(chat_id, None) # Limpiamos memoria temporal
            return "ok", 200

        send_message(chat_id, "Por favor, escribe tu nombre para comenzar.")
        return "ok", 200

    # --- FLUJO NORMAL (SI YA EXISTE) ---
    nombre_alumno = registro.get("nombre")
    grupo_alumno = registro.get("grupo")

    # A. REINICIO / TEMAS
    if user_text == "/start" or "Volver" in user_text:
        temas = TEMAS_CIENTIFICO if "Cientifico" in grupo_alumno else TEMAS_INGENIERIA
        send_message(chat_id, f"Hola {nombre_alumno} ({grupo_alumno}). Elige un tema:", 
                     reply_markup={"keyboard": [[{"text": t}] for t in temas], "resize_keyboard": True})
        return "ok", 200

    # B. SELECCIÓN DE TEMA -> MOSTRAR ACCIONES
    tema_elegido = next((t for t in TODOS_LOS_TEMAS if t in user_text), None)
    if tema_elegido and not any(icon in user_text for icon in ["❓", "📝", "📚"]):
        send_message(chat_id, f"Sobre {tema_elegido}, ¿qué quieres hacer?", 
                     reply_markup={
                         "keyboard": [
                             [{"text": f"❓ Ejercicio de {tema_elegido}"}],
                             [{"text": f"📝 Duda sobre {tema_elegido}"}],
                             [{"text": f"📚 Lectura de {tema_elegido}"}],
                             [{"text": "🔙 Volver"}]
                         ], "resize_keyboard": True
                     })
        return "ok", 200

    # C. PROCESAR ACCIONES (Técnica Anti-Amnesia)
    if "❓ Ejercicio de" in user_text:
        tema = user_text.replace("❓ Ejercicio de ", "")
        typing(chat_id)
        res = gemini_generate(f"Crea un ejercicio de bachillerato sobre {tema}.")
        send_message(chat_id, res)
        guardar_en_sheets(chat_id, grupo_alumno, tema, "Ejercicio", "N/A")
        return "ok", 200

    if "📚 Lectura de" in user_text:
        tema = user_text.replace("📚 Lectura de ", "")
        typing(chat_id)
        res = gemini_generate(f"Dime 3 recursos para estudiar {tema}.")
        send_message(chat_id, res)
        guardar_en_sheets(chat_id, grupo_alumno, tema, "Lectura", "N/A")
        return "ok", 200

    if "📝 Duda sobre" in user_text:
        tema = user_text.replace("📝 Duda sobre ", "")
        send_message(chat_id, f"Escribe tu duda técnica sobre {tema}:")
        return "ok", 200

    # D. CAPTURA DE PREGUNTA LIBRE
    if user_text not in GRUPOS and not tema_elegido:
        typing(chat_id)
        res = gemini_generate(user_text)
        send_message(chat_id, res)
        guardar_en_sheets(chat_id, grupo_alumno, "Consulta General", "Duda", user_text)
        return "ok", 200

    return "ok", 200

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup: payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

def typing(chat_id):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction", 
                  json={"chat_id": chat_id, "action": "typing"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
