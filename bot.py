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

MAX_HISTORIAL = 10  # Máximo de mensajes a recordar por alumno

# --- Listas de Temas ---
GRUPOS = ["🔬 Cientifico A", "🔬 Cientifico B", "⚙️ Ingenieria"]
TEMAS_CIENTIFICO = ["📐 Herramientas Matematicas", "🍎 Leyes de Newton", "🚀 Cinematica",
                    "➡️ Movimientos en 1D", "↗️ Movimientos en 2D", "⚡ Trabajo Mecanico y Energia"]
TEMAS_INGENIERIA = ["📐 Herramientas Matematicas", "⚡ Electrostatica", "🔌 Circuitos Electricos",
                    "🧲 Magnetismo", "🔁 Induccion", "⚛️ Fisica Moderna"]
TODOS_LOS_TEMAS = list(set(TEMAS_CIENTIFICO + TEMAS_INGENIERIA))

# --- Caches en memoria ---
_user_cache: dict = {}       # {chat_id: {existe, grupo, nombre, nivel, temas_vistos: []}}
_historial_cache: dict = {}  # {chat_id: [{role, content}, ...]}
_estado: dict = {}           # {chat_id: {tema, accion, eval_activa, eval_pregunta, eval_tema}}


# ============================================================
# SHEETS
# ============================================================

def obtener_usuario(chat_id: int) -> dict:
    """Devuelve perfil del alumno desde cache o Sheets."""
    if chat_id in _user_cache:
        return _user_cache[chat_id]
    try:
        r = requests.get(f"{URL_SHEETS}?id={chat_id}", timeout=5)
        if r.status_code == 200:
            datos = r.json()
            if datos.get("existe"):
                datos.setdefault("nivel", "básico")
                datos.setdefault("temas_vistos", [])
                if isinstance(datos["temas_vistos"], str):
                    datos["temas_vistos"] = [t.strip() for t in datos["temas_vistos"].split(",") if t.strip()]
                _user_cache[chat_id] = datos
            return datos
    except Exception as e:
        log.warning(f"Error al verificar registro {chat_id}: {e}")
    return {"existe": False}

def registrar_usuario(chat_id: int, nombre: str, grupo: str):
    payload = {"accion": "registro", "alumno": str(chat_id), "nombre": nombre, "grupo": grupo}
    try:
        requests.post(URL_SHEETS, json=payload, timeout=5)
        _user_cache[chat_id] = {
            "existe": True, "grupo": grupo, "nombre": nombre,
            "nivel": "básico", "temas_vistos": []
        }
        log.info(f"Registrado: {chat_id} ({nombre}) en {grupo}")
    except Exception as e:
        log.error(f"Error al registrar {chat_id}: {e}")

def actualizar_perfil(chat_id: int, nivel: str, temas_vistos: list):
    """Actualiza nivel y temas en cache y Sheets (async)."""
    if chat_id in _user_cache:
        _user_cache[chat_id]["nivel"] = nivel
        _user_cache[chat_id]["temas_vistos"] = temas_vistos

    def _sync():
        payload = {
            "accion": "update_perfil",
            "alumno": str(chat_id),
            "nivel": nivel,
            "temas_vistos": ",".join(temas_vistos)
        }
        try:
            requests.post(URL_SHEETS, json=payload, timeout=5)
        except Exception as e:
            log.warning(f"Error actualizando perfil {chat_id}: {e}")
    threading.Thread(target=_sync, daemon=True).start()

def cargar_historial(chat_id: int) -> list:
    """Carga historial desde Sheets si no está en cache."""
    if chat_id in _historial_cache:
        return _historial_cache[chat_id]
    try:
        r = requests.get(f"{URL_SHEETS}?id={chat_id}&historial=1", timeout=5)
        if r.status_code == 200:
            data = r.json()
            historial = data.get("historial", [])
            _historial_cache[chat_id] = historial
            return historial
    except Exception as e:
        log.warning(f"Error cargando historial {chat_id}: {e}")
    _historial_cache[chat_id] = []
    return []

def guardar_historial_sheets(chat_id: int, historial: list):
    """Guarda historial en Sheets (async)."""
    def _sync():
        payload = {
            "accion": "save_historial",
            "alumno": str(chat_id),
            "historial": json.dumps(historial[-MAX_HISTORIAL:])
        }
        try:
            requests.post(URL_SHEETS, json=payload, timeout=5)
        except Exception as e:
            log.warning(f"Error guardando historial {chat_id}: {e}")
    threading.Thread(target=_sync, daemon=True).start()

def guardar_consulta(alumno_id: int, grupo: str, tema: str, tipo: str, texto: str):
    """Guarda consulta en Sheets (async)."""
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
            log.warning(f"Error guardando consulta {alumno_id}: {e}")
    threading.Thread(target=_guardar, daemon=True).start()


# ============================================================
# HISTORIAL EN MEMORIA
# ============================================================

def agregar_al_historial(chat_id: int, role: str, content: str):
    if chat_id not in _historial_cache:
        cargar_historial(chat_id)
    _historial_cache[chat_id].append({"role": role, "content": content})
    if len(_historial_cache[chat_id]) > MAX_HISTORIAL:
        _historial_cache[chat_id] = _historial_cache[chat_id][-MAX_HISTORIAL:]
    guardar_historial_sheets(chat_id, _historial_cache[chat_id])


# ============================================================
# GEMINI
# ============================================================

FORMATO_BASE = (
    "REGLAS DE FORMATO OBLIGATORIAS: PROHIBIDO usar LaTeX, no uses $, \\frac, \\cdot, \\text ni comandos con barra invertida. "
    "Fracciones: F = k * |q1 * q2| / r^2. Exponentes: r^2, 10^9. Multiplicacion: k * q. Unidades entre parentesis: (N), (C), (m). "
)

def gemini_tutor(prompt: str, grupo: str, nivel: str, historial: list) -> str:
    """Responde con contexto del historial y adaptado al nivel del alumno."""
    instrucciones = (
        f"Eres un tutor personal de fisica de bachillerato en Uruguay para el grupo {grupo}. "
        f"El alumno esta en nivel {nivel}. Ajusta la complejidad: "
        "basico = explicaciones simples paso a paso, intermedio = conceptos mas formales, avanzado = rigor tecnico completo. "
        + FORMATO_BASE +
        "Se breve y directo. No saludes ni uses muletillas."
    )
    contexto = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in historial[-6:]])
    if contexto:
        contents = f"{instrucciones}\n\nHistorial reciente:\n{contexto}\n\nNueva pregunta: {prompt}"
    else:
        contents = f"{instrucciones}\n\nPregunta: {prompt}"
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=contents)
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        log.error(f"Error en gemini_tutor: {e}")
        return "El servidor esta sobrecargado. Intenta de nuevo en un minuto."

def gemini_evaluar(tema: str, grupo: str, nivel: str) -> str:
    """Genera una pregunta de evaluacion adaptada al nivel."""
    instrucciones = (
        f"Eres un profesor de fisica de bachillerato en Uruguay para el grupo {grupo}. "
        f"El alumno esta en nivel {nivel}. "
        f"Genera UNA sola pregunta de evaluacion sobre '{tema}' adaptada a ese nivel: "
        "basico = conceptual o calculo simple, intermedio = aplicacion de formulas, avanzado = problema con varios pasos. "
        + FORMATO_BASE +
        "Escribe solo la pregunta, sin respuesta, sin introduccion."
    )
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=instrucciones)
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        log.error(f"Error en gemini_evaluar: {e}")
        return "No pude generar la pregunta. Intenta de nuevo."

def gemini_corregir(pregunta: str, respuesta: str, grupo: str, nivel: str) -> dict:
    """Evalua la respuesta del alumno y sugiere nuevo nivel. Devuelve dict JSON."""
    instrucciones = (
        f"Eres un profesor de fisica de bachillerato en Uruguay para el grupo {grupo}. "
        f"El nivel actual del alumno es: {nivel}. "
        + FORMATO_BASE +
        "Evalua la respuesta del alumno a la pregunta de fisica. "
        "Responde UNICAMENTE con un objeto JSON valido (sin markdown, sin ```) con esta estructura exacta: "
        '{"feedback": "correccion detallada aqui", "nuevo_nivel": "basico o intermedio o avanzado", "correcto": true o false}'
    )
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{instrucciones}\n\nPregunta: {pregunta}\nRespuesta del alumno: {respuesta}"
        )
        text = response.candidates[0].content.parts[0].text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        log.error(f"Error en gemini_corregir: {e}")
        return {"feedback": "No pude evaluar tu respuesta. Intenta de nuevo.", "nuevo_nivel": nivel, "correcto": False}

def gemini_resumen(temas_vistos: list, grupo: str, nivel: str) -> str:
    """Genera un resumen del progreso del alumno."""
    if not temas_vistos:
        return "Todavia no registre consultas tuyas. Empieza explorando un tema del menu."
    instrucciones = (
        f"Eres un tutor de fisica de bachillerato en Uruguay para el grupo {grupo}. "
        f"El alumno tiene nivel {nivel} y ha trabajado los temas: {', '.join(temas_vistos)}. "
        "Escribe un resumen breve de su progreso: que temas cubrió y que podria repasar o avanzar. "
        + FORMATO_BASE +
        "Maximo 5 oraciones."
    )
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=instrucciones)
        return response.candidates[0].content.parts[0].text
    except Exception as e:
        log.error(f"Error en gemini_resumen: {e}")
        return "No pude generar el resumen en este momento."


# ============================================================
# TELEGRAM HELPERS
# ============================================================

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
            json={"chat_id": chat_id, "action": "typing"}, timeout=3
        )
    except Exception as e:
        log.warning(f"Error typing {chat_id}: {e}")

def menu_principal(chat_id: int, grupo: str):
    temas = TEMAS_CIENTIFICO if "Cientifico" in grupo else TEMAS_INGENIERIA
    keyboard = [[{"text": t}] for t in temas]
    keyboard.append([{"text": "📊 Mi Progreso"}, {"text": "🧪 Evaluarme"}])
    send_message(
        chat_id,
        f"📚 *Temas de {grupo}*\nSelecciona un tema o usa las opciones del tutor:",
        reply_markup={"keyboard": keyboard, "resize_keyboard": True}
    )

def menu_acciones(chat_id: int, tema: str):
    send_message(
        chat_id,
        f"Has seleccionado: *{tema}*\n¿Que quieres hacer?",
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

def menu_evaluacion(chat_id: int, grupo: str):
    temas = TEMAS_CIENTIFICO if "Cientifico" in grupo else TEMAS_INGENIERIA
    keyboard = [[{"text": f"📝 Eval: {t}"}] for t in temas]
    keyboard.append([{"text": "🔙 Volver al inicio"}])
    send_message(
        chat_id,
        "🧪 *Evaluacion*\nSelecciona el tema sobre el que queres que te evalue:",
        reply_markup={"keyboard": keyboard, "resize_keyboard": True}
    )


# ============================================================
# WEBHOOK
# ============================================================

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

    # --- FLUJO 1: No registrado ---
    registro = obtener_usuario(chat_id)
    if not registro.get("existe"):
        if user_text in GRUPOS:
            registrar_usuario(chat_id, user_name, user_text)
            send_message(chat_id, f"✅ Registrado en *{user_text}*. Escribe /start para comenzar.")
        else:
            send_message(
                chat_id,
                f"Hola {user_name}. No te encontre en la lista. Selecciona tu grupo:",
                reply_markup={
                    "keyboard": [[{"text": g}] for g in GRUPOS],
                    "resize_keyboard": True,
                    "one_time_keyboard": True
                }
            )
        return "ok", 200

    grupo_alumno = registro.get("grupo", "General")
    nivel_alumno = registro.get("nivel", "básico")
    temas_vistos = registro.get("temas_vistos", [])

    # Si el alumno ya registrado toca el botón de grupo de nuevo → menú principal
    if user_text in GRUPOS:
        menu_principal(chat_id, grupo_alumno)
        return "ok", 200

    # --- FLUJO 2: Volver / Start ---
    if user_text in ("/start", "🔙 Volver al inicio") or "Volver" in user_text:
        _estado.pop(chat_id, None)
        menu_principal(chat_id, grupo_alumno)
        return "ok", 200

    # --- FLUJO 3: Mi Progreso ---
    if user_text == "📊 Mi Progreso":
        typing(chat_id)
        nivel_emoji = {"básico": "🟢", "intermedio": "🟡", "avanzado": "🔴"}.get(nivel_alumno, "🟢")
        resumen = gemini_resumen(temas_vistos, grupo_alumno, nivel_alumno)
        send_message(chat_id, f"{nivel_emoji} *Nivel actual: {nivel_alumno.capitalize()}*\n\n{resumen}")
        return "ok", 200

    # --- FLUJO 4: Evaluarme ---
    if user_text == "🧪 Evaluarme":
        _estado.pop(chat_id, None)
        menu_evaluacion(chat_id, grupo_alumno)
        return "ok", 200

    # --- FLUJO 5: Seleccion de tema para evaluacion ---
    tema_eval = next((t for t in TODOS_LOS_TEMAS if user_text == f"📝 Eval: {t}"), None)
    if tema_eval:
        typing(chat_id)
        pregunta = gemini_evaluar(tema_eval, grupo_alumno, nivel_alumno)
        _estado[chat_id] = {
            "eval_activa": True,
            "eval_pregunta": pregunta,
            "eval_tema": tema_eval
        }
        send_message(chat_id, f"🧪 *Evaluacion — {tema_eval}*\n\n{pregunta}\n\n_Escribi tu respuesta:_")
        return "ok", 200

    # --- FLUJO 6: Respuesta a evaluacion activa ---
    estado = _estado.get(chat_id, {})
    if estado.get("eval_activa"):
        typing(chat_id)
        resultado = gemini_corregir(estado["eval_pregunta"], user_text, grupo_alumno, nivel_alumno)
        feedback = resultado.get("feedback", "Sin feedback.")
        nuevo_nivel = resultado.get("nuevo_nivel", nivel_alumno)
        correcto = resultado.get("correcto", False)

        icono = "✅" if correcto else "❌"
        msg_nivel = ""
        if nuevo_nivel != nivel_alumno:
            msg_nivel = f"\n\n📈 *Tu nivel cambio de {nivel_alumno} a {nuevo_nivel}*"
            actualizar_perfil(chat_id, nuevo_nivel, temas_vistos)

        send_message(chat_id, f"{icono} *Correccion:*\n\n{feedback}{msg_nivel}")
        agregar_al_historial(chat_id, "user", f"[Eval {estado['eval_tema']}] {user_text}")
        agregar_al_historial(chat_id, "assistant", feedback)
        guardar_consulta(chat_id, grupo_alumno, estado["eval_tema"], "Evaluacion", user_text)
        _estado.pop(chat_id, None)
        return "ok", 200

    # --- FLUJO 7: Seleccion de tema normal ---
    tema_detectado = next((t for t in TODOS_LOS_TEMAS if t == user_text), None)
    if tema_detectado:
        _estado.pop(chat_id, None)
        menu_acciones(chat_id, tema_detectado)
        return "ok", 200

    # --- FLUJO 8: Seleccion de accion (Ejercicio / Duda / Lectura) ---
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
        if accion_detectada == "duda":
            # La duda la escribe el alumno
            _estado[chat_id] = {"accion": "duda", "tema": tema_de_accion}
            send_message(chat_id, f"Perfecto. Escribi tu duda especifica sobre *{tema_de_accion}* y te respondo.")
        elif accion_detectada == "ejercicio":
            # Gemini genera el ejercicio de inmediato
            typing(chat_id)
            prompt = f"Genera un ejercicio de practica sobre '{tema_de_accion}' adaptado al nivel {nivel_alumno}."
            historial = cargar_historial(chat_id)
            respuesta = gemini_tutor(prompt, grupo_alumno, nivel_alumno, historial)
            send_message(chat_id, f"📝 *Ejercicio — {tema_de_accion}*\n\n{respuesta}")
            agregar_al_historial(chat_id, "user", prompt)
            agregar_al_historial(chat_id, "assistant", respuesta)
            if tema_de_accion not in temas_vistos:
                temas_vistos.append(tema_de_accion)
                actualizar_perfil(chat_id, nivel_alumno, temas_vistos)
            guardar_consulta(chat_id, grupo_alumno, tema_de_accion, "Ejercicio", prompt)
        elif accion_detectada == "lectura":
            # Gemini recomienda una lectura de inmediato
            typing(chat_id)
            prompt = f"Recomienda un texto o recurso de lectura simple y claro sobre '{tema_de_accion}' para un alumno de bachillerato nivel {nivel_alumno}. Explica brevemente de que trata y por que es util."
            historial = cargar_historial(chat_id)
            respuesta = gemini_tutor(prompt, grupo_alumno, nivel_alumno, historial)
            send_message(chat_id, f"📚 *Lectura recomendada — {tema_de_accion}*\n\n{respuesta}")
            agregar_al_historial(chat_id, "user", prompt)
            agregar_al_historial(chat_id, "assistant", respuesta)
            if tema_de_accion not in temas_vistos:
                temas_vistos.append(tema_de_accion)
                actualizar_perfil(chat_id, nivel_alumno, temas_vistos)
            guardar_consulta(chat_id, grupo_alumno, tema_de_accion, "Lectura", prompt)
        return "ok", 200

    # --- FLUJO 9: Respuesta con tutor (historial + nivel) ---
    tema_actual = estado.get("tema", "Fisica General")
    tipo_consulta = {
        "ejercicio": "Ejercicio",
        "duda": "Duda Especifica",
        "lectura": "Lectura"
    }.get(estado.get("accion"), "Duda General")

    typing(chat_id)
    historial = cargar_historial(chat_id)
    respuesta = gemini_tutor(user_text, grupo_alumno, nivel_alumno, historial)
    send_message(chat_id, respuesta)

    agregar_al_historial(chat_id, "user", user_text)
    agregar_al_historial(chat_id, "assistant", respuesta)

    if tema_actual not in temas_vistos and tema_actual != "Fisica General":
        temas_vistos.append(tema_actual)
        actualizar_perfil(chat_id, nivel_alumno, temas_vistos)

    guardar_consulta(chat_id, grupo_alumno, tema_actual, tipo_consulta, user_text)
    _estado.pop(chat_id, None)
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
