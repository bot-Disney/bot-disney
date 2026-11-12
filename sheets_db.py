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
        
        # ⚠️ IMPORTANTE: Asegúrate de que "Disney_Inventario" sea el nombre exacto de tu archivo en Drive
        # y que la pestaña de abajo se llame exactamente "Clientes"
        sheet = client.open("Disney_Inventario").worksheet("Clientes")
        return sheet

    except Exception as e:
        print(f"Error al conectar con Google Sheets: {e}")
        raise e
        
