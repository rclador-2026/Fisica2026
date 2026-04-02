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

# PEGA TU URL DE APPS SCRIPT AQUÍ
URL_SHEETS = "TU_URL_AQUI"

# ── Listas de Datos ───────────────────────────────────────────────────────────
GRUPOS = ["🔬 Cientifico A", "🔬 Cientifico B", "⚙️ Ingenieria"]
TEMAS_CIENTIFICO = ["📐 Herramientas Matematicas", "🍎 Leyes de Newton", "🚀 Cinematica", "➡️ Movimientos en 1D", "↗️ Movimientos en 2D", "⚡ Trabajo Mecanico y Energia"]
TEMAS_INGENIERIA = ["📐 Herramientas Matematicas", "⚡ Electrostatica", "🔌 Circuitos Electricos", "🧲 Magnetismo", "🔁 Induccion", "⚛️ Fisica Moderna"]
TODOS_LOS_TEMAS = list(set(TEMAS_CIENTIFICO + TEMAS_INGENIERIA))

# ── Lógica de IA y Sheets ─────────────────────────────────────────────────────

def gemini_generate(prompt):
    try:
        response = client.models.generate_content(
            model="gemini-2.5 flash", 
            contents=f"Eres un profesor de física uruguayo. Responde directo y breve: {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except:
        return "El profesor está ocupado. Intenta en un minuto."

def guardar_en_sheets(alumno, tema, tipo, consulta):
    if "TU_URL" in URL_SHEETS: return
    payload = {"alumno": str(alumno), "tema": tema, "tipo": tipo, "consulta": consulta}
    try: requests.post(URL_SHEETS, json=payload, timeout=5)
    except: pass

# ── Webhook Principal ─────────────────────────────────────────────────────────

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data: return "ok", 200

    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")

    # 1. REINICIO
    if user_text == "/start" or "Volver" in user_text:
        send_message(chat_id, "¡Hola! Selecciona tu grupo:", 
                     reply_markup={"keyboard": [[{"text": g}] for g in GRUPOS], "resize_keyboard": True})
        return "ok", 200

    # 2. SELECCIÓN DE GRUPO -> MOSTRAR TEMAS
    if user_text in GRUPOS:
        temas = TEMAS_CIENTIFICO if "Cientifico" in user_text else TEMAS_INGENIERIA
        send_message(chat_id, f"Grupo {user_text}. Elige un tema:", 
                     reply_markup={"keyboard": [[{"text": t}] for t in temas] + [[{"text": "🔙 Volver"}]], "resize_keyboard": True})
        return "ok", 200

    # 3. SELECCIÓN DE TEMA -> MOSTRAR ACCIONES
    # Buscamos si el texto del usuario coincide con algún tema
    tema_elegido = next((t for t in TODOS_LOS_TEMAS if t in user_text), None)
    if tema_elegido:
        # El truco: el bot responde confirmando el tema para que quede en el historial
        send_message(chat_id, f"Has elegido {tema_elegido}. ¿Qué quieres hacer?", 
                     reply_markup={
                         "keyboard": [
                             [{"text": f"❓ Ejercicio de {tema_elegido}"}],
                             [{"text": f"📝 Duda sobre {tema_elegido}"}],
                             [{"text": "🔙 Volver"}]
                         ], "resize_keyboard": True
                     })
        return "ok", 200

    # 4. MANEJO DE ACCIONES (Aquí leemos el tema directamente del botón)
    if "❓ Ejercicio de" in user_text:
        tema = user_text.replace("❓ Ejercicio de ", "")
        res = gemini_generate(f"Dame un ejercicio de {tema}")
        send_message(chat_id, res)
        return "ok", 200

    if "📝 Duda sobre" in user_text:
        tema = user_text.replace("📝 Duda sobre ", "")
        # Guardamos temporalmente en memoria SOLO para la siguiente respuesta
        # Si se borra aquí, el impacto es mínimo comparado con antes
        global ultima_consulta_tema
        ultima_consulta_tema = tema 
        send_message(chat_id, f"Escribe tu duda sobre {tema}:")
        return "ok", 200

    # 5. CAPTURA DE PREGUNTA LIBRE (Si no es comando, es una duda)
    # Como no tenemos base de datos, si el bot se reinicia aquí, le pedirá que elija tema
    # Pero al menos los botones de ejercicio nunca fallarán.
    if user_text not in GRUPOS and not tema_elegido:
        # Intentamos recuperar el tema del contexto (mejorable con DB, pero por ahora...)
        res = gemini_generate(f"Responde esta duda de física: {user_text}")
        guardar_en_sheets(chat_id, "Consulta Directa", "Duda", user_text)
        send_message(chat_id, res)
        return "ok", 200

    return "ok", 200

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup: payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
