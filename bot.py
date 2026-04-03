import os
import requests
from flask import Flask, request
from google import genai

app = Flask(__name__)

# Configuración de variables de entorno en Render
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
URL_SHEETS = os.environ.get("URL_SHEETS")

client = genai.Client(api_key=GEMINI_KEY)

def llamar_gemini(mensaje_usuario):
    # Prompt optimizado para tus alumnos de bachillerato en Uruguay
    prompt_sistema = """
    Eres PhysiBot, un tutor experto en Física para secundaria en Uruguay.
    Tu objetivo es ayudar a estudiantes de los niveles Científico e Ingeniería.
    - Usa un lenguaje cercano ('che', 'gurises', 'impecable').
    - Si te piden ejercicios, genera uno numérico y explica los conceptos.
    - Prioriza temas como Leyes de Newton, Termodinámica y Electromagnetismo.
    """
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        config={'system_instruction': prompt_sistema},
        contents=[mensaje_usuario]
    )
    return response.text

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if not data or "message" not in data:
        return "OK", 200

    user_id = str(data["message"]["from"]["id"])
    user_msg = data["message"].get("text", "")

    # 1. Consultar si el alumno existe en el Google Sheet
    res_sheets = requests.get(f"{URL_SHEETS}?id={user_id}")
    datos_alumno = res_sheets.json()

    if not datos_alumno.get("existe"):
        # Lógica de registro para alumnos nuevos
        if "/" in user_msg and len(user_msg.split("/")) == 2:
            nombre, grupo = user_msg.split("/")
            requests.post(URL_SHEETS, json={
                "accion": "registro",
                "alumno": user_id,
                "nombre": nombre.strip(),
                "grupo": grupo.strip()
            })
            respuesta_bot = f"¡Registrado impecable, {nombre}! Ya podés consultarme lo que necesites de Física."
        else:
            respuesta_bot = "¡Hola! No te tengo en la lista del Liceo 35. Decime tu nombre y grupo así: Nombre / Grupo (ejemplo: Juan Perez / 6to CB)."
    else:
        # 2. Respuesta educativa con Gemini
        respuesta_bot = llamar_gemini(user_msg)
        
        # 3. Guardar la consulta para tu seguimiento docente
        requests.post(URL_SHEETS, json={
            "accion": "consulta",
            "alumno": user_id,
            "grupo": datos_alumno.get("grupo"),
            "tema": "General",
            "tipo": "Chat",
            "consulta": user_msg
        })

    # Enviar respuesta a Telegram
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                  json={"chat_id": user_id, "text": respuesta_bot})

    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
