import requests

# Tu URL oficial de Apps Script que acabamos de verificar
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbyiT5N-YF3X6Tk2egHY7zl9CwH1jvyjwsIEOr9lhn_YevtzcZ1HCAqxzqrFT9EYBWMr/exec"

def consultar_datos_sheet(chat_id):
    payload = {
        "action": "consultar_datos",
        "chat_id": str(chat_id)
    }
    try:
        response = requests.post(APPS_SCRIPT_URL, json=payload)
        return response.json() 
    except Exception as e:
        print(f"Error de conexión: {e}")
        return {"status": "error"}

def obtener_codigo_gmail(chat_id):
    payload = {
        "action": "obtener_codigo",
        "chat_id": str(chat_id)
    }
    try:
        response = requests.post(APPS_SCRIPT_URL, json=payload)
        return response.json()
    except Exception as e:
        print(f"Error de conexión: {e}")
        return {"status": "error"}
        
