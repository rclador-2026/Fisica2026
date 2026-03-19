import os
import google.generativeai as genai
from flask import Flask, request
import requests

# 1. Configuración de la App
app = Flask(__name__)

# 2. Configuración de API Keys (Se sacan de las Variables de Entorno de Render)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 3. Configurar Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
else:
    print("Error: No se encontró la GEMINI_API_KEY en las variables de entorno")

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    # Verificamos que el JSON de Telegram traiga un mensaje con texto
    if data and "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"]["text"]

        try:
            # Generar respuesta con Gemini
            prompt = f"Eres un experto en física. Responde de forma clara y educativa a lo siguiente: {user_text}"
            response = model.generate_content(prompt)
            bot_response = response.text

            # Enviar de vuelta a Telegram
            send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {"chat_id": chat_id, "text": bot_response}
            requests.post(send_url, json=payload)
            
        except Exception as e:
            print(f"Error procesando el mensaje: {e}")

    return "ok", 200

# 4. Bloque de arranque corregido (con la indentación de 4 espacios)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
