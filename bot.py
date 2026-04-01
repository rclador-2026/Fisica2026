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
user_state = {}
# Estructura: {
#   chat_id: {
#     "grupo": "...",
#     "tema": "...",
#     "accion": "...",
#     "esperando_respuesta": True/False,
#     "ejercicio_actual": "texto del ejercicio generado"
#   }
# }

# ── Repartidos por tema ───────────────────────────────────────────────────────
REPARTIDOS = {
    "📐 Herramientas Matematicas":  "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "🍎 Leyes de Newton":           "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "🚀 Cinematica":                "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "➡️ Movimientos en 1D":         "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "↗️ Movimientos en 2D":         "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "⚡ Trabajo Mecanico y Energia": "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "⚡ Electrostatica":             "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "🔌 Circuitos Electricos":      "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "🧲 Magnetismo":                "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "🔁 Induccion":                 "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
    "⚛️ Fisica Moderna":            "https://drive.google.com/uc?export=download&id=ID_DEL_ARCHIVO",
}

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
            [{"text": "❓ Ponme un ejercicio"}],
            [{"text": "📝 Preguntale al profesor"}],
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

# ── Descripcion por tema ──────────────────────────────────────────────────────

PROMPTS_TEMA = {
    "📐 Herramientas Matematicas":  "algebra, trigonometria y vectores aplicados a fisica",
    "🍎 Leyes de Newton":           "las tres Leyes de Newton y sus aplicaciones",
    "🚀 Cinematica":                "cinematica y ecuaciones de movimiento",
    "➡️ Movimientos en 1D":         "movimiento rectilineo uniforme (MRU) y uniformemente acelerado (MRUA)",
    "↗️ Movimientos en 2D":         "tiro parabolico y movimiento circular",
    "⚡ Trabajo Mecanico y Energia": "trabajo mecanico, energia cinetica, potencial y conservacion de energia",
    "⚡ Electrostatica":             "electrostatica, carga electrica, Ley de Coulomb, campo y potencial electrico",
    "🔌 Circuitos Electricos":      "circuitos electricos, Ley de Ohm, circuitos serie/paralelo y leyes de Kirchhoff",
    "🧲 Magnetismo":                "campo magnetico, fuerza de Lorentz y materiales magneticos",
    "🔁 Induccion":                 "induccion electromagnetica, Ley de Faraday, Lenz, transformadores y generadores",
    "⚛️ Fisica Moderna":            "fisica moderna: relatividad, efecto fotoelectrico, mecanica cuantica y fisica nuclear"
}

# ── Prompts ───────────────────────────────────────────────────────────────────

def build_prompt(tema, accion, user_text=None, ejercicio_previo=None):
    descripcion = PROMPTS_TEMA.get(tema, "fisica general")

    if accion == "❓ Hazme una pregunta":
        return (
            f"Eres un profesor de fisica. El alumno quiere practicar sobre {descripcion}. "
            f"Formula UNA sola pregunta conceptual o de calculo, clara y apropiada para estudiante universitario. "
            f"No des la respuesta todavia. Solo la pregunta."
        )

    elif accion == "📝 Evalua lo que sabes":
        if user_text and ejercicio_previo:
            # Correccion con contexto del ejercicio original
            return (
                f"Eres un profesor de fisica corrigiendo un ejercicio sobre {descripcion}.\n\n"
                f"El ejercicio que se le planteo al alumno fue:\n{ejercicio_previo}\n\n"
                f"La respuesta del alumno fue:\n'{user_text}'\n\n"
                f"Realizá la siguiente correccion detallada:\n"
                f"1. Indică que estuvo CORRECTO en la respuesta.\n"
                f"2. Identifica cada ERROR conceptual o de calculo cometido.\n"
                f"3. Explica POR QUE es un error y cual es el concepto correcto.\n"
                f"4. Mostrá la resolucion COMPLETA paso a paso.\n"
                f"5. Da una calificacion del 1 al 10 con justificacion breve.\n"
                f"Se didactico, claro y constructivo."
            )
        else:
            # Generacion del ejercicio
            return (
                f"Eres un profesor de fisica. Crea UN ejercicio de evaluacion sobre {descripcion}. "
                f"Puede ser de calculo o conceptual, apropiado para nivel universitario. "
                f"Al final del enunciado escribi exactamente esta linea: "
                f"'Escribi tu resolucion completa para que pueda corregirla.'"
            )

    elif accion == "📚 Donde leo de este tema":
        return (
            f"Eres un profesor de fisica. Recomienda recursos de estudio sobre {descripcion}. "
            f"Incluye: libros de texto clasicos con autor y edicion, sitios web confiables, "
            f"canales de YouTube educativos y cursos online gratuitos si los hay. "
            f"Organiza la respuesta por tipo de recurso."
        )

    else:
        return (
            f"Eres un profesor de fisica. Responde en espanol sobre {descripcion}. "
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

def gemini_generate(prompt):
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Responde siempre en espanol.\n{prompt}"
    )
    return response.candidates[0].content.parts[0].text

def typing(chat_id):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
        json={"chat_id": chat_id, "action": "typing"}
    )

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
                "Hola! Soy tu profe virtual.\nSelecciona tu grupo para comenzar:",
                reply_markup=keyboard_grupos()
            )

        # ── Volver a grupos ──
        elif user_text == "🔙 Volver a grupos":
            user_state[chat_id] = {}
            send_message(chat_id, "Selecciona tu grupo:", reply_markup=keyboard_grupos())

        # ── Volver a temas ──
        elif user_text == "🔙 Volver a temas":
            user_state[chat_id] = {
                "grupo": state.get("grupo", "")
            }
            send_message(chat_id, "Selecciona un tema:", reply_markup=get_keyboard_temas(chat_id))

        # ── Seleccion de grupo ──
        elif user_text in GRUPOS:
            user_state[chat_id] = {"grupo": user_text}
            if user_text in GRUPOS_CIENTIFICO:
                send_message(
                    chat_id,
                    f"Grupo {user_text} seleccionado.\nElige un tema:",
                    reply_markup=keyboard_temas_cientifico()
                )
            else:
                send_message(
                    chat_id,
                    f"Grupo {user_text} seleccionado.\nElige un tema:",
                    reply_markup=keyboard_temas_ingenieria()
                )

        # ── Seleccion de tema ──
        elif user_text in TODOS_LOS_TEMAS:
            user_state[chat_id] = {
                "grupo": state.get("grupo", ""),
                "tema": user_text
            }
            send_message(
                chat_id,
                f"Tema: {user_text}\n\nQue queres hacer?",
                reply_markup=keyboard_acciones()
            )

        # ── Seleccion de accion ──
        elif user_text in ACCIONES:
            tema = state.get("tema", "")
            if not tema:
                send_message(chat_id, "Primero elige un tema.", reply_markup=get_keyboard_temas(chat_id))
                return "ok", 200

            user_state[chat_id]["accion"] = user_text

            if user_text in ["📚 Donde leo de este tema", "❓ Hazme una pregunta"]:
                try:
                    typing(chat_id)
                    bot_response = gemini_generate(build_prompt(tema, user_text))
                    send_message(chat_id, bot_response, reply_markup=keyboard_acciones())
                except Exception as e:
                    print(f"ERROR GEMINI: {e}")
                    send_message(chat_id, f"Error: {e}")

            elif user_text == "📝 Evalua lo que sabes":
                try:
                    # Enviar repartido si existe
                    link_repartido = REPARTIDOS.get(tema)
                    if link_repartido and "ID_DEL_ARCHIVO" not in link_repartido:
                        send_message(
                            chat_id,
                            f"Antes de empezar, aca tenes el repartido de ejercicios:\n{link_repartido}",
                            reply_markup=keyboard_acciones()
                        )

                    typing(chat_id)
                    # Generar ejercicio y guardarlo en el estado
                    ejercicio = gemini_generate(build_prompt(tema, user_text))
                    user_state[chat_id]["esperando_respuesta"] = True
                    user_state[chat_id]["ejercicio_actual"] = ejercicio  # <-- se guarda el ejercicio

                    send_message(
                        chat_id,
                        f"{ejercicio}\n\n_Escribi tu resolucion completa para que pueda corregirla._",
                        reply_markup=keyboard_acciones()
                    )
                except Exception as e:
                    print(f"ERROR GEMINI: {e}")
                    send_message(chat_id, f"Error: {e}")

        # ── Respuesta del alumno → correccion con contexto ──
        elif state.get("esperando_respuesta") and user_text:
            tema = state.get("tema", "")
            ejercicio_previo = state.get("ejercicio_actual", "")  # <-- se recupera el ejercicio
            try:
                typing(chat_id)
                # Se pasa el ejercicio original junto con la respuesta del alumno
                prompt = build_prompt(
                    tema,
                    "📝 Evalua lo que sabes",
                    user_text=user_text,
                    ejercicio_previo=ejercicio_previo
                )
                evaluacion = gemini_generate(prompt)
                # Limpiar estado de evaluacion pero mantener tema y grupo
                user_state[chat_id]["esperando_respuesta"] = False
                user_state[chat_id]["ejercicio_actual"] = ""
                send_message(chat_id, evaluacion, reply_markup=keyboard_acciones())
            except Exception as e:
                print(f"ERROR GEMINI: {e}")
                send_message(chat_id, f"Error: {e}")

        # ── Consulta libre ──
        elif user_text:
            tema = state.get("tema", "")
            accion = state.get("accion", "")
            try:
                typing(chat_id)
                prompt = build_prompt(tema, accion, user_text)
                bot_response = gemini_generate(prompt)
                markup = keyboard_acciones() if tema else get_keyboard_temas(chat_id)
                send_message(chat_id, bot_response, reply_markup=markup)
            except Exception as e:
                print(f"ERROR GEMINI: {e}")
                send_message(chat_id, f"Error: {e}")

    return "ok", 200

@app.route('/')
def index():
    return "Bot activo", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
