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
URL_SHEETS = "TU_URL_AQUI"

# ── Listas de Datos ───────────────────────────────────────────────────────────
GRUPOS = ["🔬 Cientifico A", "🔬 Cientifico B", "⚙️ Ingenieria"]
TEMAS_CIENTIFICO = ["📐 Herramientas Matematicas", "🍎 Leyes de Newton", "🚀 Cinematica", "⚡ Trabajo y Energia"]
TEMAS_INGENIERIA = ["📐 Herramientas Matematicas", "⚡ Electrostatica", "🔌 Circuitos", "🧲 Magnetismo", "⚛️ Fisica Moderna"]
TODOS_LOS_TEMAS = list(set(TEMAS_CIENTIFICO + TEMAS_INGENIERIA))

# ── Funciones Core ────────────────────────────────────────────────────────────

def gemini_generate(prompt):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", # <--- ACTUALIZADO A 2.5 FLASH
            contents=f"Eres un profesor de física uruguayo. Responde directo y breve: {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        print(f"Error Gemini: {e}")
        return "El profe de física está en el laboratorio. Intenta en un minuto."

def guardar_en_sheets(alumno, tema, tipo, consulta):
    if "TU_URL" in URL_SHEETS: return
    payload = {"alumno": str(alumno), "tema": tema, "tipo": tipo, "consulta": consulta}
    try:
        # Enviamos como JSON al Apps Script
        requests.post(URL_SHEETS, json=payload, timeout=8)
    except:
        pass

# ── Webhook Principal (Lógica Anti-Amnesia) ───────────────────────────────────

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data: return "ok", 200

    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")

    # 1. INICIO
    if user_text == "/start" or "Volver" in user_text:
        send_message(chat_id, "¡Hola! Selecciona tu grupo para empezar:", 
                     reply_markup={"keyboard": [[{"text": g}] for g in GRUPOS], "resize_keyboard": True})
        return "ok", 200

    # 2. SELECCIÓN DE GRUPO -> MUESTRA TEMAS
    if user_text in GRUPOS:
        temas = TEMAS_CIENTIFICO if "Cientifico" in user_text else TEMAS_INGENIERIA
        send_message(chat_id, f"Has elegido {user_text}. Elige un tema:", 
                     reply_markup={"keyboard": [[{"text": t}] for t in temas] + [[{"text": "🔙 Volver"}]], "resize_keyboard": True})
        return "ok", 200

    # 3. SELECCIÓN DE TEMA -> MUESTRA ACCIONES CON EL TEMA INCLUIDO
    tema_detectado = next((t for t in TODOS_LOS_TEMAS if t in user_text), None)
    if tema_detectado and "❓" not in user_text and "📝" not in user_text:
        send_message(chat_id, f"Sobre {tema_detectado}, ¿qué necesitas?", 
                     reply_markup={
                         "keyboard": [
                             [{"text": f"❓ Ejercicio de {tema_detectado}"}],
                             [{"text": f"📝 Duda sobre {tema_detectado}"}],
                             [{"text": "🔙 Volver"}]
                         ], "resize_keyboard": True
                     })
        return "ok", 200

    # 4. EJERCICIO (Lee el tema directamente del botón)
    if "❓ Ejercicio de" in user_text:
        tema = user_text.replace("❓ Ejercicio de ", "")
        res = gemini_generate(f"Dame un ejercicio de nivel bachillerato sobre {tema}")
        send_message(chat_id, res)
        guardar_en_sheets(chat_id, tema, "Pedido Ejercicio", "N/A")
        return "ok", 200

    # 5. DUDA (Prepara al bot para la siguiente respuesta)
    if "📝 Duda sobre" in user_text:
        tema = user_text.replace("📝 Duda sobre ", "")
        send_message(chat_id, f"Escribe tu duda específica sobre {tema} y te responderé:")
        # Aquí el bot "espera" la respuesta, pero si se reinicia, 
        # la siguiente línea igual intentará responder con IA general.
        return "ok", 200

    # 6. CAPTURA DE PREGUNTA LIBRE
    if user_text not in GRUPOS and not tema_detectado:
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
