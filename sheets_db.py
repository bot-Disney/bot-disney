import gspread
from google.oauth2.service_account import Credentials

# Definir los permisos necesarios para Google Sheets y Google Drive
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def conectar_sheets():
    """Carga las credenciales directamente desde el Secret File configurado en Render."""
    try:
        # Apunta directamente al archivo secreto credentials.json en Render
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
        
        # Autorizar gspread
        client = gspread.authorize(creds)
        
        # Abrir la hoja de cálculo y la pestaña (ajústalo si tus nombres son distintos)
        sheet = client.open("Disney_Inventario").worksheet("Perfiles")
        return sheet

    except Exception as e:
        print(f"Error al conectar con Google Sheets: {e}")
        raise e

def consultar_suscripcion(telegram_id):
    """Busca la suscripción del usuario por su ID de Telegram en la hoja de cálculo."""
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        
        for fila in registros:
            # Asegúrate de que la columna en tu Google Sheets se llame Telegram_ID
            if str(fila.get("Telegram_ID")) == str(telegram_id):
                return fila
                
        return None
    except Exception as e:
        print(f"Error al consultar la suscripción: {e}")
        return None
