import os
import requests
from flask import Flask, request, jsonify
from google import genai

app = Flask(__name__)

# Configuración (Usa tus variables de entorno en Render)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
URL_SHEETS = os.environ.get("URL_SHEETS") # La URL de tu Apps Script

client = genai.Client(api_key=GEMINI_KEY)

def llamar_gemini(prompt_sistema, mensaje_usuario):
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

    # 1. CONSULTAR ESTADO AL SHEETS (¿Qué estaba haciendo el alumno?)
    # Usamos el parámetro historial=1 que definimos en el Apps Script
    res_sheets = requests.get(f"{URL_SHEETS}?id={user_id}&historial=1")
    datos_previos = res_sheets.json()
    ultimo_ejercicio = datos_previos.get("historial", "")

    # 2. DECIDIR SI ES UNA RESPUESTA O UNA CONSULTA NUEVA
    # Si el último mensaje guardado tiene un "Enunciado" y el usuario manda algo corto (un número o unidad)
    es_posible_respuesta = "Enunciado:" in ultimo_ejercicio and len(user_msg) < 15

    if es_posible_respuesta:
        prompt_instruccion = f"""
        Actúa como un profesor de Física uruguayo. 
        El alumno está resolviendo este ejercicio previo: {ultimo_ejercicio}
        Su respuesta actual es: "{user_msg}"
        
        TAREA:
        1. Si la respuesta es correcta (considerando redondeos y unidades), felicítalo y dile: "¡Impecable! ¿Querés que sigamos con otro o tenés alguna duda?".
        2. Si es incorrecta o le faltan unidades, no le des la solución. Explícale el error (ej: 'revisá el pasaje de km a metros') y pídele que lo intente de nuevo.
        3. Mantén el tono de 'profe de liceo' (usa 'che', 'gurises', etc).
        """
    else:
        prompt_instruccion = """
        Eres PhysiBot, un tutor de Física para bachillerato en Uruguay.
        Si el usuario te pide ejercicios, SIEMPRE empieza el texto con 'Enunciado:' seguido del problema.
        Si el usuario solo saluda, preséntate y ofrece ayuda con Newton, Termodinámica o Cinemática.
        """

    # 3. GENERAR RESPUESTA CON GEMINI
    respuesta_ai = llamar_gemini(prompt_instruccion, user_msg)

    # 4. ENVIAR A TELEGRAM
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                  json={"chat_id": user_id, "text": respuesta_ai})

    # 5. ACTUALIZAR EL HISTORIAL EN EL SHEETS
    # Guardamos lo que el bot acaba de decir para que en la próxima vuelta sepamos qué ejercicio hay pendiente
    requests.post(URL_SHEETS, json={
        "accion": "save_historial",
        "alumno": user_id,
        "historial": respuesta_ai
    })

    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
