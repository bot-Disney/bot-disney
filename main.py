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

# Llave privada protegida y codificada para prevenir errores de formato móvil
PEM_B64 = (
    "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JSUV2QUlCQURBTkJna3Foa2lHOXcw"
    "QkFRRUZBQVNDQktZd2dnU2lBZ0VBQW9JQkFRQ25ZQllwbVJRQ3VzUHYKMjA4QkIvQVpF"
    "QllVMmRtcyJJTWFLU3ZVVXdZWURHUEl1elVoYnhhVHJDdjBwSFFYml1clJaUmZBTjNh"
    "ZUJ5MHhBCnFQTVE5L2piN0RVK25YMGNqS1UzdGxCM0VGVElzczdWdThucW5WTUFTV1Zj"
    "dEZvYWgvUlZ0VWdhTFlLQVA1L2YKRGxsK3F4ZHdVMTBBd2NhaHRTL1lmZ1JyUnFZMjFT"
    "WGg3NDdKUVV0VUlHV3dsTHBVWW9tOWdqUzUwRGZNM2IKSzJybGN0MU5rb2cybWZKKzUwaW"
    "pOclVnUTYxZW1RZ09wcS9ERVdrSG4wQzBxaVVScWlWbzRtNVJ4R2xFYktwCnlzUkpWUndQ"
    "aituemhuT0FkR1dlcTFtRFZRN3FNMzZPRGhSZzJJQ0l5ZUl5bThEUEVuMEtoZW82YzRBVF"
    "lvCnhlcXwydDdMQWdNQkFBRWNnZ0VBTFhGam0vbUtXdEZkZUdaNVZVVFRFZDh2VTJrK2dT"
    "L3FaZTV1RXR6dVt5UnV1CkhJTVNzcG5JOS80YTIyekJWOW9WZjBPVXhyM29YLzc5MEpRZ1"
    "p0bTM5RmF6VVFmcjFhSVp4SnlhclF5QmVmSjA3CmxnRWw2cWVPZVF6ago5eVVnYldGZmVp"
    "eWozQ1IzOUtJRUxZNVFmMVA5dS9pei1ZcEpJQWVzMkFJcVlzWTNaCmZsTHRReXVsVVZBNG"
    "mWlBCbmNQZXB2RktiZ21hYVFmcmhZd1lTNFBmRTB3WFRpcmtUM2NaQ3JvU3paV1ZNCnBa"
    "WndkQ1VlTDJ3SFliY1A4RDJEbHUvYVhuby9qMWo3Qk5zSDl2L1Nic2U1NDdlNlRzVGZ5cX"
    "grbmlLT1p1T08KMXNnT0JRRGROTlJVYllzamlLSXl4MjlOT05yRExQMkdqTmhzY1lNMVJR"
    "S2JnUURSb3l3eEhwVHpCb29qTUJQZwpNUHVwL3JnamFqVHZhbVRVQWhOdVUtbGdqS0R0a3"
    "JLNC9heVdISmpuM0VScXhOb3NHRmhXS3NUbU1TRDlqNkdRLzJoNU1aSkN3Vm1ZdVM1NXVH"
    "UBsMjlKaC9mdG5DMTBVcExPUHE0RzdhQVA5VlBjdGxXLWhCbUFWQnB5V1cvNU01cDFqL3JU"
    "aHhhbHFrQy8vQy9SSnpQUUtnZ1BETVpEU2pzbGRYZEpGMmc4RDBvRU9wZ1RTcDRBTXdTMX"
    "VvCjNSalVIdUREN2xhTVR0Y2dFYlEvOEJLS0tuT3pibjVsSGZaWHhhSHpoQU50MVNwdTJw"
    "UmFiUHBDc1FIK3VRWAprd1dINzRkWmI4UWhLTEQvendmUGhtVXJtYllmbFg4dDVjTThHRD"
    "F1R3NyWEtQMjFFT3cySUVnRHFCc0ltU3cKVlBUWVFGYXB3S0JnQTU3RmY5aW5HbEpKMHVj"
    "ODVLRjc2eGN2YkhURmJKWTZPZGJSZ3U1YTBNcUNUTW45TFoKZXdWM3Z2aXhKMnowb281QU"
    "VrYWReVnRhVmo2aGUrS2taTTN1WU5MTEpIbXoxVGJIOV0lMTFnZDhfb3RQZ1hoSwoKaCtl"
    "RlB1SXRvZVdYMFBGRy9xcGFaYTJXSTZkQ3FNS3did3JKdWtVWEF4SWFoWjVWVWRwM1BzSU"
    "ZvR0FBWjd1CkJiQVNwT09WY3BnbjRqOTFCMWFvRUVKY0EvNHlJbWhHRHpaR1V6LyttUU1W"
    "RVMwMlgyOTNgb3laWjdEQXFHMk4KV1RXeU9UT1JUTTZmL2trUVN6MTlWdXpzaFp0Z053YS"
    "9ub1V3cW5PQ05UZlpiYTR1dGJNT1JjZzZ4cGdsT3pnCjBncjAxSlN2TU5FeFhQOWF0emtk"
    "RmxveWlpSFZqVDVKSTNUMlRyVUNnWUFMbFpaOG1pTnMybUQwNFlWTjUyUmkKZHZ5TzQ5elh"
    "Eb2tTU25lZHRHc3RkM3ptenB2clJ6V2QydjcGVydHJNR3o3aWdnaFhkamtxTlphMDBVV0hW"
    "bE5ECkQ1NFdObHVIVENwM2lDODhuQmRubHhYclYxSDF1Y010NVRMVUE3ckdHcXZpaFAyWj"
    "hUWmh3cGRuVjJYS3JTazdCCkhLUklKVnhKaGFJdDRvUjJWWXNCR2c9PQo="
)

def obtener_conexion_google():
    private_key_decoded = base64.b64decode(PEM_B64).decode('utf-8')
    
    creds_info = {
        "type": "service_account",
        "project_id": "voltaic-range-514403-v5",
        "private_key_id": "2e26db608639b5a231160463802c30bdf5c7e686",
        "private_key": private_key_decoded,
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
