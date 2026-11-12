import datetime
from sheets_db import conectar_sheets
from gmail_otp import obtener_ultimo_codigo_disney

WHATSAPP_NUMERO = "584247091547"

def procesar_mensaje_bot(chat_id, texto, nombre, username, enviar_mensaje_callback, editar_mensaje_callback=None, message_id=None, es_callback=False, callback_data=None):
    """Cerebro unificado del bot: maneja mensajes, comandos y botones interactivos."""
    
    # 1. Registrar al cliente automáticamente si no existe en la hoja 'Clientes'
    registrar_cliente_si_no_existe(chat_id, nombre, username)
    
    # Manejar acciones de botones flotantes (Callbacks) o texto normal
    accion = callback_data if es_callback else texto.lower().strip()
    
    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: MENÚ PRINCIPAL
    # -------------------------------------------------------------
    if accion == "menu_principal" or accion == "/start" or accion == "/menu":
        texto_menu = (
            "🤖 **Bienvenido al servicio de Streaming**\n\n"
            "Selecciona una opción en los botones de abajo:"
        )
        teclado = get_main_menu_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, texto_menu, teclado)
        else:
            enviar_mensaje_callback(chat_id, texto_menu, teclado)

    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: VER DATOS DE LA CUENTA / PANTALLA
    # -------------------------------------------------------------
    elif accion == "ver_datos" or "cuenta" in accion:
        cliente = obtener_datos_cliente_por_id(chat_id)
        
        if not cliente:
            mensaje = "⚠️ No tienes ninguna pantalla registrada con este ID de Telegram."
        else:
            cuenta = cliente.get("Cuenta", "N/A")
            pantalla = str(cliente.get("Pantalla", "N/A"))
            vencimiento_raw = cliente.get("Vencimiento", "Sin fecha")
            estado = cliente.get("Estado", "Activo")
            
            mensaje = (
                f"📋 *TUS DATOS DE SUSCRIPCIÓN*\n\n"
                f"• *Cuenta:* `{cuenta}`\n"
                f"• *Pantalla N°:* {pantalla}\n"
                f"• *Vencimiento:* {vencimiento_raw}\n"
                f"• *Estado:* {estado}"
            )
            
        teclado = get_back_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)

    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: SOLICITAR CÓDIGO DISNEY (Vía Gmail OTP)
    # -------------------------------------------------------------
    elif accion == "obtener_codigo" or "codigo" in accion:
        # Validar si el cliente está activo antes de entregar el código
        if not verificar_cliente_activo(chat_id):
            mensaje = (
                "🔒 *ACCESO RESTRINGIDO*\n\n"
                "Para solicitar códigos de acceso, tu suscripción debe estar Activa y con una cuenta asignada. "
                "Si ya realizaste tu pago, comunícate por soporte para activar tu saldo."
            )
            teclado = get_back_keyboard()
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
            else:
                enviar_mensaje_callback(chat_id, mensaje, teclado)
            return

        # Informar búsqueda
        msg_espera = "🔍 Buscando código reciente en el correo de Disney+, un momento..."
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, msg_espera, get_back_keyboard())
        else:
            enviar_mensaje_callback(chat_id, msg_espera)

        # Leer el código usando gmail_otp.py
        codigo = obtener_ultimo_codigo_disney()
        
        if codigo:
            mensaje = f"🔑 Tu código de acceso de Disney+ es:\n\n`{codigo}`\n\n(Tócalo para copiar e ingrésalo en tu pantalla)"
        else:
            mensaje = "⚠️ No hay solicitudes de código recientes. Espera 1 minuto tras solicitar el código en tu TV y vuelve a presionar el botón."

        teclado = get_back_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)

    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: SOPORTE Y PAGOS (WhatsApp)
    # -------------------------------------------------------------
    elif accion == "soporte" or "pago" in accion:
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text=Hola,%20quiero%20información%20sobre%20los%20pagos%20o%20renovaciones%20de%20Disney+."
        teclado_whatsapp = {
            "inline_keyboard": [
                [{"text": "💬 Abrir Chat de WhatsApp", "url": url_whatsapp}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = "💬 *ATENCIÓN AL CLIENTE Y PAGOS*\n\nPresiona el botón de abajo para comunicarte directamente por WhatsApp:"
        
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_whatsapp)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_whatsapp)

    # -------------------------------------------------------------
    # MENSAJE POR DEFECTO
    # -------------------------------------------------------------
    else:
        mensaje = "¡Hola! Selecciona una opción del menú de abajo:"
        teclado = get_main_menu_keyboard()
        enviar_mensaje_callback(chat_id, mensaje, teclado)


# ==========================================
# FUNCIONES AUXILIARES DE GOOGLE SHEETS
# ==========================================
def obtener_datos_cliente_por_id(chat_id):
    """Busca en la hoja 'Clientes' el registro del usuario usando su Telegram ID."""
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        
        str_chat_id = str(chat_id).strip()
        for fila in registros:
            if str(fila.get("Telegram_ID", "")).strip() == str_chat_id:
                return fila
        return None
    except Exception as e:
        print(f"Error en obtener_datos_cliente_por_id: {e}")
        return None

def registrar_cliente_si_no_existe(chat_id, nombre, username):
    """Registra automáticamente al usuario en Google Sheets si es su primera vez."""
    try:
        cliente = obtener_datos_cliente_por_id(chat_id)
        if cliente:
            return  # Ya existe

        sheet = conectar_sheets()
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        
        # Estructura de columnas: [Telegram_ID, Nombre, Cuenta, Pantalla, Vencimiento, Estado]
        sheet.append_row([str(chat_id), nombre_completo, "Por Asignar", "Por Asignar", "", "Pendiente Pago"])
    except Exception as e:
        print(f"Error registrando cliente: {e}")

def verificar_cliente_activo(chat_id):
    """Verifica si el cliente tiene una cuenta válida y estado activo."""
    cliente = obtener_datos_cliente_por_id(chat_id)
    if not cliente:
        return False

    estado = str(cliente.get("Estado", "")).lower()
    cuenta = str(cliente.get("Cuenta", "")).lower()

    return (estado == "activo" and cuenta != "" and cuenta != "por asignar" and cuenta != "n/a")


# ==========================================
# DISEÑO DE TECLADOS (INLINE KEYBOARDS)
# ==========================================
def get_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📲 Ver mis datos / Pantalla", "callback_data": "ver_datos"}],
            [{"text": "🔑 Solicitar Código Disney", "callback_data": "obtener_codigo"}],
            [{"text": "💬 Soporte / Solicitar Pago", "callback_data": "soporte"}]
        ]
    }

def get_back_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
        ]
    }
    
