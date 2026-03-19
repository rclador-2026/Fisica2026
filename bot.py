import os
from genai import Client  # La nueva forma de importar
from flask import Flask, request
import requests

app = Flask(__name__)

# 1. Configuración de API Keys
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 2. Inicializar el nuevo Cliente de Google GenAI
client = Client(api_key=GEMINI_API_KEY)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    
    if data and "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"]["text"]

        try:
            # 3. Nueva forma de generar contenido
            prompt = f"Eres un experto en física. Responde de forma clara: {user_text}"
            response = client.models.generate_content(
                model="gemini-1.5-flash", 
                contents=prompt
            )
            bot_response = response.text

            # 4. Enviar a Telegram
            send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(send_url, json={"chat_id": chat_id, "text": bot_response})
            
        except Exception as e:
            print(f"Error con la nueva librería: {e}")

    return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
