import os
import re
import imaplib
import email
from datetime import datetime, timedelta
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_BOT_TOKEN_AQUI")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
GMAIL_USER = os.getenv("GMAIL_USER", "tucorreo@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "tu_app_password")

def conectar_sheets(nombre_pestana):
    """Conexión con Google Sheets usando credenciales en variable de entorno."""
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(eval(creds_json), scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    
    client = gspread.authorize(creds)
    sheet = client.open("Disney_Inventario").worksheet(nombre_pestana)
    return sheet

def registrar_en_cola_pagos(chat_id, nombre_usuario, metodo_pago, referencia, monto):
    """Registra una solicitud de pago en la pestaña Cola_Pagos como pendiente."""
    try:
        sheet = conectar_sheets("Cola_Pagos")
        sheet.append_row([str(chat_id), str(chat_id), nombre_usuario, metodo_pago, str(referencia), str(monto), "pendiente"])
        return True
    except Exception as e:
        print(f"Error en Cola_Pagos: {e}")
        return False

def asignar_perfil_con_fecha_corte(chat_id, nombre_usuario):
    """Busca un perfil libre, lo asigna y calcula la fecha de corte a 30 días."""
    try:
        sheet = conectar_sheets("Perfiles")
        data = sheet.get_all_records()
        
        hoy = datetime.now()
        fecha_corte = (hoy + timedelta(days=30)).strftime("%Y-%m-%d")
        fecha_asignacion = hoy.strftime("%Y-%m-%d")
        
        for index, row in enumerate(data, start=2):
            estado = str(row.get("estado", "")).strip().lower()
            if estado == "libre":
                sheet.update_cell(index, 4, "ocupado")
                sheet.update_cell(index, 5, str(chat_id))
                sheet.update_cell(index, 6, nombre_usuario)
                sheet.update_cell(index, 7, fecha_asignacion)
                sheet.update_cell(index, 8, fecha_corte)
                
                return {
                    "correo": row.get("correo"),
                    "password": row.get("password"),
                    "perfil": row.get("numero_perfil"),
                    "fecha_corte": fecha_corte
                }
        return None
    except Exception as e:
        print(f"Error asignando perfil: {e}")
        return None

def registrar_pago_en_sheets(chat_id, metodo_pago, referencia, monto, correo_asignado, perfil_asignado):
    """Guarda la venta procesada en la pestaña Historial_Pagos."""
    try:
        sheet = conectar_sheets("Historial_Pagos")
        fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row([str(chat_id), metodo_pago, str(referencia), str(monto), correo_asignado, perfil_asignado, fecha_hora])
    except Exception as e:
        print(f"Error en Historial_Pagos: {e}")

def aprobar_pago_por_administrador(referencia_buscada):
    """Aprueba el pago pendiente, asigna el perfil y notifica al cliente."""
    try:
        sheet_cola = conectar_sheets("Cola_Pagos")
        data_cola = sheet_cola.get_all_records()
        
        for index, row in enumerate(data_cola, start=2):
            ref = str(row.get("referencia", "")).strip()
            estado = str(row.get("estado_aprobacion", "")).strip().lower()
            
            if ref == str(referencia_buscada) and estado == "pendiente":
                chat_id = row.get("chat_id")
                nombre = row.get("nombre_usuario")
                monto = row.get("monto")
                metodo = row.get("metodo_pago")
                
                sheet_cola.update_cell(index, 7, "aprobado")
                perfil = asignar_perfil_con_fecha_corte(chat_id, nombre)
                
                if not perfil:
                    return {"status": "error", "mensaje": "Pago aprobado, pero no hay perfiles libres en inventario."}
                
                registrar_pago_en_sheets(chat_id, metodo, ref, monto, perfil["correo"], perfil["perfil"])
                
                msg = (
                    f"✅ *¡Pago verificado y aprobado por el administrador!*\n\n"
                    f"📺 *Servicio:* Disney+\n"
                    f"📧 *Correo:* `{perfil['correo']}`\n"
                    f"🔑 *Contraseña:* `{perfil['password']}`\n"
                    f"👤 *Tu Pantalla:* `{perfil['perfil']}`\n"
                    f"⏳ *Vencimiento:* `{perfil['fecha_corte']}`\n\n"
                    "¡Disfruta tu servicio! Si tu televisor requiere un código de verificación, puedes solicitarlo con el botón en el menú principal."
                )
                requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
                
                return {"status": "success", "mensaje": f"Pago {ref} aprobado. Perfil {perfil['perfil']} entregado a ID {chat_id}."}
                
        return {"status": "not_found", "mensaje": "No se encontró un pago pendiente con esa referencia."}
    except Exception as e:
        return {"status": "error", "mensaje": str(e)}

def procesar_pago_efectivo_admin(chat_id_cliente, monto):
    """Registra y entrega una pantalla de inmediato cuando se cobra en efectivo físico."""
    try:
        ref_fisica = f"EFECTIVO-{datetime.now().strftime('%H%M%S')}"
        perfil = asignar_perfil_con_fecha_corte(chat_id_cliente, "Cliente Efectivo")
        
        if not perfil:
            return {"status": "error", "mensaje": "❌ No hay perfiles libres en el inventario actual."}
            
        registrar_pago_en_sheets(chat_id_cliente, "Efectivo Físico", ref_fisica, monto, perfil["correo"], perfil["perfil"])
        
        msg = (
            "💵 *¡Pago en efectivo registrado y verificado!*\n\n"
            "📺 *Servicio:* Disney+\n"
            f"📧 *Correo:* `{perfil['correo']}`\n"
            f"🔑 *Contraseña:* `{perfil['password']}`\n"
            f"👤 *Tu Pantalla:* `{perfil['perfil']}`\n"
            f"⏳ *Vencimiento:* `{perfil['fecha_corte']}`\n\n"
            "¡Gracias por tu compra! Puedes solicitar códigos de verificación desde el menú principal del bot."
        )
        requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id_cliente, "text": msg, "parse_mode": "Markdown"})
        
        return {"status": "success", "mensaje": f"✅ Pago en efectivo procesado. Pantalla {perfil['perfil']} entregada al cliente {chat_id_cliente}."}
    except Exception as e:
        return {"status": "error", "mensaje": str(e)}

def revisar_y_notificar_vencimientos():
    """Notifica a los usuarios con perfiles a 2 días de vencer."""
    try:
        sheet = conectar_sheets("Perfiles")
        data = sheet.get_all_records()
        hoy = datetime.now()
        fecha_objetivo = (hoy + timedelta(days=2)).strftime("%Y-%m-%d")
        
        enviados = 0
        for row in data:
            if str(row.get("estado", "")).lower() == "ocupado":
                if str(row.get("fecha_corte", "")) == fecha_objetivo:
                    chat_id = str(row.get("telegram_id", ""))
                    if chat_id and chat_id != "None":
                        msg = "⚠️ *¡Hola! Tu suscripción de Disney+ vence en 2 días.* Contacta a soporte para renovar y no perder tus configuraciones."
                        requests.post(f"{TELEGRAM_URL}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"})
                        enviados += 1
        return {"avisos": enviados}
    except Exception as e:
        return {"error": str(e)}

def liberar_perfiles_vencidos():
    """Libera y resetea las filas de perfiles vencidos."""
    try:
        sheet = conectar_sheets("Perfiles")
        data = sheet.get_all_records()
        hoy = datetime.now()
        
        liberados = 0
        for index, row in enumerate(data, start=2):
            if str(row.get("estado", "")).lower() == "ocupado":
                corte_str = str(row.get("fecha_corte", ""))
                if corte_str and corte_str != "None":
                    fecha_corte = datetime.strptime(corte_str, "%Y-%m-%d")
                    if fecha_corte < hoy:
                        sheet.update_cell(index, 4, "libre")
                        sheet.update_cell(index, 5, "")
                        sheet.update_cell(index, 6, "")
                        sheet.update_cell(index, 7, "")
                        sheet.update_cell(index, 8, "")
                        liberados += 1
        return {"liberados": liberados}
    except Exception as e:
        return {"error": str(e)}

def obtener_mi_suscripcion(chat_id):
    """Devuelve la información de la suscripción activa del usuario."""
    try:
        sheet = conectar_sheets("Perfiles")
        data = sheet.get_all_records()
        for row in data:
            if str(row.get("telegram_id", "")) == str(chat_id):
                return (
                    f"📊 *Tu Suscripción Activa:*\n\n"
                    f"📧 *Correo:* `{row.get('correo')}`\n"
                    f"👤 *Pantalla:* `{row.get('numero_perfil')}`\n"
                    f"⏳ *Fecha de Corte:* `{row.get('fecha_corte')}`"
                )
        return "⚠️ No tienes ninguna suscripción activa en este momento."
    except Exception as e:
        return f"Error consultando suscripción: {e}"
