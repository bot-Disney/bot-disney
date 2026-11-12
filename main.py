import os
import requests
from fastapi import FastAPI, Request
from sheets_db import consultar_suscripcion

app = FastAPI()

# Token de tu bot de Telegram (reemplaza o usa variable de entorno)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_TOKEN_DE_TELEGRAM")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

@app.on_event("startup")
def startup_event():
    print("¡El bot de Telegram y FastAPI se han iniciado correctamente en Render!")

@app.get("/")
def home():
    return {"status": "El bot está activo y funcionando"}

@app.post("/webhook")
async def recibir_webhook(request: Request):
    """Punto de entrada (webhook) que recibe los mensajes y botones de Telegram."""
    try:
        data = await request.json()
        
        # Verificar si el mensaje viene de Telegram
        if "message" in data:
            message = data["message"]
            chat_id = message["chat"]["id"]
            texto = message.get("text", "")
            
            # Si el usuario escribe o presiona algo relacionado con suscripción
            if "suscripción" in texto.lower() or texto == "/suscribcion":
                # Consultar los datos en Google Sheets
                suscripcion = consultar_suscripcion(chat_id)
                
                if suscripcion:
                    respuesta = f"Tu suscripción está activa. Datos: {suscripcion}"
                else:
                    respuesta = "No se encontró ninguna suscripción activa para tu usuario."
                
                # Enviar la respuesta de vuelta al chat de Telegram
                enviar_mensaje_telegram(chat_id, respuesta)

        return {"status": "ok"}
    
    except Exception as e:
        print(f"Error procesando el webhook: {e}")
        return {"status": "error", "message": str(e)}

def enviar_mensaje_telegram(chat_id, texto):
    """Función para enviar mensajes de texto de vuelta a Telegram."""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error enviando mensaje a Telegram: {e}")

# Asegurar que Uvicorn escuche en el puerto dinámico que exige Render
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
 
