import os
import imaplib
import email
import re

GMAIL_USER = os.getenv("GMAIL_USER", "tucorreo@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "tu_app_password")

def obtener_ultimo_codigo_disney():
    """Lee el buzón de Gmail por IMAP y recupera el último código de 6 dígitos de Disney."""
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("inbox")
        
        status, messages = mail.search(None, '(SUBJECT "Disney")')
        if status != "OK":
            return None
            
        email_ids = messages[0].split()
        if not email_ids:
            return None
            
        latest_email_id = email_ids[-1]
        status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
        
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                
                match = re.search(r'\b\d{6}\b', body)
                if match:
                    mail.logout()
                    return match.group(0)
                    
        mail.logout()
        return None
    except Exception as e:
        print(f"Error en lectura IMAP: {e}")
        return None
