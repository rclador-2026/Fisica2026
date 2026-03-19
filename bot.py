import os
from google import genai  # <--- EL CAMBIO ESTÁ AQUÍ
from flask import Flask, request
import requests

app = Flask(__name__)

# Configuración de API Keys
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# Inicializar el nuevo Cliente de Google (Forma correcta)
client = genai.Client(api_key=GEMINI_API_KEY)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    if data and "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"]["text"]

        try:
            # Generar respuesta con el nuevo cliente
            response = client.models.generate_content(
                model="gemini-1.5-flash", 
                contents=user_text
            )
            bot_response = response.text

            # Enviar a Telegram
            send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(send_url, json={"chat_id": chat_id, "text": bot_response})
            
        except Exception as e:
            print(f"Error en la lógica: {e}")

    return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
