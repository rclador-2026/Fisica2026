import os
from google import genai
from flask import Flask, request
import requests

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

client = genai.Client(api_key=GEMINI_API_KEY)

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    render_url = os.environ.get('RENDER_EXTERNAL_URL')
    resp = requests.post(url, json={"url": f"{render_url}/webhook"})
    return resp.json()

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "")

        if user_text == "/start":
            send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(send_url, json={"chat_id": chat_id, "text": "Hola! Soy tu profe virtual. Tienes dudas ?."})

        elif user_text:
            try:
                response = client.models.generate_content(
                    model="gemini-1.5-flash",
                    contents=user_text
                )
                bot_response = response.text
                send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                requests.post(send_url, json={"chat_id": chat_id, "text": bot_response})

            except Exception as e:
                # Muestra el error en logs Y te lo manda por Telegram
                print(f"ERROR GEMINI: {e}")
                send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                requests.post(send_url, json={"chat_id": chat_id, "text": f"Error: {e}"})

    return "ok", 200

@app.route('/')
def index():
    return "Bot activo", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
