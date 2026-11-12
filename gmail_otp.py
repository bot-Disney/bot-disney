import os
import imaplib
import email
import re

GMAIL_USER = os.getenv("GMAIL_USER", "tucorreo@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "tu_app_password")

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

def obtener_ultimo_codigo_disney():
    """Lee el buzón de Gmail por IMAP y recupera el último código de 6 dígitos de Disney."""
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
            
        latest_email_id = email_ids[-1]
        status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
        
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                body = _extraer_cuerpo_correo(msg)
                
                match = re.search(r'\b\d{6}\b', body)
                if match:
                    mail.logout()
                    return match.group(0)
                    
        mail.logout()
        return None
    except Exception as e:
        print(f"Error en lectura IMAP Disney: {e}")
        return None

def obtener_ultimo_codigo_netflix():
    """Lee el buzón de Gmail por IMAP y recupera el último código de 4 dígitos de Netflix."""
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("inbox")
        
        # Busca correos recientes cuyo asunto contenga "Netflix" (cubre códigos de inicio de sesión y acceso temporal)
        status, messages = mail.search(None, '(SUBJECT "Netflix")')
        if status != "OK":
            mail.logout()
            return None
            
        email_ids = messages[0].split()
        if not email_ids:
            mail.logout()
            return None
            
        # Revisamos los últimos 2 correos por si el más reciente fue una notificación general sin código
        for email_id in reversed(email_ids[-2:]):
            status, msg_data = mail.fetch(email_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    body = _extraer_cuerpo_correo(msg)
                    
                    # Evita confundir el año actual (ej. 2026) con el código OTP de 4 dígitos
                    codigos = re.findall(r'\b\d{4}\b', body)
                    for cod in codigos:
                        if cod not in ["2025", "2026", "2027"]:
                            mail.logout()
                            return cod
                    
        mail.logout()
        return None
    except Exception as e:
        print(f"Error en lectura IMAP Netflix: {e}")
        return None
