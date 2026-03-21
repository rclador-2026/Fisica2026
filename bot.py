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
user_state = {}  # { chat_id: { "grupo": "...", "tema": "...", "accion": "..." } }

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

def keyboard_acciones():
    return {
        "keyboard": [
            [{"text": "❓ Hazme una pregunta"}],
            [{"text": "📝 Evalua lo que sabes"}],
            [{"text": "📚 Donde leo de este tema"}],
            [{"text": "🔙 Volver a temas"}]
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

ACCIONES = [
    "❓ Hazme una pregunta",
    "📝 Evalua lo que sabes",
    "📚 Donde leo de este tema"
]

# ── Prompts base por tema ─────────────────────────────────────────────────────

PROMPTS_TEMA = {
    "📐 Herramientas Matematicas": "álgebra, trigonometría y vectores aplicados a física",
    "🍎 Leyes de Newton": "las tres Leyes de Newton y sus aplicaciones",
    "🚀 Cinematica": "cinemática y ecuaciones de movimiento",
    "➡️ Movimientos en 1D": "movimiento rectilíneo uniforme (MRU) y uniformemente acelerado (MRUA)",
    "↗️ Movimientos en 2D": "tiro parabólico y movimiento circular",
    "⚡ Trabajo Mecanico y Energia": "trabajo mecánico, energía cinética, potencial y conservación de energía",
    "⚡ Electrostatica": "electrostática, carga eléctrica, Ley de Coulomb, campo y potencial eléctrico",
    "🔌 Circuitos Electricos": "circuitos eléctricos, Ley de Ohm, circuitos serie/paralelo y leyes de Kirchhoff",
    "🧲 Magnetismo": "campo magnético, fuerza de Lorentz y materiales magnéticos",
    "🔁 Induccion": "inducción electromagnética, Ley de Faraday, Lenz, transformadores y generadores",
    "⚛️ Fisica Moderna": "física moderna: relatividad, efecto fotoeléctrico, mecánica cuántica y física nuclear"
}

# ── Prompts por acción ────────────────────────────────────────────────────────

def build_prompt(tema, accion, user_text=None):
    descripcion = PROMPTS_TEMA.get(tema, "física general")

    if accion == "❓ Hazme una pregunta":
        return (
            f"Eres un profesor de física. El alumno quiere practicar sobre {descripcion}. "
            f"Formulá UNA sola pregunta conceptual o de cálculo, clara y apropiada para estudiante universitario. "
            f"No des la respuesta todavía. Solo la pregunta."
        )

    elif accion == "📝 Evalua lo que sabes":
        if user_text:
            return (
                f"Eres un profesor de física evaluando a un alumno sobre {descripcion}. "
                f"El alumno respondió lo siguiente: '{user_text}'. "
                f"Evaluá su respuesta: indicá si es correcta, qué estuvo bien, qué mejorar y dá la respuesta completa. "
                f"Sé constructivo y didáctico."
            )
        else:
            return (
                f"Eres un profesor de física. Creá un ejercicio o pregunta de evaluación sobre {descripcion}. "
                f"Puede ser de opción múltiple o de desarrollo. Indicá claramente qué debe responder el alumno."
            )

    elif accion == "📚 Donde leo de este tema":
        return (
            f"Eres un profesor de física. Recomendá recursos de estudio sobre {descripcion}. "
            f"Incluí: libros de texto clásicos con autor y edición, sitios web confiables, "
            f"canales de YouTube educativos y si hay cursos online gratuitos. "
            f"Organizá la respuesta por tipo de recurso."
        )

    else:
        return (
            f"Eres un profesor de física. Responde en español sobre {descripcion}. "
            f"Pregunta: {user_text}"
        )

# ── Helpers ───────────────────────────────────────────────────────────────────

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

def get_keyboard_temas(chat_id):
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
            send_message(chat_id, "↩️ Seleccioná tu grupo:", reply_markup=keyboard_grupos())

        # ── Volver a temas ──
        elif user_text == "🔙 Volver a temas":
            user_state[chat_id].pop("accion", None)
            user_state[chat_id].pop("tema", None)
            tema_keyboard = get_keyboard_temas(chat_id)
            send_message(chat_id, "↩️ Seleccioná un tema:", reply_markup=tema_keyboard)

        # ── Selección de grupo ──
        elif user_text in GRUPOS:
            user_state[chat_id] = {"grupo": user_text}
            if user_text in GRUPOS_CIENTIFICO:
                send_message(
                    chat_id,
                    f"✅ Grupo *{user_text}* seleccionado.\nElegí un tema:",
                    reply_markup=keyboard_temas_cientifico()
                )
            else:
                send_message(
                    chat_id,
                    f"✅ Grupo *{user_text}* seleccionado.\nElegí un tema:",
                    reply_markup=keyboard_temas_ingenieria()
                )

        # ── Selección de tema ──
        elif user_text in TODOS_LOS_TEMAS:
            user_state[chat_id]["tema"] = user_text
            user_state[chat_id].pop("accion", None)
            send_message(
                chat_id,
                f"📖 Tema: *{user_text}*\n\n¿Qué querés hacer?",
                reply_markup=keyboard_acciones()
            )

        # ── Selección de acción ──
        elif user_text in ACCIONES:
            tema = state.get("tema", "")
            if not tema:
                send_message(chat_id, "⚠️ Primero elegí un tema.", reply_markup=get_keyboard_temas(chat_id))
                return "ok", 200

            user_state[chat_id]["accion"] = user_text

            # "Donde leo" y "Hazme una pregunta" se resuelven de inmediato
            if user_text in ["📚 Donde leo de este tema", "❓ Hazme una pregunta"]:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
                        json={"chat_id": chat_id, "action": "typing"}
                    )
                    prompt = build_prompt(tema, user_text)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f"Responde siempre en español.\n{prompt}"
                    )
                    bot_response = response.candidates[0].content.parts[0].text
                    send_message(chat_id, bot_response, reply_markup=keyboard_acciones())
                except Exception as e:
                    print(f"ERROR GEMINI: {e}")
                    send_message(chat_id, f"⚠️ Error: {e}")

            # "Evalua lo que sabes" genera primero el ejercicio
            elif user_text == "📝 Evalua lo que sabes":
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
                        json={"chat_id": chat_id, "action": "typing"}
                    )
                    prompt = build_prompt(tema, user_text)
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f"Responde siempre en español.\n{prompt}"
                    )
                    ejercicio = response.candidates[0].content.parts[0].text
                    user_state[chat_id]["esperando_respuesta"] = True
                    send_message(
                        chat_id,
                        f"{ejercicio}\n\n✏️ _Escribí tu respuesta y la evaluaré._",
                        reply_markup=keyboard_acciones()
                    )
                except Exception as e:
                    print(f"ERROR GEMINI: {e}")
                    send_message(chat_id, f"⚠️ Error: {e}")

        # ── Respuesta del alumno a la evaluación ──
        elif state.get("esperando_respuesta") and user_text:
            tema = state.get("tema", "")
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
                    json={"chat_id": chat_id, "action": "typing"}
                )
                prompt = build_prompt(tema, "📝 Evalua lo que sabes", user_text)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"Responde siempre en español.\n{prompt}"
                )
                evaluacion = response.candidates[0].content.parts[0].text
                user_state[chat_id]["esperando_respuesta"] = False
                send_message(chat_id, evaluacion, reply_markup=keyboard_acciones())
            except Exception as e:
                print(f"ERROR GEMINI: {e}")
                send_message(chat_id, f"⚠️ Error: {e}")

        # ── Consulta libre ──
        elif user_text:
            tema = state.get("tema", "")
            accion = state.get("accion", "")
            try:
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
                    json={"chat_id": chat_id, "action": "typing"}
                )
                prompt = build_prompt(tema, accion, user_text)
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=f"Responde siempre en español.\n{prompt}"
                )
                bot_response = response.candidates[0].content.parts[0].text
                send_message(chat_id, bot_response, reply_markup=keyboard_acciones() if tema else get_keyboard_temas(chat_id))
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

