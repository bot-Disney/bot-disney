import os
import requests
from fastapi import FastAPI, Request
from bot_logic import procesar_mensaje_bot

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_DE_TELEGRAM")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

@app.on_event("startup")
def startup_event():
    print("¡El servidor, el lector de Gmail y el bot interactivo se han iniciado en Render!")

@app.get("/")
def home():
    return {"status": "El bot de streaming está activo y funcionando"}

@app.post("/webhook")
async def recibir_webhook(request: Request):
    """Recibe mensajes y clics de botones (callbacks) desde Telegram."""
    try:
        data = await request.json()
        
        # 1. Si el usuario hizo clic en un botón flotante (Inline Keyboard)
        if "callback_query" in data:
            cb = data["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            message_id = cb["message"]["message_id"]
            callback_data = cb["data"]
            callback_id = cb["id"]
            
            nombre = cb["from"].get("first_name", "Cliente")
            username = cb["from"].get("username", "")
            
            # Responder al callback de Telegram para quitar el reloj de carga del botón
            responder_callback_telegram(callback_id)
            
            # Procesar la acción en la lógica del bot
            procesar_mensaje_bot(
                chat_id=chat_id,
                texto="",
                nombre=nombre,
                username=username,
                enviar_mensaje_callback=enviar_mensaje_telegram,
                editar_mensaje_callback=editar_mensaje_telegram,
                message_id=message_id,
                es_callback=True,
                callback_data=callback_data
            )
            
        # 2. Si el usuario envió un mensaje de texto normal
        elif "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            texto = message.get("text", "")
            nombre = message["from"].get("first_name", "Cliente")
            username = message["from"].get("username", "")
            
            procesar_mensaje_bot(
                chat_id=chat_id,
                texto=texto,
                nombre=nombre,
                username=username,
                enviar_mensaje_callback=enviar_mensaje_telegram
            )

        return {"status": "ok"}
    
    except Exception as e:
        print(f"Error procesando el webhook: {e}")
        return {"status": "error", "message": str(e)}

def enviar_mensaje_telegram(chat_id, texto, teclado=None):
    """Envía un mensaje nuevo al chat de Telegram."""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    if teclado:
        payload["reply_markup"] = teclado
        
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

def editar_mensaje_telegram(chat_id, message_id, texto, teclado=None):
    """Edita un mensaje existente para una experiencia más fluida."""
    url = f"{TELEGRAM_API_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    if teclado:
        payload["reply_markup"] = teclado
        
    try:
        response = requests.post(url, json=payload)
        res_json = response.json()
        # Si el contenido es idéntico y Telegram rechaza editar, enviamos uno nuevo como respaldo
        if not res_json.get("ok"):
            enviar_mensaje_telegram(chat_id, texto, teclado)
    except Exception as e:
        print(f"Error editando mensaje en Telegram: {e}")

def responder_callback_telegram(callback_id):
    """Quita el icono de carga del botón en Telegram al presionarlo."""
    url = f"{TELEGRAM_API_URL}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id})
    except Exception as e:
        print(f"Error respondiendo callback: {e}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
