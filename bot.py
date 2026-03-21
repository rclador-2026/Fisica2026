import os
from google import genai
from flask import Flask, request
import requests
import json

app = Flask(__name__)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)

# ── Estado en memoria ─────────────────────────────────────────────────────────
user_state = {}  # { chat_id: { "grupo": "...", "tema": "..." } }

# ── Teclados ──────────────────────────────────────────────────────────────────

def keyboard_grupos():
    return {
        "keyboard": [
            [{"text": "🔬 Cientifico A"}],
            [{"text": "🔬 Cientifico B"}],
            [{"text": "⚙️ Ingenieria"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def keyboard_temas_cientifico():
    return {
        "keyboard": [
            [{"text": "📐 Herramientas Matematicas"}],
            [{"text": "🍎 Leyes de Newton"}],
            [{"text": "🚀 Cinematica"}],
            [{"text": "➡️ Movimientos en 1D"}],
            [{"text": "↗️ Movimientos en 2D"}],
            [{"text": "⚡ Trabajo Mecanico y Energia"}],
            [{"text": "🔙 Volver a grupos"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def keyboard_temas_ingenieria():
    return {
        "keyboard": [
            [{"text": "📐 Herramientas Matematicas"}],
            [{"text": "⚡ Electrostatica"}],
            [{"text": "🔌 Circuitos Electricos"}],
            [{"text": "🧲 Magnetismo"}],
            [{"text": "🔁 Induccion"}],
            [{"text": "⚛️ Fisica Moderna"}],
            [{"text": "🔙 Volver a grupos"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

# ── Constantes ────────────────────────────────────────────────────────────────

GRUPOS = ["🔬 Cientifico A", "🔬 Cientifico B", "⚙️ Ingenieria"]
GRUPOS_CIENTIFICO = ["🔬 Cientifico A", "🔬 Cientifico B"]

TEMAS_CIENTIFICO = [
    "📐 Herramientas Matematicas",
    "🍎 Leyes de Newton",
    "🚀 Cinematica",
    "➡️ Movimientos en 1D",
    "↗️ Movimientos en 2D",
    "⚡ Trabajo Mecanico y Energia"
]

TEMAS_INGENIERIA = [
    "📐 Herramientas Matematicas",
    "⚡ Electrostatica",
    "🔌 Circuitos Electricos",
    "🧲 Magnetismo",
    "🔁 Induccion",
    "⚛️ Fisica Moderna"
]

TODOS_LOS_TEMAS = set(TEMAS_CIENTIFICO + TEMAS_INGENIERIA)

# ── Prompts por tema ──────────────────────────────────────────────────────────

PROMPTS_TEMA = {
    # Científico A y B
    "📐 Herramientas Matematicas": "Eres un profesor de física. Explica usando álgebra, trigonometría y vectores de forma clara y paso a paso.",
    "🍎 Leyes de Newton": "Eres un profesor de física especializado en las Leyes de Newton. Explica con ejemplos cotidianos y fórmulas.",
    "🚀 Cinematica": "Eres un profesor de física especializado en cinemática. Usa las ecuaciones de movimiento y explica paso a paso.",
    "➡️ Movimientos en 1D": "Eres un profesor de física. Responde sobre movimiento en una dimensión: MRU y MRUA, con fórmulas y ejemplos.",
    "↗️ Movimientos en 2D": "Eres un profesor de física. Responde sobre movimiento en dos dimensiones: tiro parabólico y movimiento circular.",
    "⚡ Trabajo Mecanico y Energia": "Eres un profesor de física especializado en trabajo mecánico, energía cinética, potencial y conservación de energía.",
    # Ingeniería
    "⚡ Electrostatica": "Eres un profesor de física especializado en electrostática. Explica carga eléctrica, Ley de Coulomb, campo y potencial eléctrico con fórmulas y ejemplos.",
    "🔌 Circuitos Electricos": "Eres un profesor de física especializado en circuitos eléctricos. Explica Ley de Ohm, circuitos en serie y paralelo, y leyes de Kirchhoff con ejercicios resueltos.",
    "🧲 Magnetismo": "Eres un profesor de física especializado en magnetismo. Explica campo magnético, fuerza de Lorentz y materiales magnéticos con claridad.",
    "🔁 Induccion": "Eres un profesor de física especializado en inducción electromagnética. Explica la Ley de Faraday, Lenz y aplicaciones como transformadores y generadores.",
    "⚛️ Fisica Moderna": "Eres un profesor de física especializado en física moderna. Explica relatividad, efecto fotoeléctrico, mecánica cuántica y física nuclear de forma accesible."
}

# ── Helper de envío ───────────────────────────────────────────────────────────

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

def get_keyboard_for(chat_id):
    """Devuelve el teclado correcto según el grupo actual del usuario."""
    grupo = user_state.get(chat_id, {}).get("grupo", "")
    if grupo in GRUPOS_CIENTIFICO:
        return keyboard_temas_cientifico()
    elif grupo == "⚙️ Ingenieria":
        return keyboard_temas_ingenieria()
    return keyboard_grupos()

# ── Rutas ─────────────────────────────────────────────────────────────────────

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    resp = requests.post(url, json={"url": f"{render_url}/webhook"})
    return resp.json()

@app.route('/modelos', methods=['GET'])
def modelos():
    models = client.models.list()
    return str([m.name for m in models])

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "")
        state = user_state.get(chat_id, {})

        # ── /start ──
        if user_text == "/start":
            user_state[chat_id] = {}
            send_message(
                chat_id,
                "👋 ¡Hola! Soy tu profe virtual.\nSeleccioná tu grupo para comenzar:",
                reply_markup=keyboard_grupos()
            )

        # ── Volver a grupos ──
        elif user_text == "🔙 Volver a grupos":
            user_state[chat_id] = {}
            send_message(
                chat_id,
                "↩️ Seleccioná tu grupo:",
                reply_markup=keyboard_grupos()
            )

        # ── Selección de grupo ──
        elif user_text in GRUPOS:
            user_state[chat_id] = {"grupo": user_text}

            if user_text in GRUPOS_CIENTIFICO:
                send_message(
                    chat_id,
                    f"✅ Grupo *{user_text}* seleccionado.\nElegí un tema:",
                    reply_markup=keyboard_temas_cientifico()
                )
            elif user_text == "⚙️ Ingenieria":
                send_message(
                    chat_id,
                    f"✅ Grupo *{user_text}* seleccionado.\nElegí un tema:",
                    reply_markup=keyboard_temas_ingenieria()
                )

        # ── Selección de tema ──
        elif user_text in TODOS_LOS_TEMAS:
            user_state[chat_id]["tema"] = user_text
            send_message(
                chat_id,
                f"📖 Tema: *{user_text}*\n\nHaceme tu consulta 👇",
                reply_markup=get_keyboard_for(chat_id)
            )

        # ── Consulta libre → Gemini ──
        elif user_text:
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
                    json={"chat_id": chat_id, "action": "typing"}
                )

                tema = state.get("tema", "")
                sistema = PROMPTS_TEMA.get(tema, "Eres un profesor virtual. Responde de forma clara y didáctica.")
                prompt = f"{sistema}\nResponde siempre en español.\nPregunta del usuario: {user_text}"

                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                bot_response = response.candidates[0].content.parts[0].text
                send_message(chat_id, bot_response, reply_markup=get_keyboard_for(chat_id))

            except Exception as e:
                print(f"ERROR GEMINI: {e}")
                send_message(chat_id, f"⚠️ Error: {e}")

    return "ok", 200

@app.route('/')
def index():
    return "Bot activo", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
