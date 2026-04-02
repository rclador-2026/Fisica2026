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
# Asegúrate de que esta URL sea la de la "Nueva Implementación" con acceso a "Cualquiera"
URL_SHEETS = "https://script.google.com/macros/s/AKfycbyVL89rtoJLTxBJSnj24zuUrPUqv9dIa8gfRQ8AuG36m7df_MZnEyRCkssMNQ8HOpwU/exec"

# --- Listas de Temas ---
GRUPOS = ["🔬 Cientifico A", "🔬 Cientifico B", "⚙️ Ingenieria"]
TEMAS_CIENTIFICO = ["📐 Herramientas Matematicas", "🍎 Leyes de Newton", "🚀 Cinematica", "➡️ Movimientos en 1D", "↗️ Movimientos en 2D", "⚡ Trabajo Mecanico y Energia"]
TEMAS_INGENIERIA = ["📐 Herramientas Matematicas", "⚡ Electrostatica", "🔌 Circuitos Electricos", "🧲 Magnetismo", "🔁 Induccion", "⚛️ Fisica Moderna"]
TODOS_LOS_TEMAS = list(set(TEMAS_CIENTIFICO + TEMAS_INGENIERIA))

# --- Funciones de Apoyo ---

def verificar_registro(chat_id):
    try:
        # Timeout corto para no ralentizar el bot si Google tarda
        r = requests.get(f"{URL_SHEETS}?id={chat_id}", timeout=4)
        if r.status_code == 200:
            return r.json()
        return {"existe": False}
    except:
        return {"existe": False}

def gemini_generate(prompt, grupo="General"):
    try:
        instrucciones = (
            f"Actúa como un profesor de física de bachillerato en Uruguay para el grupo de {grupo}. "
            "Tu tono debe ser formal, técnico y extremadamente breve. Ve directo al grano. "
            "No saludes, no uses muletillas, responde la duda técnica de inmediato."
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=f"{instrucciones}\n\nPregunta del alumno: {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except:
        return "El servidor de física está sobrecargado. Intenta de nuevo en un minuto."

def guardar_en_sheets(alumno_id, grupo, tema, tipo, texto_consulta):
    payload = {
        "accion": "consulta",
        "alumno": str(alumno_id),
        "grupo": grupo,
        "tema": tema,
        "tipo": tipo,
        "consulta": texto_consulta  # CORREGIDO: Antes decía texto_puro
    }
    try:
        requests.post(URL_SHEETS, json=payload, timeout=5)
    except:
        pass

# --- Webhook Principal ---

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data: return "ok", 200
    
    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")
    user_name = data["message"]["from"].get("first_name", "Alumno")

    # Verificamos si el alumno ya está en el Excel
    registro = verificar_registro(chat_id)

    # 1. FLUJO DE REGISTRO (Si no existe en el Excel)
    if not registro.get("existe"):
        if user_text in GRUPOS:
            payload = {"accion": "registro", "alumno": str(chat_id), "nombre": user_name, "grupo": user_text}
            requests.post(URL_SHEETS, json=payload)
            send_message(chat_id, f"✅ ¡Registrado con éxito en {user_text}! Escribe /start para ver tus temas.")
            return "ok", 200
        
        send_message(chat_id, f"¡Hola {user_name}! No te encontré en la lista. Por favor, selecciona tu grupo:", 
                     reply_markup={"keyboard": [[{"text": g}] for g in GRUPOS], "resize_keyboard": True, "one_time_keyboard": True})
        return "ok", 200

    # 2. MENÚ DE TEMAS (Si ya está registrado)
    grupo_alumno = registro.get("grupo")
    if user_text == "/start" or "Volver" in user_text or "🔙" in user_text:
        temas = TEMAS_CIENTIFICO if "Cientifico" in grupo_alumno else TEMAS_INGENIERIA
        send_message(chat_id, f"📚 *Temas de {grupo_alumno}* \nSelecciona uno para trabajar:", 
                     reply_markup={"keyboard": [[{"text": t}] for t in temas], "resize_keyboard": True})
        return "ok", 200

    # 3. SUB-MENÚ DE ACCIONES (Ejercicio, Duda, Lectura)
    tema_detectado = next((t for t in TODOS_LOS_TEMAS if t == user_text), None)
    if tema_detectado:
        send_message(chat_id, f"Has seleccionado: *{tema_detectado}*\n¿Qué quieres hacer?", 
                     reply_markup={
                         "keyboard": [
                             [{"text": f"❓ Ejercicio de {tema_detectado}"}],
                             [{"text": f"📝 Duda sobre {tema_detectado}"}],
                             [{"text": f"📚 Lectura de {tema_detectado}"}],
                             [{"text": "🔙 Volver al inicio"}]
                         ], "resize_keyboard": True
                     })
        return "ok", 200

   # 4. RESPUESTA TÉCNICA
    if user_text not in GRUPOS:
        # Si el usuario solo tocó el botón pero no escribió su duda aún:
        if any(user_text == f"{prefix} de {tema}" for prefix in ["❓ Ejercicio", "📚 Lectura"] for tema in TODOS_LOS_TEMAS) or \
           any(user_text == f"📝 Duda sobre {tema}" for tema in TODOS_LOS_TEMAS):
            
            accion = "ejercicio" if "❓" in user_text else "lectura" if "📚" in user_text else "duda"
            send_message(chat_id, f"Perfecto. Escribí ahora tu {accion} específica sobre este tema y te respondo.")
            return "ok", 200

        # Si ya escribió algo más que el texto del botón, procesamos con Gemini
        typing(chat_id)
        
        # Identificar contexto para Sheets
        tipo = "Duda General"
        if "❓" in user_text: tipo = "Ejercicio"
        elif "📝" in user_text: tipo = "Duda Específica"
        elif "📚" in user_text: tipo = "Lectura"

        res = gemini_generate(user_text, grupo_alumno)
        send_message(chat_id, res)
        
        # Guardar en Google Sheets
        guardar_en_sheets(chat_id, grupo_alumno, "Física", tipo, user_text)

    return "ok", 200

# --- Funciones de Telegram ---

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup: payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=payload)
    except:
        pass

def typing(chat_id):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction", 
                      json={"chat_id": chat_id, "action": "typing"})
    except:
        pass

if __name__ == "__main__":
    # Render usa el puerto 5000 por defecto
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
