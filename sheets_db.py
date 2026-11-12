import os
import json
import gspread
from google.oauth2.service_account import Credentials

# 1. Definir los permisos necesarios para Google Sheets y Google Drive
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def conectar_sheets():
    """Carga las credenciales desde la variable de entorno de Render y conecta con Google Sheets."""
    try:
        # 2. Leer la variable de entorno segura configurada en Render
        credentials_json_string = os.getenv("GOOGLE_CREDENTIALS_JSON")
        
        if not credentials_json_string:
            raise ValueError("No se encontró la variable de entorno GOOGLE_CREDENTIALS_JSON en Render.")

        # 3. Convertir el texto JSON plano en un diccionario de Python
        creds_dict = json.loads(credentials_json_string)

        # 4. Generar las credenciales utilizando google-auth
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        
        # 5. Autorizar gspread
        client = gspread.authorize(creds)
        
        # 6. Abrir la hoja de cálculo y la pestaña (asegúrate de que los nombres coincidan con tus archivos)
        sheet = client.open("Disney_Inventario").worksheet("Perfiles")
        return sheet

    except Exception as e:
        print(f"Error al conectar con Google Sheets: {e}")
        raise e

def consultar_suscripcion(telegram_id):
    """Ejemplo de función para buscar la suscripción del usuario por su ID de Telegram."""
    try:
        sheet = conectar_sheets()
        # Obtiene todos los registros de la hoja
        registros = sheet.get_all_records()
        
        # Busca el registro que coincida con el ID de Telegram
        for fila in registros:
            # Asegúrate de que 'Telegram_ID' coincida exactamente con el encabezado de tu columna en Sheets
            if str(fila.get("Telegram_ID")) == str(telegram_id):
                return fila
                
        return None
    except Exception as e:
        print(f"Error al consultar la suscripción: {e}")
        return None
