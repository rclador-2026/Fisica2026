import os
import json
import logging
import threading
import requests
from flask import Flask, request
from google import genai

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuración ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
client = genai.Client(api_key=GEMINI_API_KEY)
URL_SHEETS = "https://script.google.com/macros/s/AKfycbyVL89rtoJLTxBJSnj24zuUrPUqv9dIa8gfRQ8AuG36m7df_MZnEyRCkssMNQ8HOpwU/exec"

# --- Listas de Temas ---
GRUPOS = ["🔬 Cientifico A", "🔬 Cientifico B", "⚙️ Ingenieria"]
TEMAS_CIENTIFICO = ["📐 Herramientas Matematicas", "🍎 Leyes de Newton", "🚀 Cinematica",
                    "➡️ Movimientos en 1D", "↗️ Movimientos en 2D", "⚡ Trabajo Mecanico y Energia"]
TEMAS_INGENIERIA = ["📐 Herramientas Matematicas", "⚡ Electrostatica", "🔌 Circuitos Electricos",
                    "🧲 Magnetismo", "🔁 Induccion", "⚛️ Fisica Moderna"]
TODOS_LOS_TEMAS = list(set(TEMAS_CIENTIFICO + TEMAS_INGENIERIA))

# --- Cache en memoria ---
# Estructura: { chat_id: {"grupo": str, "nombre": str} }
_user_cache: dict = {}

# Estado de conversación por usuario
# Estructura: { chat_id: {"tema": str, "accion": str} }
# accion puede ser: "ejercicio", "duda", "lectura"
_estado: dict = {}


# --- Registro / Cache ---

def obtener_usuario(chat_id: int) -> dict:
    """Devuelve datos del usuario desde cache o Google Sheets."""
    if chat_id in _user_cache:
        return _user_cache[chat_id]
    try:
        r = requests.get(f"{URL_SHEETS}?id={chat_id}", timeout=5)
        if r.status_code == 200:
            datos = r.json()
            if datos.get("existe"):
                _user_cache[chat_id] = datos  # Guarda en cache
            return datos
    except Exception as e:
        log.warning(f"Error al verificar registro de {chat_id}: {e}")
    return {"existe": False}

def registrar_usuario(chat_id: int, nombre: str, grupo: str):
    """Registra al usuario en Sheets y actualiza el cache."""
    payload = {"accion": "registro", "alumno": str(chat_id), "nombre": nombre, "grupo": grupo}
    try:
        requests.post(URL_SHEETS, json=payload, timeout=5)
        _user_cache[chat_id] = {"existe": True, "grupo": grupo, "nombre": nombre}
        log.info(f"Usuario {chat_id} ({nombre}) registrado en {grupo}")
    except Exception as e:
        log.error(f"Error al registrar usuario {chat_id}: {e}")


# --- Gemini ---

def gemini_generate(prompt: str, grupo: str = "General") -> str:
    instrucciones = (
        f"Actúa como un profesor de física de bachillerato en Uruguay para el grupo de {grupo}. "
        "REGLAS DE FORMATO — obligatorias: "
        "PROHIBIDO usar LaTeX, no uses $, \\frac, \\cdot, \\text ni comandos con barra invertida. "
        "Las fracciones se escriben así: F = k * |q1 * q2| / r^2. "
        "Los exponentes con ^: r^2, 10^9. La multiplicación con *: k * q. "
        "Las unidades entre paréntesis: (N), (C), (m). "
        "Tono formal, técnico y extremadamente breve. Sin saludos ni muletillas."
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{instrucciones}\n\nPregunta del alumno: {prompt}"
        )
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        log.error(f"Error en Gemini: {e}")
        return "El servidor de física está sobrecargado. Intenta de nuevo en un minuto."


# --- Google Sheets (en hilo separado para no bloquear) ---

def guardar_en_sheets(alumno_id: int, grupo: str, tema: str, tipo: str, texto: str):
    """Guarda la consulta en Sheets de forma asíncrona."""
    def _guardar():
        payload = {
            "accion": "consulta",
            "alumno": str(alumno_id),
            "grupo": grupo,
            "tema": tema,
            "tipo": tipo,
            "consulta": texto
        }
        try:
            requests.post(URL_SHEETS, json=payload, timeout=5)
        except Exception as e:
            log.warning(f"No se pudo guardar consulta en Sheets: {e}")

    threading.Thread(target=_guardar, daemon=True).start()


# --- Telegram helpers ---

def send_message(chat_id: int, text: str, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        log.error(f"Error enviando mensaje a {chat_id}: {e}")

def typing(chat_id: int):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=3
        )
    except Exception as e:
        log.warning(f"Error enviando typing a {chat_id}: {e}")

def menu_temas(chat_id: int, grupo: str):
    temas = TEMAS_CIENTIFICO if "Cientifico" in grupo else TEMAS_INGENIERIA
    send_message(
        chat_id,
        f"📚 *Temas de {grupo}*\nSelecciona uno para trabajar:",
        reply_markup={"keyboard": [[{"text": t}] for t in temas], "resize_keyboard": True}
    )

def menu_acciones(chat_id: int, tema: str):
    send_message(
        chat_id,
        f"Has seleccionado: *{tema}*\n¿Qué quieres hacer?",
        reply_markup={
            "keyboard": [
                [{"text": f"❓ Ejercicio de {tema}"}],
                [{"text": f"📝 Duda sobre {tema}"}],
                [{"text": f"📚 Lectura de {tema}"}],
                [{"text": "🔙 Volver al inicio"}]
            ],
            "resize_keyboard": True
        }
    )


# --- Webhook Principal ---

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data:
        return "ok", 200

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    user_text = msg.get("text", "").strip()
    user_name = msg["from"].get("first_name", "Alumno")

    if not user_text:
        return "ok", 200

    # --- FLUJO 1: Usuario no registrado ---
    registro = obtener_usuario(chat_id)
    if not registro.get("existe"):
        if user_text in GRUPOS:
            registrar_usuario(chat_id, user_name, user_text)
            send_message(chat_id, f"✅ ¡Registrado en *{user_text}*! Escribe /start para ver tus temas.")
        else:
            send_message(
                chat_id,
                f"¡Hola {user_name}! No te encontré en la lista. Selecciona tu grupo:",
                reply_markup={
                    "keyboard": [[{"text": g}] for g in GRUPOS],
                    "resize_keyboard": True,
                    "one_time_keyboard": True
                }
            )
        return "ok", 200

    # --- FLUJO 2: Menú de temas ---
    grupo_alumno = registro.get("grupo", "General")

    if user_text in ("/start", "🔙 Volver al inicio") or "Volver" in user_text:
        _estado.pop(chat_id, None)  # Limpia estado previo
        menu_temas(chat_id, grupo_alumno)
        return "ok", 200

    # --- FLUJO 3: Selección de tema ---
    tema_detectado = next((t for t in TODOS_LOS_TEMAS if t == user_text), None)
    if tema_detectado:
        _estado.pop(chat_id, None)  # Limpia estado previo
        menu_acciones(chat_id, tema_detectado)
        return "ok", 200

    # --- FLUJO 4: Selección de acción (Ejercicio / Duda / Lectura) ---
    accion_detectada = None
    tema_de_accion = None

    for tema in TODOS_LOS_TEMAS:
        if user_text == f"❓ Ejercicio de {tema}":
            accion_detectada, tema_de_accion = "ejercicio", tema
            break
        elif user_text == f"📝 Duda sobre {tema}":
            accion_detectada, tema_de_accion = "duda", tema
            break
        elif user_text == f"📚 Lectura de {tema}":
            accion_detectada, tema_de_accion = "lectura", tema
            break

    if accion_detectada:
        # Guarda el contexto en estado
        _estado[chat_id] = {"accion": accion_detectada, "tema": tema_de_accion}
        send_message(chat_id, f"Perfecto. Escribí ahora tu {accion_detectada} específica sobre *{tema_de_accion}* y te respondo.")
        return "ok", 200

    # --- FLUJO 5: Respuesta con Gemini (usando contexto de estado) ---
    estado_usuario = _estado.get(chat_id, {})
    tema_actual = estado_usuario.get("tema", "Física General")
    tipo_consulta = {
        "ejercicio": "Ejercicio",
        "duda": "Duda Específica",
        "lectura": "Lectura"
    }.get(estado_usuario.get("accion"), "Duda General")

    typing(chat_id)
    respuesta = gemini_generate(user_text, grupo_alumno)
    send_message(chat_id, respuesta)

    # Guardar en Sheets de forma no bloqueante
    guardar_en_sheets(chat_id, grupo_alumno, tema_actual, tipo_consulta, user_text)

    # Limpiamos el estado tras responder (opcional: comentar si querés mantener contexto)
    _estado.pop(chat_id, None)

    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
