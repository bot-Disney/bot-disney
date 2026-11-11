from fastapi import FastAPI, Request
import requests
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import base64
import re

app = FastAPI()

BOT_TOKEN = "9197975180:AAGGidSbVmRlJTMDU8UhXEFP9h2oOmt1vJU"
WHATSAPP_NUMERO = "584247091547"

# Configuración de Google Sheets y Gmail
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.readonly"
]

def obtener_conexion_google():
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    client = gspread.authorize(creds)
    return client, creds

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
        text = msg.get("text", "").strip().lower()
        
        if text in ["/start", "/menu"]:
            enviar_menu(chat_id)
        elif text in ["/codigo", "codigo"]:
            procesar_solicitud_codigo(chat_id)
        else:
            enviar_menu(chat_id)

    return {"status": "ok"}

def enviar_menu(chat_id):
    teclado = {
        "inline_keyboard": [
            [{"text": "📲 Ver mis datos / Pantalla", "callback_data": "ver_datos"}],
            [{"text": "🔑 Solicitar Código Disney", "callback_data": "obtener_codigo"}],
            [{"text": "💬 Soporte / Solicitar Pago", "callback_data": "soporte"}]
        ]
    }
    enviar_mensaje(chat_id, "Bienvenido al servicio de Streaming\n\nSelecciona una opción en los botones de abajo:", teclado)

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
        client, _ = obtener_conexion_google()
        sh = client.open("Clientes")
        worksheet = sh.worksheet("Clientes")
        cell = worksheet.find(str(chat_id))
        
        if cell:
            row_values = worksheet.row_values(cell.row)
            cuenta = row_values[2] if len(row_values) > 2 else "N/A"
            pantalla = row_values[3] if len(row_values) > 3 else "N/A"
            vencimiento = row_values[4] if len(row_values) > 4 else "Sin fecha"
            estado = row_values[5] if len(row_values) > 5 else "Activo"
            
            mensaje = f"Tus datos de suscripción:\n\n• Cuenta: {cuenta}\n• Pantalla N°: {pantalla}\n• Vencimiento: {vencimiento}\n• Estado: {estado}"
        else:
            mensaje = "⚠️ No tienes ninguna pantalla registrada con este ID de Telegram."
    except Exception as e:
        mensaje = "Ocurrió un error al consultar tus datos en la hoja."
        
    teclado = {"inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]}
    enviar_mensaje(chat_id, mensaje, teclado)

def procesar_solicitud_codigo(chat_id):
    try:
        client, creds = obtener_conexion_google()
        sh = client.open("Clientes")
        worksheet = sh.worksheet("Clientes")
        cell = worksheet.find(str(chat_id))
        
        if not cell:
            enviar_mensaje(chat_id, "⚠️ No estás registrado en el sistema.")
            return
            
        row_values = worksheet.row_values(cell.row)
        cuenta = row_values[2] if len(row_values) > 2 else ""
        estado = row_values[5] if len(row_values) > 5 else ""
        
        if estado.lower() != "activo" or not cuenta or cuenta.lower() in ["por asignar", "n/a"]:
            enviar_mensaje(chat_id, "ACCESO RESTRINGIDO\n\nTu suscripción debe estar Activa y con una cuenta asignada para pedir códigos.")
            return

        enviar_mensaje(chat_id, "🔍 Buscando código reciente en el correo de Disney+, un momento...")

        service = build('gmail', 'v1', credentials=creds)
        query = f"from:disney to:{cuenta} label:INBOX newer_than:15m"
        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])

        if messages:
            msg_id = messages[0]['id']
            msg = service.users().messages().get(userId='me', id=msg_id).execute()
            
            payload = msg.get('payload', {})
            body = ""
            if 'body' in payload and 'data' in payload['body']:
                body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
            elif 'parts' in payload:
                for part in payload['parts']:
                    if part.get('mimeType') == 'text/plain' and 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        break

            match_codigo = re.search(r'\b\d{4,8}\b', body)
            if match_codigo:
                texto_respuesta = f"Tu código de acceso de Disney+ es:\n\n{match_codigo[0]}\n\n(Cópialo e ingrésalo en tu pantalla)"
            else:
                texto_respuesta = f"Último mensaje recibido de Disney+:\n\n{body[:200]}..."
        else:
            texto_respuesta = f"No hay solicitudes de código recientes para la cuenta ({cuenta}). Espera un minuto tras intentar iniciar sesión en tu TV y vuelve a presionar el botón."

    except Exception as e:
        texto_respuesta = "Ocurrió un error al consultar el correo de Disney+."

    teclado = {"inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]}
    enviar_mensaje(chat_id, texto_respuesta, teclado)

def enviar_mensaje(chat_id, texto, teclado=None):
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    if teclado:
        payload["reply_markup"] = teclado
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
             
