import os
import requests
from fastapi import FastAPI, Request
from bot_logic import procesar_mensaje_bot

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_DE_TELEGRAM")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

@app.on_event("startup")
def startup_event():
    print("¡El servidor y el bot con botones interactivos se han iniciado en Render!")

@app.get("/")
def home():
    return {"status": "El bot está activo y funcionando"}

@app.post("/webhook")
async def recibir_webhook(request: Request):
    try:
        data = await request.json()
        
        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            texto = message.get("text", "")
            
            # Pasa la información a la lógica del bot
            procesar_mensaje_bot(chat_id, texto, enviar_mensaje_telegram)

        return {"status": "ok"}
    
    except Exception as e:
        print(f"Error procesando el webhook: {e}")
        return {"status": "error", "message": str(e)}

def enviar_mensaje_telegram(chat_id, texto, incluir_botones=False):
    """Envía mensajes a Telegram agregando opcionalmente un teclado de botones fijos."""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    
    # Si se solicitan botones, se agregan al mensaje
    if incluir_botones:
        payload["reply_markup"] = {
            "keyboard": [
                [{"text": "📺 Ver mi pantalla"}, {"text": "💳 Reportar pago"}],
                [{"text": "🛠️ Soporte técnico"}]
            ],
            "resize_keyboard": True,  # Hace que los botones se vean ordenados y no ocupen toda la pantalla
            "is_persistent": True
        }

    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
 
