import os
import time
import datetime
from sheets_db import conectar_sheets
from gmail_otp import obtener_ultimo_codigo_disney

WHATSAPP_NUMERO = "584247091547"

# Lee exactamente tu variable de entorno configurada en Render
ADMIN_ID = str(os.getenv("ADMIN_TELEGRAM_ID", "")).strip()

# Control de intentos y tiempo de espera (Cooldown) en memoria: 
# {chat_id: {"intentos": int, "ultimo_tiempo": float}}
control_intentos_otp = {}
MAX_INTENTOS_RAPIDOS = 2       # Permitir 2 intentos seguidos
COOLDOWN_SEGUNDOS = 180        # 3 minutos de espera tras agotar los 2 intentos

def procesar_mensaje_bot(chat_id, texto, nombre, username, enviar_mensaje_callback, editar_mensaje_callback=None, message_id=None, es_callback=False, callback_data=None):
    """Cerebro unificado del bot con multi-pantalla, 2 intentos de código, renovación y panel admin."""
    
    # 1. Registrar al cliente automáticamente si no existe en la hoja 'Clientes'
    registrar_cliente_si_no_existe(chat_id, nombre, username)
    
    accion = callback_data if es_callback else texto.lower().strip()
    str_chat_id = str(chat_id).strip()
    
    # -------------------------------------------------------------
    # COMANDO EXCLUSIVO: PANEL DE ADMINISTRADOR (/admin)
    # -------------------------------------------------------------
    if accion == "/admin":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            reporte = generar_reporte_admin()
            enviar_mensaje_callback(chat_id, reporte, get_back_keyboard())
        else:
            enviar_mensaje_callback(chat_id, "⛔ No tienes permisos para acceder a este panel.", get_main_menu_keyboard())
        return

    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: MENÚ PRINCIPAL
    # -------------------------------------------------------------
    elif accion == "menu_principal" or accion == "/start" or accion == "/menu":
        texto_menu = (
            "🤖 *Bienvenido al servicio de Streaming*\n\n"
            "Gestiona tus pantallas, códigos de acceso y renovaciones desde los botones de abajo:"
        )
        teclado = get_main_menu_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, texto_menu, teclado)
        else:
            enviar_mensaje_callback(chat_id, texto_menu, teclado)

    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: VER DATOS DE LA CUENTA / MULTI-PANTALLA
    # -------------------------------------------------------------
    elif accion == "ver_datos" or "cuenta" in accion:
        suscripciones = obtener_suscripciones_por_id(chat_id)
        
        if not suscripciones:
            mensaje = "⚠️ No tienes ninguna pantalla registrada con este ID de Telegram."
            teclado = get_back_keyboard()
        else:
            total = len(suscripciones)
            encabezado = f"📋 *TUS DATOS DE SUSCRIPCIÓN ({total} {'pantalla' if total == 1 else 'pantallas'})*\n\n"
            bloques = []
            tiene_por_renovar = False

            for idx, sub in enumerate(suscripciones, start=1):
                cuenta = sub.get("Cuenta", "Por Asignar")
                pantalla = str(sub.get("Pantalla", "Por Asignar"))
                vencimiento = str(sub.get("Vencimiento", "Sin fecha")).strip() or "Sin fecha"
                estado = str(sub.get("Estado", "Pendiente Pago")).strip()
                
                alerta_vencimiento = verificar_alerta_vencimiento(vencimiento, estado)
                if "Vencida" in alerta_vencimiento or "Vence" in alerta_vencimiento or estado.lower() != "activo":
                    tiene_por_renovar = True

                bloque = (
                    f"🔹 *Suscripción #{idx}*\n"
                    f"• *Cuenta:* `{cuenta}`\n"
                    f"• *Pantalla N°:* {pantalla}\n"
                    f"• *Vencimiento:* {vencimiento} {alerta_vencimiento}\n"
                    f"• *Estado:* {estado}"
                )
                bloques.append(bloque)

            mensaje = encabezado + "\n\n".join(bloques)
            teclado = get_datos_keyboard(mostrar_renovar=tiene_por_renovar)
            
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)

    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: SOLICITAR CÓDIGO DISNEY (Con 2 Intentos y Cooldown)
    # -------------------------------------------------------------
    elif accion == "obtener_codigo" or "codigo" in accion:
        # 1. Validar si tiene al menos una pantalla activa
        if not verificar_cliente_activo(chat_id):
            mensaje = (
                "🔒 *ACCESO RESTRINGIDO*\n\n"
                "Para solicitar códigos de acceso, debes tener al menos una suscripción en estado *Activo* y con una cuenta asignada.\n\n"
                "Si tu pantalla venció o aún no has reportado tu pago, presiona renovar abajo:"
            )
            teclado = get_datos_keyboard(mostrar_renovar=True)
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
            else:
                enviar_mensaje_callback(chat_id, mensaje, teclado)
            return

        # 2. Control de Intentos y Cooldown (Permite 2 intentos seguidos)
        ahora = time.time()
        if str_chat_id not in control_intentos_otp:
            control_intentos_otp[str_chat_id] = {"intentos": 0, "ultimo_tiempo": 0}

        datos_usuario = control_intentos_otp[str_chat_id]
        
        # Si ya pasó el tiempo de cooldown, reiniciamos el contador de intentos
        if ahora - datos_usuario["ultimo_tiempo"] > COOLDOWN_SEGUNDOS:
            datos_usuario["intentos"] = 0

        # Si agotó los 2 intentos rápidos, exigimos esperar
        if datos_usuario["intentos"] >= MAX_INTENTOS_RAPIDOS:
            transcurrido = ahora - datos_usuario["ultimo_tiempo"]
            if transcurrido < COOLDOWN_SEGUNDOS:
                restante = int(COOLDOWN_SEGUNDOS - transcurrido)
                minutos = restante // 60
                segundos = restante % 60
                mensaje = (
                    f"⏳ *LÍMITE DE INTENTOS ALCANZADO*\n\n"
                    f"Has solicitado códigos 2 veces seguidas. Por seguridad y para no saturar el correo, debes esperar *{minutos}m {segundos}s* antes de volver a intentar."
                )
                teclado = get_back_keyboard()
                if es_callback and editar_mensaje_callback:
                    editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
                else:
                    enviar_mensaje_callback(chat_id, mensaje, teclado)
                return

        # Incrementamos intento y actualizamos marca de tiempo
        datos_usuario["intentos"] += 1
        datos_usuario["ultimo_tiempo"] = ahora

        # 3. Informar búsqueda al usuario
        intentos_restantes = MAX_INTENTOS_RAPIDOS - datos_usuario["intentos"]
        msg_espera = f"🔍 Buscando código reciente en el correo de Disney+ (Intento {datos_usuario['intentos']}/{MAX_INTENTOS_RAPIDOS})..."
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, msg_espera, get_back_keyboard())
        else:
            enviar_mensaje_callback(chat_id, msg_espera)

        # 4. Leer el código usando gmail_otp.py
        codigo = obtener_ultimo_codigo_disney()
        
        if codigo:
            mensaje = (
                f"🔑 *Tu código de acceso de Disney+ es:*\n\n"
                f"`{codigo}`\n\n"
                f"_(Tócalo para copiar e ingrésalo en tu pantalla)_"
            )
        else:
            mensaje = (
                "⚠️ No se encontraron códigos nuevos en este momento.\n\n"
                f"Asegúrate de haberlo solicitado en tu TV. Te queda(n) *{intentos_restantes} intento(s)* rápido(s) antes del bloqueo temporal."
            )

        teclado = get_back_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)

    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: AUTOGESTIÓN DE RENOVACIÓN (+30 DÍAS)
    # -------------------------------------------------------------
    elif accion == "renovar_suscripcion":
        suscripciones = obtener_suscripciones_por_id(chat_id)
        cantidad = len(suscripciones) if suscripciones else 1
        
        texto_wa = (
            f"Hola, quiero renovar mi servicio de Disney+ por 30 días más. "
            f"Mi ID de Telegram es: {str_chat_id} ({cantidad} pantalla/s)."
        )
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        
        teclado_renovar = {
            "inline_keyboard": [
                [{"text": "💳 Reportar Pago de Renovación", "url": url_whatsapp}],
                [{"text": "➕ Comprar Pantalla Adicional", "callback_data": "comprar_extra"}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = (
            "🔄 *RENOVACIÓN DE SUSCRIPCIÓN (+30 DÍAS)*\n\n"
            f"• *Tu ID de Cliente:* `{str_chat_id}`\n"
            f"• *Pantallas registradas:* {cantidad}\n\n"
            "Presiona el botón de abajo para enviar tu comprobante por WhatsApp con tus datos prellenados y activar tu mes al instante:"
        )
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_renovar)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_renovar)

    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: COMPRAR PANTALLA ADICIONAL
    # -------------------------------------------------------------
    elif accion == "comprar_extra":
        texto_wa = f"Hola, quiero adquirir una pantalla adicional de Disney+. Mi ID de Telegram es: {str_chat_id}."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        
        teclado_extra = {
            "inline_keyboard": [
                [{"text": "🛒 Solicitar Pantalla por WhatsApp", "url": url_whatsapp}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = (
            "➕ *ADQUIRIR PANTALLA ADICIONAL*\n\n"
            "Puedes agregar todas las pantallas que necesites bajo tu mismo usuario de Telegram.\n\n"
            "Presiona el botón de abajo para coordinar el pago y asignarte tu nuevo perfil:"
        )
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_extra)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_extra)

    # -------------------------------------------------------------
    # OPCIÓN / BOTÓN: SOPORTE Y PAGOS (WhatsApp)
    # -------------------------------------------------------------
    elif accion == "soporte" or "pago" in accion:
        texto_wa = f"Hola, necesito información o soporte con mi servicio de Disney+. Mi ID es: {str_chat_id}."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
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
# FUNCIONES AUXILIARES Y MULTI-PANTALLA
# ==========================================
def obtener_suscripciones_por_id(chat_id):
    """Devuelve TODAS las filas/pantallas asociadas a un mismo Telegram ID."""
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        
        str_chat_id = str(chat_id).strip()
        encontrados = []
        for fila in registros:
            if str(fila.get("Telegram_ID", "")).strip() == str_chat_id:
                encontrados.append(fila)
        return encontrados
    except Exception as e:
        print(f"Error en obtener_suscripciones_por_id: {e}")
        return []

def registrar_cliente_si_no_existe(chat_id, nombre, username):
    """Registra automáticamente al usuario en Google Sheets si no tiene ninguna fila aún."""
    try:
        suscripciones = obtener_suscripciones_por_id(chat_id)
        if suscripciones:
            return  # Ya tiene al menos un registro

        sheet = conectar_sheets()
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        sheet.append_row([str(chat_id), nombre_completo, "Por Asignar", "Por Asignar", "", "Pendiente Pago"])
    except Exception as e:
        print(f"Error registrando cliente: {e}")

def verificar_cliente_activo(chat_id):
    """Verifica si el cliente tiene AL MENOS UNA pantalla en estado 'Activo' con cuenta asignada."""
    suscripciones = obtener_suscripciones_por_id(chat_id)
    if not suscripciones:
        return False

    for sub in suscripciones:
        estado = str(sub.get("Estado", "")).strip().lower()
        cuenta = str(sub.get("Cuenta", "")).strip().lower()
        if estado == "activo" and cuenta not in ("", "por asignar", "n/a"):
            return True
            
    return False

def verificar_alerta_vencimiento(vencimiento_str, estado_str):
    """Evalúa si la fecha está vencida o próxima a vencer."""
    if estado_str.lower() != "activo":
        return "🔴"
    
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            fecha_venc = datetime.datetime.strptime(vencimiento_str, fmt).date()
            hoy = datetime.date.today()
            dias_restantes = (fecha_venc - hoy).days
            
            if dias_restantes < 0:
                return "⚠️ *(Vencida)*"
            elif dias_restantes == 0:
                return "🟠 *(Vence HOY)*"
            elif dias_restantes <= 3:
                return f"🟡 *(Vence en {dias_restantes} días)*"
            else:
                return "🟢"
        except ValueError:
            continue
    return ""

def generar_reporte_admin():
    """Genera estadísticas en tiempo real para el administrador."""
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        
        total_filas = len(registros)
        activos = 0
        pendientes = 0
        inactivos_vencidos = 0
        usuarios_unicos = set()
        
        for fila in registros:
            tid = str(fila.get("Telegram_ID", "")).strip()
            if tid:
                usuarios_unicos.add(tid)
                
            estado = str(fila.get("Estado", "")).strip().lower()
            if estado == "activo":
                activos += 1
            elif "pendiente" in estado:
                pendientes += 1
            else:
                inactivos_vencidos += 1
                
        return (
            "📊 *PANEL DE CONTROL ADMINISTRADOR*\n\n"
            f"👥 *Clientes únicos:* {len(usuarios_unicos)}\n"
            f"📺 *Total pantallas registradas:* {total_filas}\n"
            f"🟢 *Pantallas Activas:* {activos}\n"
            f"🟡 *Pendientes por Pago:* {pendientes}\n"
            f"🔴 *Vencidas / Inactivas:* {inactivos_vencidos}"
        )
    except Exception as e:
        return f"❌ Error generando reporte: {e}"


# ==========================================
# DISEÑO DE TECLADOS (INLINE KEYBOARDS)
# ==========================================
def get_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📲 Ver mis datos / Pantallas", "callback_data": "ver_datos"}],
            [{"text": "🔑 Solicitar Código Disney", "callback_data": "obtener_codigo"}],
            [
                {"text": "🔄 Renovar (+30 días)", "callback_data": "renovar_suscripcion"},
                {"text": "➕ Otra Pantalla", "callback_data": "comprar_extra"}
            ],
            [{"text": "💬 Soporte / Pagos", "callback_data": "soporte"}]
        ]
    }

def get_datos_keyboard(mostrar_renovar=False):
    botones = []
    if mostrar_renovar:
        botones.append([{"text": "🔄 Renovar Suscripción Ahora", "callback_data": "renovar_suscripcion"}])
    botones.append([{"text": "➕ Comprar Pantalla Adicional", "callback_data": "comprar_extra"}])
    botones.append([{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}])
    return {"inline_keyboard": botones}

def get_back_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
        ]
    }
    
