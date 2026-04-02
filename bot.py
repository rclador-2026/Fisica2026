import os
from google import genai
from flask import Flask, request
import requests
import json

app = Flask(__name__)

# --- Configuración ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)
URL_SHEETS = "TU_NUEVA_URL_AQUI" # <--- PEGA LA URL NUEVA AQUÍ

# --- Listas ---
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

def gemini_generate(prompt, grupo="General"):
    try:
        instrucciones = (
            f"Eres un profesor de física de Uruguay para el grupo de {grupo}. "
            "Responde de forma técnica, formal y muy breve. Ve directo al punto. "
            "No saludes ni divagues."
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=f"{instrucciones}\n\nAlumno: {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except:
        return "Consulte nuevamente en un minuto."

def guardar_en_sheets(alumno_id, grupo, tema, tipo, texto_consulta):
    payload = {
        "accion": "consulta",
        "alumno": str(alumno_id),
        "grupo": grupo,
        "tema": tema,
        "tipo": tipo,
        "consulta": texto_consulta # <--- Nombre clave
    }
    try:
        requests.post(URL_SHEETS, json=payload, timeout=5)
    except:
        pass

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data: return "ok", 200
    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")
    user_name = data["message"]["from"].get("first_name", "Alumno")

    registro = verificar_registro(chat_id)

    # 1. REGISTRO
    if not registro.get("existe"):
        if user_text in GRUPOS:
            payload = {"accion": "registro", "alumno": str(chat_id), "nombre": user_name, "grupo": user_text}
            requests.post(URL_SHEETS, json=payload)
            send_message(chat_id, f"Registrado en {user_text}. Escribe /start para comenzar.")
            return "ok", 200
        
        send_message(chat_id, "Selecciona tu grupo:", 
                     reply_markup={"keyboard": [[{"text": g}] for g in GRUPOS], "resize_keyboard": True})
        return "ok", 200

    # 2. MENÚ DE TEMAS
    grupo = registro.get("grupo")
    if user_text == "/start" or "Volver" in user_text:
        temas = TEMAS_CIENTIFICO if "Cientifico" in grupo else TEMAS_INGENIERIA
        send_message(chat_id, f"Temas de {grupo}:", 
                     reply_markup={"keyboard": [[{"text": t}] for t in temas], "resize_keyboard": True})
        return "ok", 200

    # 3. ACCIONES DE TEMA
    tema_detectado = next((t for t in TODOS_LOS_TEMAS if t in user_text), None)
    if tema_detectado and not any(icon in user_text for icon in ["❓", "📝", "📚"]):
        send_message(chat_id, f"¿Qué necesitas de {tema_detectado}?", 
                     reply_markup={
                         "keyboard": [
                             [{"text": f"❓ Ejercicio de {tema_detectado}"}],
                             [{"text": f"📝 Duda sobre {tema_detectado}"}],
                             [{"text": f"📚 Lectura de {tema_detectado}"}],
                             [{"text": "🔙 Volver"}]
                         ], "resize_keyboard": True
                     })
        return "ok", 200

    # 4. RESPUESTA TÉCNICA
    if user_text not in GRUPOS:
        typing(chat_id)
        res = gemini_generate(user_text, grupo)
        send_message(chat_id, res)
        
        # Guardar si es una duda real
        tipo = "Duda"
        if "❓" in user_text: tipo = "Ejercicio"
        if "📚" in user_text: tipo = "Lectura"
        guardar_en_sheets(chat_id, grupo, "Física", tipo, user_text)

    return "ok", 200

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup: payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json=payload)

def typing(chat_id):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
