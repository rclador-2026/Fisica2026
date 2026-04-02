import os
from google import genai
from flask import Flask, request
import requests
import json

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)
URL_SHEETS = "https://script.google.com/macros/s/AKfycbyTG4V1BcupwWsZ92G8G4QHKtj00jxbVbTDQLacBzexT2AenRii1nPeSG-oIo5S4UYP/exec" # Pon tu URL de Google Apps Script

GRUPOS = ["🔬 Cientifico A", "🔬 Cientifico B", "⚙️ Ingenieria"]
TEMAS_CIENTIFICO = ["📐 Herramientas Matematicas", "🍎 Leyes de Newton", "🚀 Cinematica", "➡️ Movimientos en 1D", "↗️ Movimientos en 2D", "⚡ Trabajo Mecanico y Energia"]
TEMAS_INGENIERIA = ["📐 Herramientas Matematicas", "⚡ Electrostatica", "🔌 Circuitos Electricos", "🧲 Magnetismo", "🔁 Induccion", "⚛️ Fisica Moderna"]
TODOS_LOS_TEMAS = list(set(TEMAS_CIENTIFICO + TEMAS_INGENIERIA))

def verificar_registro(chat_id):
    try:
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
        return "El profesor está en el laboratorio. Intenta en un momento."

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data: return "ok", 200
    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")
    first_name = data["message"]["from"].get("first_name", "Alumno")

    registro = verificar_registro(chat_id)

    # --- REGISTRO SIMPLIFICADO ---
    if not registro.get("existe"):
        # Si elige grupo, lo registramos usando su nombre de Telegram
        if user_text in GRUPOS:
            payload = {"accion": "registro", "alumno": str(chat_id), "nombre": first_name, "grupo": user_text}
            requests.post(URL_SHEETS, json=payload)
            send_message(chat_id, f"¡Hola {first_name}! Te registré en {user_text}. Ya puedes usar el bot. Escribe /start.")
            return "ok", 200
        
        # Si no está registrado, solo le mostramos los grupos
        send_message(chat_id, f"¡Bienvenido {first_name}! Selecciona tu grupo para comenzar:", 
                     reply_markup={"keyboard": [[{"text": g}] for g in GRUPOS], "one_time_keyboard": True, "resize_keyboard": True})
        return "ok", 200

    # --- FLUJO NORMAL ---
    grupo_alumno = registro.get("grupo")

    if user_text == "/start" or "Volver" in user_text:
        temas = TEMAS_CIENTIFICO if "Cientifico" in grupo_alumno else TEMAS_INGENIERIA
        send_message(chat_id, f"Menú de {grupo_alumno}. Elige un tema:", 
                     reply_markup={"keyboard": [[{"text": t}] for t in temas], "resize_keyboard": True})
        return "ok", 200

    # Lógica de temas y acciones (Se mantiene igual que antes)
    tema_elegido = next((t for t in TODOS_LOS_TEMAS if t in user_text), None)
    if tema_elegido and not any(icon in user_text for icon in ["❓", "📝", "📚"]):
        send_message(chat_id, f"Sobre {tema_elegido}, ¿qué quieres hacer?", 
                     reply_markup={"keyboard": [[{"text": f"❓ Ejercicio de {tema_elegido}"}], [{"text": f"📝 Duda sobre {tema_elegido}"}], [{"text": f"📚 Lectura de {tema_elegido}"}], [{"text": "🔙 Volver"}]], "resize_keyboard": True})
        return "ok", 200

    if any(x in user_text for x in ["❓", "📝", "📚"]):
        # Procesar ejercicio/duda/lectura usando el truco del botón
        typing(chat_id)
        res = gemini_generate(user_text)
        send_message(chat_id, res)
        return "ok", 200

    # Consulta libre
    typing(chat_id)
    res = gemini_generate(user_text)
    send_message(chat_id, res)
    return "ok", 200

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup: payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload)

def typing(chat_id):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
