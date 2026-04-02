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

# URL de Google Apps Script (La que termina en /exec)
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

# ── Lógica de IA (Gemini 2.5 Flash) ───────────────────────────────────────────

def gemini_generate(prompt):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=f"Eres un profesor de física uruguayo. Responde directo, técnico y breve. {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        print(f"Error Gemini: {e}")
        return "El profesor está corrigiendo parciales. Intenta en un minuto."

def guardar_en_sheets(alumno, tema, tipo, consulta):
    if "TU_URL" in URL_SHEETS: return
    payload = {"alumno": str(alumno), "tema": tema, "tipo": tipo, "consulta": consulta}
    try:
        requests.post(URL_SHEETS, json=payload, timeout=8)
    except:
        pass

# ── Webhook Principal ─────────────────────────────────────────────────────────

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data: return "ok", 200

    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")

    # 1. REINICIO TOTAL
    if user_text == "/start" or user_text == "🔙 Volver a grupos":
        send_message(chat_id, "¡Hola! Selecciona tu grupo:", 
                     reply_markup={"keyboard": [[{"text": g}] for g in GRUPOS], "resize_keyboard": True})
        return "ok", 200

    # 2. SELECCIÓN DE GRUPO -> MOSTRAR TEMAS
    if user_text in GRUPOS:
        temas = TEMAS_CIENTIFICO if "Cientifico" in user_text else TEMAS_INGENIERIA
        send_message(chat_id, f"Grupo {user_text}. Elegí un tema:", 
                     reply_markup={"keyboard": [[{"text": t}] for t in temas] + [[{"text": "🔙 Volver a grupos"}]], "resize_keyboard": True})
        return "ok", 200

    # 3. SELECCIÓN DE TEMA -> MOSTRAR LAS 3 ACCIONES (Originales)
    tema_elegido = next((t for t in TODOS_LOS_TEMAS if t in user_text), None)
    # Solo entramos aquí si el texto es el nombre exacto del tema (sin iconos de acción)
    if tema_elegido and not any(icon in user_text for icon in ["❓", "📝", "📚"]):
        send_message(chat_id, f"Has elegido {tema_elegido}. ¿Qué quieres hacer?", 
                     reply_markup={
                         "keyboard": [
                             [{"text": f"❓ Ejercicio de {tema_elegido}"}],
                             [{"text": f"📝 Duda sobre {tema_elegido}"}],
                             [{"text": f"📚 Lectura de {tema_elegido}"}],
                             [{"text": "🔙 Volver a grupos"}]
                         ], "resize_keyboard": True
                     })
        return "ok", 200

    # 4. MANEJO DE ACCIONES (Recuperando el tema del botón)
    
    # ACCIÓN: EJERCICIO
    if "❓ Ejercicio de" in user_text:
        tema = user_text.replace("❓ Ejercicio de ", "")
        typing(chat_id)
        res = gemini_generate(f"Crea un ejercicio de bachillerato sobre {tema}. Solo el enunciado.")
        send_message(chat_id, res)
        guardar_en_sheets(chat_id, tema, "Pedido Ejercicio", "N/A")
        return "ok", 200

    # ACCIÓN: LECTURA (El botón que se había perdido)
    if "📚 Lectura de" in user_text:
        tema = user_text.replace("📚 Lectura de ", "")
        typing(chat_id)
        res = gemini_generate(f"Dime 3 recursos específicos (libros o links) para estudiar {tema}.")
        send_message(chat_id, res)
        guardar_en_sheets(chat_id, tema, "Pedido Lectura", "N/A")
        return "ok", 200

    # ACCIÓN: DUDA (Prepara la captura de la pregunta)
    if "📝 Duda sobre" in user_text:
        tema = user_text.replace("📝 Duda sobre ", "")
        send_message(chat_id, f"Escribí tu duda técnica sobre {tema}:")
        return "ok", 200

    # 5. CAPTURA DE TEXTO LIBRE (Dudas directas)
    if user_text not in GRUPOS and not tema_elegido:
        typing(chat_id)
        res = gemini_generate(user_text)
        send_message(chat_id, res)
        guardar_en_sheets(chat_id, "Consulta General", "Duda", user_text)
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
def typing(chat_id):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction", 
                  json={"chat_id": chat_id, "action": "typing"})

if __name__ == "__main__":
    # Esta es la línea que estaba incompleta
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
