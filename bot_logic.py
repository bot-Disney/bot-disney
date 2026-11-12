import os
import time
from gmail_otp import obtener_ultimo_codigo_disney, obtener_ultimo_codigo_netflix

# Configuración de Cooldown anti-spam para códigos OTP (en segundos)
COOLDOWN_SEGUNDOS = 60
MAX_INTENTOS_RAPIDOS = 3
control_intentos_otp = {}

def procesar_mensaje_bot(
    chat_id, 
    user_id, 
    texto_mensaje, 
    foto_file_id, 
    username, 
    nombre, 
    message_id,
    enviar_mensaje_callback, 
    editar_mensaje_callback, 
    es_callback,
    verificar_cliente_activo_fn,
    obtener_suscripciones_fn,
    registrar_cliente_fn,
    enviar_admin_pago_fn,
    actualizar_vencimiento_fn
):
    """
    Controlador central de la lógica del bot de Telegram para streaming (Disney y Netflix).
    """
    str_chat_id = str(chat_id)
    accion = texto_mensaje.strip().lower() if texto_mensaje else ""

    # 1. Registrar cliente automáticamente si manda /start o interactúa
    try:
        registrar_cliente_fn(chat_id, username, nombre)
    except Exception as e:
        print(f"Error registrando cliente automáticamente: {e}")

    # 2. Manejo de Fotos (Comprobantes de pago)
    if foto_file_id:
        try:
            enviar_admin_pago_fn(chat_id, username, nombre, foto_file_id)
            mensaje = "📸 **¡Comprobante recibido con éxito!**\n\nHa sido enviado al administrador para su revisión y aprobación. Te notificaremos en cuanto tus 30 días estén activos. 🚀"
            teclado = get_datos_keyboard(mostrar_renovar=True)
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
            else:
                enviar_mensaje_callback(chat_id, mensaje, teclado)
        except Exception as e:
            print(f"Error al procesar foto de pago: {e}")
            enviar_mensaje_callback(chat_id, "❌ Ocurrió un error al enviar tu comprobante. Inténtalo de nuevo.")
        return

    # 3. Menú Principal o /start
    if accion in ["/start", "menu_principal", "🏠 menú principal", "volver"]:
        mensaje = (
            "🎬 **¡Bienvenido a tu servicio de Streaming!**\n\n"
            "Gestiona tus pantallas y códigos al instante desde los botones de abajo 👇"
        )
        teclado = get_datos_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)
        return

    # 4. Opción: Mis Datos / Vencimiento
    elif accion in ["mis datos", "vencimiento", "estado", "datos"]:
        suscripciones = obtener_suscripciones_fn(chat_id)
        if not suscripciones:
            mensaje = "❌ No encontramos registros activos con este usuario de Telegram. Contacta al administrador."
        else:
            mensaje = "📋 **Tus Datos y Suscripciones:**\n\n"
            for sub in suscripciones:
                srv = sub.get("Servicio", "Disney+").strip()
                cta = sub.get("Cuenta", "Cuenta").strip()
                pnt = sub.get("Pantalla", "1").strip()
                est = sub.get("Estado", "Inactivo").strip()
                venc = sub.get("Vencimiento", "N/A").strip()
                mensaje += f"• 📺 **{srv}**\n  - Cuenta: `{cta}`\n  - Pantalla: `{pnt}`\n  - Estado: *{est}*\n  - Vence: `{venc}`\n\n"
        
        teclado = get_datos_keyboard(mostrar_renovar=True)
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)
        return

    # 5. Opción: Renovar / Instrucciones de Pago
    elif accion in ["renovar", "pagar", "comprar"]:
        mensaje = (
            "🔄 **¿Cómo renovar tus 30 días?**\n\n"
            "1️⃣ Realiza tu pago correspondiente.\n"
            "2️⃣ **Envía la captura de pantalla (foto) de tu pago directamente por aquí** en este chat.\n"
            "3️⃣ El administrador aprobará tu recarga al instante.\n\n"
            "¡Así de fácil mantienes tu pantalla activa!"
        )
        teclado = get_back_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)
        return

    # 6. Opción: Solicitar Código OTP (Disney+ o Netflix)
    elif accion == "obtener_codigo" or "codigo" in accion:
        if not verificar_cliente_activo_fn(chat_id):
            mensaje = "🔒 **ACCESO RESTRINGIDO**\n\nPara solicitar códigos, debes tener al menos una pantalla en estado *Activo*."
            teclado = get_datos_keyboard(mostrar_renovar=True)
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
            else:
                enviar_mensaje_callback(chat_id, mensaje, teclado)
            return

        suscripciones_activas = [s for s in obtener_suscripciones_fn(chat_id) if s.get("Estado", "").strip().lower() == "activo"]

        # Si el usuario tiene múltiples pantallas activas (ej: Disney y Netflix), se le muestra un selector
        if len(suscripciones_activas) > 1 and not accion.startswith("pedir_otp_"):
            botones_selector = []
            for idx, sub in enumerate(suscripciones_activas):
                srv = sub.get("Servicio", "Disney+").strip()
                cta = sub.get("Cuenta", "Cuenta")
                pnt = sub.get("Pantalla", "1")
                botones_selector.append([{"text": f"📺 {srv} - Pantalla {pnt}", "callback_data": f"pedir_otp_{idx}"}])
            botones_selector.append([{"text": "🔙 Volver", "callback_data": "menu_principal"}])
            
            mensaje = "📺 Tienes varias pantallas activas. **¿Para cuál deseas solicitar el código?**:"
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, {"inline_keyboard": botones_selector})
            else:
                enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})
            return

        # Si tiene 1 sola pantalla activa o por defecto
        servicio_seleccionado = suscripciones_activas[0].get("Servicio", "Disney").strip().lower() if suscripciones_activas else "disney"
        ejecutar_busqueda_otp(chat_id, str_chat_id, servicio_seleccionado, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)
        return

    elif accion.startswith("pedir_otp_"):
        try:
            idx_sub = int(accion.split("_")[-1])
            suscripciones_activas = [s for s in obtener_suscripciones_fn(chat_id) if s.get("Estado", "").strip().lower() == "activo"]
            servicio_seleccionado = suscripciones_activas[idx_sub].get("Servicio", "Disney").strip().lower() if idx_sub < len(suscripciones_activas) else "disney"
            ejecutar_busqueda_otp(chat_id, str_chat_id, servicio_seleccionado, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)
        except Exception as e:
            print(f"Error procesando botón OTP múltiple: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error al seleccionar la pantalla. Inténtalo de nuevo.")
        return

    # 7. Mensaje por defecto si no reconoce el texto
    else:
        mensaje = "🤖 No reconozco ese comando. Utiliza los botones del menú principal para navegar:"
        teclado = get_datos_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)


# --- FUNCIONES AUXILIARES DE INTERFAZ (TECLADOS) ---

def get_datos_keyboard(mostrar_renovar=False):
    """Genera el teclado principal interactivo en Telegram."""
    keyboard = [
        [{"text": "🔑 Solicitar Código", "callback_data": "obtener_codigo"}],
        [{"text": "📲 Mis Datos y Vencimiento", "callback_data": "mis_datos"}]
    ]
    if mostrar_renovar:
        keyboard.append([{"text": "🔄 Renovar (Enviar Comprobante)", "callback_data": "renovar"}])
    return {"inline_keyboard": keyboard}


def get_back_keyboard():
    """Genera un teclado simple con botón de retorno al menú principal."""
    return {"inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]}


def ejecutar_busqueda_otp(chat_id, str_chat_id, servicio, message_id, enviar_cb, editar_cb, es_cb):
    """Controla el tiempo de espera (cooldown) y busca el código de Disney+ o Netflix."""
    ahora = time.time()
    if str_chat_id not in control_intentos_otp:
        control_intentos_otp[str_chat_id] = {"intentos": 0, "ultimo_tiempo": 0}

    datos_usuario = control_intentos_otp[str_chat_id]
    if ahora - datos_usuario["ultimo_tiempo"] > COOLDOWN_SEGUNDOS:
        datos_usuario["intentos"] = 0

    if datos_usuario["intentos"] >= MAX_INTENTOS_RAPIDOS:
        transcurrido = ahora - datos_usuario["ultimo_tiempo"]
        if transcurrido < COOLDOWN_SEGUNDOS:
            restante = int(COOLDOWN_SEGUNDOS - transcurrido)
            mensaje = f"⏳ **LÍMITE ALCANZADO**\n\nEspera **{restante // 60}m {restante % 60}s** antes de pedir otro código."
            if es_cb and editar_cb:
                editar_cb(chat_id, message_id, mensaje, get_back_keyboard())
            else:
                enviar_cb(chat_id, mensaje, get_back_keyboard())
            return

    datos_usuario["intentos"] += 1
    datos_usuario["ultimo_tiempo"] = ahora

    es_netflix = "netflix" in servicio
    nombre_plataforma = "Netflix" if es_netflix else "Disney+"

    msg_espera = f"🔍 Buscando código reciente de **{nombre_plataforma}** en el correo, un momento..."
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, msg_espera, get_back_keyboard())
    else:
        enviar_cb(chat_id, msg_espera)

    codigo = obtener_ultimo_codigo_netflix() if es_netflix else obtener_ultimo_codigo_disney()

    if codigo:
        mensaje = f"🔑 **Tu código de acceso de {nombre_plataforma} es:**\n\n`{codigo}`\n\n_(Cópialo e ingrésalo en tu pantalla)_"
    else:
        mensaje = f"⚠️ No se encontraron códigos nuevos de **{nombre_plataforma}**. Asegúrate de haberlo solicitado en tu TV hace unos segundos e intenta de nuevo."

    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, mensaje, get_back_keyboard())
    else:
        enviar_cb(chat_id, mensaje, get_back_keyboard())
            
