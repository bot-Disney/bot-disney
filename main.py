from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

BOT_TOKEN = "9197975180:AAGGidSbVmRlJTMDU8UhXEFP9h2oOmt1vJU"
WHATSAPP_NUMERO = "584247091547"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbyiT5N-YF3X6Tk2egHY7zl9CwH1jvyjwsIEOr9lhn_YevtzcZ1HCAqxzqrFT9EYBWMr/exec"

@app.get("/")
async def home():
    return {"status": "¡El bot de Disney+ está activo y funcionando sin errores de criptografía!"}

@app.post("/webhook")
async def recibir_webhook(req: Request):
    data = await req.json()
    
    if "callback_query" in data:
        cb = data["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        cb_data = cb["data"]
        cb_id = cb["id"]
        
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb_id})
        
        if cb_data == "menu_principal":
            enviar_menu(chat_id)
        elif cb_data == "soporte":
            enviar_soporte(chat_id)
        elif cb_data == "ver_datos":
            consultar_datos_cliente(chat_id)
        elif cb_data == "obtener_codigo":
            procesar_solicitud_codigo(chat_id)

    elif "message" in data:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()
        text_lower = text.lower()
        
        user_info = msg.get("from", {})
        nombre_usuario = user_info.get("first_name", "Cliente")
        if user_info.get("username"):
            nombre_usuario += f" (@{user_info.get('username')})"

        verificar_o_registrar_usuario(chat_id, nombre_usuario)

        if text_lower in ["/start", "/menu"]:
            enviar_menu(chat_id)
        elif text_lower in ["/codigo", "codigo"]:
            procesar_solicitud_codigo(chat_id)
        else:
            enviar_menu(chat_id)

    return {"status": "ok"}

def verificar_o_registrar_usuario(chat_id, nombre_usuario):
    try:
        requests.post(APPS_SCRIPT_URL, json={"action": "verificar_o_registrar", "chat_id": str(chat_id), "nombre_usuario": nombre_usuario})
    except Exception as e:
        print(f"Error en auto-registro: {e}")

def enviar_menu(chat_id):
    teclado = {
        "inline_keyboard": [
            [{"text": "📲 Ver mis datos / Pantalla", "callback_data": "ver_datos"}],
            [{"text": "🔑 Solicitar Código Disney", "callback_data": "obtener_codigo"}],
            [{"text": "💬 Soporte / Solicitar Pago", "callback_data": "soporte"}]
        ]
    }
    enviar_mensaje(chat_id, "Bienvenido al servicio de Streaming 🍿\n\nSelecciona una opción en los botones de abajo:", teclado)

def enviar_soporte(chat_id):
    url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text=Hola,%20quiero%20información%20sobre%20los%20pagos%20o%20renovaciones%20de%20Disney+."
    teclado = {
        "inline_keyboard": [
            [{"text": "💬 Abrir Chat de WhatsApp", "url": url_whatsapp}],
            [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
        ]
    }
    enviar_mensaje(chat_id, "💬 *ATENCIÓN AL CLIENTE Y PAGOS*\n\nPresiona el botón de abajo para comunicarte directamente por WhatsApp:", teclado)

def consultar_datos_cliente(chat_id):
    try:
        res = requests.post(APPS_SCRIPT_URL, json={"action": "consultar_datos", "chat_id": str(chat_id)})
        data = res.json()
        if data.get("status") == "ok":
            mensaje = f"Tus datos de suscripción:\n\n• Cuenta: {data['cuenta']}\n• Pantalla N°: {data['pantalla']}\n• Vencimiento: {data['vencimiento']}\n• Estado: {data['estado']}"
        else:
            mensaje = "⚠️ No se encontraron tus datos en el sistema."
    except Exception as e:
        mensaje = f"❌ Error:\n`{str(e)}`"
        
    teclado = {"inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]}
    enviar_mensaje(chat_id, mensaje, teclado)

def procesar_solicitud_codigo(chat_id):
    try:
        enviar_mensaje(chat_id, "🔍 Buscando código reciente en tu correo...\n\nUn momento...")
        res = requests.post(APPS_SCRIPT_URL, json={"action": "obtener_codigo", "chat_id": str(chat_id)})
        data = res.json()
        
        if data.get("status") == "no_account":
            texto_respuesta = "⚠️ Aún no tienes una cuenta de Disney+ asignada. Comunícate a soporte."
        elif data.get("status") == "success" and data.get("codigo"):
            texto_respuesta = f"Tu código de acceso de Disney+ es:\n\n`{data['codigo']}`\n\n(Cópialo e ingrésalo en tu pantalla)"
        elif data.get("status") == "success":
            texto_respuesta = f"Último mensaje recibido de Disney+:\n\n{data['body']}..."
        else:
            texto_respuesta = "No hay códigos recientes para tu cuenta."
    except Exception as e:
        texto_respuesta = f"❌ Error de correo:\n`{str(e)}`"

    teclado = {"inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]}
    enviar_mensaje(chat_id, texto_respuesta, teclado)

def enviar_mensaje(chat_id, texto, teclado=None):
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    if teclado:
        payload["reply_markup"] = teclado
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
              
