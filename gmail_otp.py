import os
import imaplib
import email
import re
from email.utils import parsedate_to_datetime
import datetime

GMAIL_USER = os.getenv("GMAIL_USER", "tucorreo@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "tu_app_password")

# Tiempo máximo de validez de un código OTP en minutos
MINUTOS_MAXIMOS_VALIDOS = 4

def _extraer_cuerpo_correo(msg):
    """Extrae el texto del correo soportando tanto text/plain como text/html limpio."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="ignore")
            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode("utf-8", errors="ignore")
                    body = re.sub(r'<[^>]+>', ' ', html)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            raw = payload.decode("utf-8", errors="ignore")
            body = re.sub(r'<[^>]+>', ' ', raw) if msg.get_content_type() == "text/html" else raw
    return body

def _es_correo_reciente(msg):
    """Verifica si la fecha del correo está dentro del margen de minutos permitidos."""
    try:
        fecha_str = msg.get("Date")
        if fecha_str:
            fecha_correo = parsedate_to_datetime(fecha_str)
            if fecha_correo.tzinfo is not None:
                # Normalizar a UTC o comparar de forma segura quitando la zona horaria si genera conflicto
                ahora = datetime.datetime.now(datetime.timezone.utc)
                diferencia = ahora - fecha_correo.astimezone(datetime.timezone.utc)
            else:
                ahora = datetime.datetime.now()
                diferencia = ahora - fecha_correo
            
            # Retorna True si el correo tiene menos o igual a los minutos permitidos
            return diferencia.total_seconds() <= (MINUTOS_MAXIMOS_VALIDOS * 60)
    except Exception as e:
        print(f"Aviso al validar fecha del correo: {e}")
    
    # Si por alguna razón no se pudo leer la fecha, por seguridad permitimos evaluar (o puedes retornar False)
    return True

def obtener_ultimo_codigo_disney():
    """Lee el buzón de Gmail por IMAP y recupera el último código de 6 dígitos de Disney si es reciente."""
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("inbox")
        
        status, messages = mail.search(None, '(SUBJECT "Disney")')
        if status != "OK":
            mail.logout()
            return None
            
        email_ids = messages[0].split()
        if not email_ids:
            mail.logout()
            return None
            
        # Revisamos los últimos 3 correos por si acaso
        for email_id in reversed(email_ids[-3:]):
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Validar que el correo sea reciente antes de buscar el código
                    if _es_correo_reciente(msg):
                        body = _extraer_cuerpo_correo(msg)
                        match = re.search(r'\b\d{6}\b', body)
                        if match:
                            mail.logout()
                            return match.group(0)
                    else:
                        # Como los IDs vienen en orden cronológico inverso, si el último ya es viejo, los anteriores también lo serán
                        break
                    
        mail.logout()
        return None
    except Exception as e:
        print(f"Error en lectura IMAP Disney: {e}")
        return None

def obtener_ultimo_codigo_netflix():
    """Lee el buzón de Gmail por IMAP y recupera el último código de 4 dígitos de Netflix si es reciente."""
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("inbox")
        
        status, messages = mail.search(None, '(SUBJECT "Netflix")')
        if status != "OK":
            mail.logout()
            return None
            
        email_ids = messages[0].split()
        if not email_ids:
            mail.logout()
            return None
            
        # Revisamos los últimos 3 correos
        for email_id in reversed(email_ids[-3:]):
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Validar que el correo sea reciente
                    if _es_correo_reciente(msg):
                        body = _extraer_cuerpo_correo(msg)
                        codigos = re.findall(r'\b\d{4}\b', body)
                        for cod in codigos:
                            if cod not in ["2025", "2026", "2027"]:
                                mail.logout()
                                return cod
                    else:
                        break
                    
        mail.logout()
        return None
    except Exception as e:
        print(f"Error en lectura IMAP Netflix: {e}")
        return None
