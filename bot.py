import os
from google import genai
from flask import Flask, request
import requests
import json

app = Flask(__name__)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)

user_state = {}

# ── Configuración de Botones (Sincronizados) ──────────────────────────────────
OP_EJERCICIO = "❓ Ponme un ejercicio"
OP_PREGUNTA = "📝 Preguntale al profesor"
OP_LECTURA = "📚 Donde leo de este tema"
OP_VOLVER = "🔙 Volver a temas"

ACCIONES = [OP_EJERCICIO, OP_PREGUNTA, OP_LECTURA]

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

# (Mantén tus funciones de keyboard_grupos y temas igual que antes...)

# ── Generación de IA Optimizada ───────────────────────────────────────────────

def gemini_generate(prompt):
    # Usamos 1.5-flash-002 o 2.0-flash para máxima velocidad
    response = client.models.generate_content(
        model="gemini-2.0-flash", 
        contents=f"Eres un profesor de física uruguayo. Responde DIRECTO, sin introducciones largas. {prompt}"
    )
    return response.candidates[0].content.parts[0].text

def build_prompt(tema, accion, user_text=None):
    if accion == OP_EJERCICIO:
        return f"Crea UN ejercicio técnico de {tema} para nivel bachillerato. Ve directo al enunciado."
    
    elif accion == OP_LECTURA:
        return f"Recomienda 3 fuentes bibliográficas o links rápidos para estudiar {tema}."
    
    elif accion == OP_PREGUNTA:
        return f"Responde de forma técnica y breve (máximo 2 párrafos) sobre {tema}. Pregunta: {user_text}"
    
    return f"Explica brevemente: {user_text}"

# ── Lógica del Webhook ────────────────────────────────────────────────────────

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data:
        return "ok", 200

    chat_id = data["message"]["chat"]["id"]
    user_text = data["message"].get("text", "")
    state = user_state.get(chat_id, {})

    # Lógica de Navegación
    if user_text == "/start" or user_text == "🔙 Volver a grupos":
        user_state[chat_id] = {}
        send_message(chat_id, "Selecciona tu grupo:", reply_markup=keyboard_grupos())
    
    elif user_text == OP_VOLVER:
        user_state[chat_id] = {"grupo": state.get("grupo")}
        send_message(chat_id, "Elige un tema:", reply_markup=get_keyboard_temas(chat_id))

    # Selección de Temas (Simplificado)
    elif user_text in TODOS_LOS_TEMAS:
        user_state[chat_id] = {"grupo": state.get("grupo"), "tema": user_text}
        send_message(chat_id, f"Has elegido {user_text}. ¿Qué quieres hacer?", reply_markup=keyboard_acciones())

    # Acciones del Botón
    elif user_text in ACCIONES:
        tema = state.get("tema")
        if not tema:
            send_message(chat_id, "Primero elige un tema.")
            return "ok", 200
        
        user_state[chat_id]["ultima_accion"] = user_text
        
        if user_text == OP_PREGUNTA:
            send_message(chat_id, "Dime tu duda técnica y te respondo de inmediato:")
        else:
            # Para ejercicio o lectura, respondemos directo
            res = gemini_generate(build_prompt(tema, user_text))
            send_message(chat_id, res, reply_markup=keyboard_acciones())

    # Respuesta a "Preguntale al profesor" (cuando el usuario escribe la duda)
    elif state.get("ultima_accion") == OP_PREGUNTA:
        tema = state.get("tema")
        res = gemini_generate(build_prompt(tema, OP_PREGUNTA, user_text))
        user_state[chat_id]["ultima_accion"] = None # Resetear acción
        send_message(chat_id, res, reply_markup=keyboard_acciones())

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
