from sheets_db import conectar_sheets

def procesar_mensaje_bot(chat_id, texto, enviar_mensaje_callback):
    """Maneja las interacciones del bot enviando botones y respuestas automáticas."""
    texto_lower = texto.lower().strip()
    
    # 1. BOTÓN O TEXTO: CONSULTAR MI CUENTA / PANTALLA
    if "📺 ver mi pantalla" in texto_lower or "cuenta" in texto_lower or texto_lower == "/cuenta":
        datos = consultar_datos_cliente(chat_id)
        if datos:
            correo = datos.get("Correo", "No especificado")
            pin = datos.get("PIN", "Sin PIN")
            pantalla = datos.get("Pantalla", "Completa")
            vencimiento = datos.get("Vencimiento", "Por verificar")
            
            respuesta = (
                f"🎬 **Tus Datos de Acceso - Disney+** 🎬\n\n"
                f"📧 **Correo:** `{correo}`\n"
                f"🔢 **PIN:** `{pin}`\n"
                f"📺 **Perfil/Pantalla:** {pantalla}\n"
                f"📅 **Vence el:** {vencimiento}\n\n"
                f"⚠️ *Recuerda no cambiar la contraseña ni el correo.*"
            )
        else:
            respuesta = "❌ No encontramos ninguna suscripción activa registrada con tu usuario. Contacta al administrador si ya pagaste."
        
        enviar_mensaje_callback(chat_id, respuesta, incluir_botones=True)
    
    # 2. BOTÓN O TEXTO: SOPORTE
    elif "🛠️ soporte técnico" in texto_lower or "soporte" in texto_lower:
        respuesta = (
            "🛠️ **Centro de Soporte**\n\n"
            "Si tienes problemas con tu pantalla o error de hogar, envía un mensaje con tu captura de pantalla y te atenderemos."
        )
        enviar_mensaje_callback(chat_id, respuesta, incluir_botones=True)

    # 3. BOTÓN O TEXTO: REPORTAR PAGO
    elif "💳 reportar pago" in texto_lower or "pago" in texto_lower:
        respuesta = (
            "💳 **Reportar Pago**\n\n"
            "Envía el comprobante de tu pago móvil o transferencia por aquí para actualizar tu fecha de vencimiento."
        )
        enviar_mensaje_callback(chat_id, respuesta, incluir_botones=True)
        
    # 4. MENSAJE DE BIENVENIDA CON EL TECLADO DE BOTONES
    else:
        respuesta = (
            "🤖 **¡Bienvenido a tu servicio de Streaming!**\n\n"
            "Selecciona una opción del menú de aquí abajo para continuar sin escribir comandos:"
        )
        enviar_mensaje_callback(chat_id, respuesta, incluir_botones=True)

def consultar_datos_cliente(telegram_id):
    """Busca en Google Sheets el registro del cliente usando su Telegram ID."""
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        
        for fila in registros:
            if str(fila.get("Telegram_ID")) == str(telegram_id):
                return fila
                
        return None
    except Exception as e:
        print(f"Error consultando los datos en Sheets: {e}")
        return None
