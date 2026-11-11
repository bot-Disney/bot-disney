from fastapi import FastAPI, Request
import requests
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import base64
import re
from datetime import datetime, date

app = FastAPI()

BOT_TOKEN = "9197975180:AAGGidSbVmRlJTMDU8UhXEFP9h2oOmt1vJU"
WHATSAPP_NUMERO = "584247091547"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/gmail.readonly"
]

def obtener_conexion_google():
    # Llave privada en bloque multilínea nativo (Inmune a errores de formato y padding)
    private_key_content = """-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQCnYBYPmRQCusPv
208BB/AZBYU2kmsIfMKvuUWwYYDGPIuZUhbxaTrCv0pHQXimTrBZRfAN3byBy0xA
qPMQ9/jb7DU+nX0cjKU3tlB3EFTIss7Vu8nqnVMASWVctFoah/RVtUgaLYKAP5/f
Dll+qxdwXU1pAwcahtS/YfgRrRqY2aSXh747JQUtUIGVwlLpUYom9wGjS50DfM3b
K2rlct1Nkog2mxfJ+50ijNrUgQ61emQgOpq/DEWkH4oC0qiURiqVo4m5RxGlEbKp
ysRJVRwPj+nzhnOAdGYeq1mDVQ7qM36ODhREx2ICIyeIym8DPAen0Kheo6c4ATIo
xerq2d7LAgMBAAECggEALXFjm/mKWtFdeGZ5VUTT9d8vU2k+gS/qZe5uEtzuKyRu
HIMSspnI9+4a2yzV9oVf0OUxr3oX/790JQwZ7m39FazUqfr1aIZxJyarQyBefJ07
lgEl6bqsOeQzjo9y9UgbWRfeiyj3CR39KIELYF5Qf1P9u/iz+YpJAes2AIqYsY3Z
flLqReulUVA4fZlPBncPepvFKbgmabAq5rhYwYS4pfE0wXTirkT+cZCroSvzDUWM
pMZsdCUeL2wHYbcP8D2Dlu/aXno/j1j7BNsH9v/Sbds547e6TsTfYqx+niKOZuOO
1sgOBQDdNNRUbYsJiKYx29NONrDLP2GjNhycUYM1XQKBgQDRoywxHpTzBoojMBPg
MPup/rgjajTvamTUAhNuU+lgjKDTkrK4/ayWHjjn3ERqxNxsGFhWKsTmMSD9j6GQ
2h5MZJCwVmUysE55uHMPl29Jh/ftnC10UpLOPq4G7aApQ9VPctlW+hBmAVBvpYWW
/5M5p1j/rThxalqkC//C/RJzPQKBgQDMZDSjsdxXdJ+2g8D0oEOpgTSp4AMwS1uo
3RjUHuDD7NlaMTtcgEbQ/8BKKKnOzbn5lHfZXxaHzhANt1Spu2pRabPpCsQH+uQX
kuWH74dZb8QhKLd/zwfPkxsMubrYflX8t5cM8GD1uGsrXKP21EOw2IEgDqBsImSw
V+TYVFaapwKBgA57Ff9inGlZJ0uc85KF76xjcvbHTFbJY6OdbRgu5a0MqcNTm9LZ
ewV3mvixJ2y0ooE5AUkadTVtaVj6he+KkZM3UyNLJHxm31TbH9+Q11gd80tPgXhK
h+eFPuItoeWX0PFG/qpaZa2WI6dCqMKwbswJukUXAxIahZ5VUdp3PsIFAoGAAZcu
CbASpOOVcpgn4j91B1aoEEJcA/4yImhGDzCGUz/+mQMVES02X939oxYZ7DARqG2N
WTWyOTBTU6f/kqqQsz19VuzshZtgNwa/noUwqnOCNTfZ5ba4utbMORcg6xpglOzg
0gr01jSvMNExvXP9atzkdFloyi6iVfT5JO3TFrUCgYALlrZ8miNs8mD04YVN52Ri
ndvY49xZDokSSnedtGstd3mzp6vR2Xd2v7ervrMGz7i9ghXDkbjqNLa0zUWHVBlND
D54WNluHTCp3iB48nBdnlxXrV1H1ucMt5TLUA7rGpqivhPZ8TZhwpdnV2XKrSN7B
HKRIJVxJhaIt4oR2VYsBKg==
-----END PRIVATE KEY-----"""

    creds_info = {
        "type": "service_account",
        "project_id": "voltaic-range-514403-v5",
        "private_key_id": "2e26db608639b5a231160463802c30bdf5c7e686",
        "private_key": private_key_content,
        "client_email": "bot-disney@voltaic-range-514403-v5.iam.gserviceaccount.com",
        "token_uri": "https://oauth2.googleapis.com/token"
    }
    
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client, creds

@app.get("/")
async def home():
    return {"status": "¡El bot de Disney+ está activo y funcionando!"}

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

@app.get("/enviar-recordatorios")
async def enviar_recordatorios_automaticos():
    try:
        client, _ = obtener_conexion_google()
        sh = client.open("Clientes")
        worksheet = sh.worksheet("Clientes")
        registros = worksheet.get_all_values()
        
        hoy = date.today()
        enviados = 0
        
        for row in registros[1:]:
            if len(row) < 6:
                continue
            chat_id = row[0]
            nombre = row[1]
            cuenta = row[2]
            vencimiento_str = row[4].strip()
            estado = row[5].strip()
            
            if estado.lower() != "activo":
                continue
                
            try:
                fecha_venc = datetime.strptime(vencimiento_str, "%Y-%m-%d").date()
                dias_restantes = (fecha_venc - hoy).days
                
                if dias_restantes in [0, 1]:
                    mensaje = f"⚠️ *AVISO DE VENCIMIENTO*\n\nHola {nombre}, tu suscripción de Disney+ (cuenta `{cuenta}`) "
                    if dias_restantes == 0:
                        mensaje += "*vence HOY*."
                    else:
                        mensaje += "vence mañana."
                    
                    mensaje += "\n\nComunícate a soporte para realizar tu renovación."
                    
                    payload = {"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
                    enviados += 1
            except ValueError:
                continue
                
        return {"status": "success", "recordatorios_enviados": enviados}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def verificar_o_registrar_usuario(chat_id, nombre_usuario):
    try:
        client, _ = obtener_conexion_google()
        sh = client.open("Clientes")
        worksheet = sh.worksheet("Clientes")
        try:
            cell = worksheet.find(str(chat_id))
        except:
            cell = None
        if not cell:
            worksheet.append_row([str(chat_id), nombre_usuario, "Por asignar", "N/A", "Sin fecha", "Activo"])
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
        client, _ = obtener_conexion_google()
        sh = client.open("Clientes")
        worksheet = sh.worksheet("Clientes")
        try:
            cell = worksheet.find(str(chat_id))
        except:
            cell = None
        
        if cell:
            row_values = worksheet.row_values(cell.row)
            cuenta = row_values[2] if len(row_values) > 2 else "Por asignar"
            pantalla = row_values[3] if len(row_values) > 3 else "N/A"
            vencimiento = row_values[4] if len(row_values) > 4 else "Sin fecha"
            estado = row_values[5] if len(row_values) > 5 else "Activo"
            mensaje = f"Tus datos de suscripción:\n\n• Cuenta: {cuenta}\n• Pantalla N°: {pantalla}\n• Vencimiento: {vencimiento}\n• Estado: {estado}"
        else:
            mensaje = "⚠️ No se encontraron tus datos en el sistema."
    except Exception as e:
        mensaje = f"❌ Error:\n`{str(e)}`"
        
    teclado = {"inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]}
    enviar_mensaje(chat_id, mensaje, teclado)

def procesar_solicitud_codigo(chat_id):
    try:
        client, creds = obtener_conexion_google()
        sh = client.open("Clientes")
        worksheet = sh.worksheet("Clientes")
        try:
            cell = worksheet.find(str(chat_id))
        except:
            cell = None
            
        if not cell:
            enviar_mensaje(chat_id, "⚠️ No estás registrado en el sistema.")
            return
            
        row_values = worksheet.row_values(cell.row)
        cuenta = row_values[2] if len(row_values) > 2 else ""
        
        if not cuenta or cuenta.lower() in ["por asignar", "n/a", ""]:
            enviar_mensaje(chat_id, "⚠️ Aún no tienes una cuenta de Disney+ asignada. Comunícate a soporte.")
            return

        enviar_mensaje(chat_id, f"🔍 Buscando código reciente para el correo:\n`{cuenta}`\n\nUn momento...")

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
                texto_respuesta = f"Tu código de acceso de Disney+ es:\n\n`{match_codigo[0]}`\n\n(Cópialo e ingrésalo en tu pantalla)"
            else:
                texto_respuesta = f"Último mensaje recibido de Disney+:\n\n{body[:200]}..."
        else:
            texto_respuesta = f"No hay códigos recientes para la cuenta `{cuenta}`."

    except Exception as e:
        texto_respuesta = f"❌ Error de correo:\n`{str(e)}`"

    teclado = {"inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]}
    enviar_mensaje(chat_id, texto_respuesta, teclado)

def enviar_mensaje(chat_id, texto, teclado=None):
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "Markdown"}
    if teclado:
        payload["reply_markup"] = teclado
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload)
            
