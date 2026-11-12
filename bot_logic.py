import os
import time
import datetime
from sheets_db import conectar_sheets
from gmail_otp import obtener_ultimo_codigo_disney

WHATSAPP_NUMERO = "584247091547"
ADMIN_ID = str(os.getenv("ADMIN_TELEGRAM_ID", "")).strip()

control_intentos_otp = {}
MAX_INTENTOS_RAPIDOS = 2
COOLDOWN_SEGUNDOS = 180

def procesar_mensaje_bot(chat_id, texto, nombre, username, enviar_mensaje_callback, editar_mensaje_callback=None, message_id=None, es_callback=False, callback_data=None):
    """Cerebro industrial con selector de pantallas, aprobación admin y multi-cuenta."""
    
    registrar_cliente_si_no_existe(chat_id, nombre, username)
    
    accion = callback_data if es_callback else texto.lower().strip()
    str_chat_id = str(chat_id).strip()
    
    # -------------------------------------------------------------
    # PANEL DE ADMINISTRADOR Y APROBACIÓN DE PAGOS
    # -------------------------------------------------------------
    if accion == "/admin":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            reporte = generar_reporte_admin()
            teclado = {
                "inline_keyboard": [
                    [{"text": "📋 Ver Pendientes por Aprobar", "callback_data": "admin_ver_pendientes"}],
                    [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
                ]
            }
            enviar_mensaje_callback(chat_id, reporte, teclado)
        else:
            enviar_mensaje_callback(chat_id, "⛔ No tienes permisos para acceder a este panel.", get_main_menu_keyboard())
        return

    elif accion == "admin_ver_pendientes":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            pendientes = obtener_clientes_pendientes()
            if not pendientes:
                enviar_mensaje_callback(chat_id, "✅ No hay pagos pendientes en este momento.", get_back_keyboard())
            else:
                for idx, row_idx, p in pendientes:
                    txt = (
                        f"🟡 *Pago Pendiente #{idx}* (Fila {row_idx})\n"
                        f"• *Cliente:* {p.get('Nombre')}\n"
                        f"• *Telegram ID:* `{p.get('Telegram_ID')}`\n"
                        f"• *Cuenta:* {p.get('Cuenta')}"
                    )
                    teclado_aprobar = {
                        "inline_keyboard": [
                            [{"text": "✅ Aprobar y Activar (+30 días)", "callback_data": f"aprobar_{row_idx}"}],
                            [{"text": "🔙 Volver", "callback_data": "menu_principal"}]
                        ]
                    }
                    enviar_mensaje_callback(chat_id, txt, teclado_aprobar)
        return

    elif accion.startswith("aprobar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx = int(accion.split("_")[1])
                exito = aprobar_suscripcion_sheet(row_idx)
                if exito:
                    enviar_mensaje_callback(chat_id, f"✅ ¡Suscripción de la fila {row_idx} activada con éxito por 30 días más!", get_back_keyboard())
                else:
                    enviar_mensaje_callback(chat_id, "❌ Error al actualizar la hoja de cálculo.", get_back_keyboard())
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # MENÚ PRINCIPAL
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
    # VER DATOS Y MULTI-PANTALLA
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
    # SOLICITAR CÓDIGO CON SELECTOR INTELIGENTE DE PANTALLAS
    # -------------------------------------------------------------
    elif accion == "obtener_codigo" or "codigo" in accion:
        if not verificar_cliente_activo(chat_id):
            mensaje = (
                "🔒 *ACCESO RESTRINGIDO*\n\n"
                "Para solicitar códigos, debes tener al menos una pantalla en estado *Activo* y con cuenta asignada."
            )
            teclado = get_datos_keyboard(mostrar_renovar=True)
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
            else:
                enviar_mensaje_callback(chat_id, mensaje, teclado)
            return

        suscripciones_activas = [s for s in obtener_suscripciones_por_id(chat_id) if s.get("Estado","").strip().lower() == "activo"]

        # Si tiene más de una pantalla activa, mostramos selector
        if len(suscripciones_activas) > 1 and not accion.startswith("pedir_otp_"):
            botones_selector = []
            for idx, sub in enumerate(suscripciones_activas, start=1):
                cta = sub.get("Cuenta", "Cuenta")
                pnt = sub.get("Pantalla", "1")
                botones_selector.append([{"text": f"📺 Pantalla {pnt} ({cta})", "callback_data": f"pedir_otp_{idx}"}])
            botones_selector.append([{"text": "🔙 Volver", "callback_data": "menu_principal"}])
            
            mensaje = "📺 Tienes varias pantallas activas. *¿Para cuál pantalla deseas solicitar el código de acceso?*:"
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, {"inline_keyboard": botones_selector})
            else:
                enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})
            return

        # Control de Cooldown e Intentos
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
                mensaje = f"⏳ *LÍMITE ALCANZADO*\n\nEspera *{restante // 60}m {restante % 60}s* antes de pedir otro código."
                teclado = get_back_keyboard()
                if es_callback and editar_mensaje_callback:
                    editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
                else:
                    enviar_mensaje_callback(chat_id, mensaje, teclado)
                return

        datos_usuario["intentos"] += 1
        datos_usuario["ultimo_tiempo"] = ahora

        msg_espera = "🔍 Buscando código reciente en el correo de Disney+, un momento..."
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, msg_espera, get_back_keyboard())
        else:
            enviar_mensaje_callback(chat_id, msg_espera)

        codigo = obtener_ultimo_codigo_disney()
        
        if codigo:
            mensaje = f"🔑 *Tu código de acceso de Disney+ es:*\n\n`{codigo}`\n\n_(Cópialo e ingrésalo en tu TV)_"
        else:
            mensaje = "⚠️ No se encontraron códigos nuevos. Asegúrate de haberlo solicitado en tu TV."

        teclado = get_back_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)

    elif accion.startswith("pedir_otp_"):
        # Maneja la selección directa de pantalla
        # Reutilizamos la lógica de obtención de código
        process_otp_direct(chat_id, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback, str_chat_id)

    # -------------------------------------------------------------
    # RENOVACIÓN Y SOPORTE
    # -------------------------------------------------------------
    elif accion == "renovar_suscripcion":
        suscripciones = obtener_suscripciones_por_id(chat_id)
        cantidad = len(suscripciones) if suscripciones else 1
        
        texto_wa = f"Hola, quiero reportar mi pago de renovación por 30 días. Mi ID de Telegram es: {str_chat_id} ({cantidad} pantalla/s)."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        
        teclado_renovar = {
            "inline_keyboard": [
                [{"text": "💳 Reportar Pago por WhatsApp", "url": url_whatsapp}],
                [{"text": "➕ Comprar Pantalla Adicional", "callback_data": "comprar_extra"}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = (
            "🔄 *RENOVACIÓN DE SUSCRIPCIÓN (+30 DÍAS)*\n\n"
            f"• *Tu ID de Cliente:* `{str_chat_id}`\n"
            "Realiza tu pago y presiona el botón para enviarlo con tus datos prellenados:"
        )
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_renovar)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_renovar)

    elif accion == "comprar_extra":
        texto_wa = f"Hola, quiero adquirir una pantalla adicional de Disney+. Mi ID de Telegram es: {str_chat_id}."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        
        teclado_extra = {
            "inline_keyboard": [
                [{"text": "🛒 Solicitar por WhatsApp", "url": url_whatsapp}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = "➕ *ADQUIRIR PANTALLA ADICIONAL*\n\nPresiona el botón para coordinar tu nueva pantalla:"
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_extra)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_extra)

    elif accion == "soporte" or "pago" in accion:
        texto_wa = f"Hola, necesito soporte con mi servicio de Disney+. Mi ID es: {str_chat_id}."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        teclado_whatsapp = {
            "inline_keyboard": [
                [{"text": "💬 Abrir WhatsApp", "url": url_whatsapp}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = "💬 *ATENCIÓN AL CLIENTE*\n\nComunícate con soporte:"
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_whatsapp)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_whatsapp)

    else:
        mensaje = "¡Hola! Selecciona una opción del menú de abajo:"
        teclado = get_main_menu_keyboard()
        enviar_mensaje_callback(chat_id, mensaje, teclado)


def process_otp_direct(chat_id, message_id, enviar_cb, editar_cb, es_cb, str_chat_id):
    msg = "🔍 Buscando código reciente en el correo de Disney+..."
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, msg, get_back_keyboard())
    else:
        enviar_cb(chat_id, msg)
        
    codigo = obtener_ultimo_codigo_disney()
    mensaje = f"🔑 *Tu código de acceso de Disney+ es:*\n\n`{codigo}`\n\n_(Cópialo e ingrésalo en tu TV)_" if codigo else "⚠️ No se encontraron códigos nuevos."
    
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, mensaje, get_back_keyboard())
    else:
        enviar_cb(chat_id, mensaje, get_back_keyboard())


# ==========================================
# FUNCIONES AUXILIARES Y DE GOOGLE SHEETS
# ==========================================
def obtener_suscripciones_por_id(chat_id):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        str_chat_id = str(chat_id).strip()
        return [f for f in registros if str(f.get("Telegram_ID", "")).strip() == str_chat_id]
    except Exception as e:
        print(f"Error: {e}")
        return []

def registrar_cliente_si_no_existe(chat_id, nombre, username):
    try:
        if obtener_suscripciones_por_id(chat_id):
            return
        sheet = conectar_sheets()
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        sheet.append_row([str(chat_id), nombre_completo, "Por Asignar", "Por Asignar", "", "Pendiente Pago"])
    except Exception as e:
        print(f"Error registrando: {e}")

def verificar_cliente_activo(chat_id):
    for sub in obtener_suscripciones_por_id(chat_id):
        if str(sub.get("Estado", "")).strip().lower() == "activo" and str(sub.get("Cuenta", "")).strip().lower() not in ("", "por asignar"):
            return True
    return False

def obtener_clientes_pendientes():
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        pendientes = []
        for idx, row in enumerate(registros, start=2): # Comienza en fila 2 por el encabezado
            if "pendiente" in str(row.get("Estado", "")).strip().lower():
                pendientes.append((len(pendientes)+1, idx, row))
        return pendientes
    except Exception as e:
        print(f"Error obteniendo pendientes: {e}")
        return []

def aprobar_suscripcion_sheet(row_idx):
    try:
        sheet = conectar_sheets()
        # Sumar 30 días a la fecha actual
        nueva_fecha = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        sheet.update_cell(row_idx, 5, nueva_fecha) # Columna E: Vencimiento
        sheet.update_cell(row_idx, 6, "Activo")    # Columna F: Estado
        return True
    except Exception as e:
        print(f"Error aprobando suscripción: {e}")
        return False

def verificar_alerta_vencimiento(vencimiento_str, estado_str):
    if estado_str.lower() != "activo":
        return "🔴"
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            fecha_venc = datetime.datetime.strptime(vencimiento_str, fmt).date()
            dias = (fecha_venc - datetime.date.today()).days
            if dias < 0: return "⚠️ *(Vencida)*"
            elif dias == 0: return "🟠 *(Vence HOY)*"
            elif dias <= 3: return f"🟡 *(Vence en {dias} días)*"
            return "🟢"
        except ValueError:
            continue
    return ""

def generar_reporte_admin():
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        activos = sum(1 for r in registros if str(r.get("Estado","")).lower() == "activo")
        pendientes = sum(1 for r in registros if "pendiente" in str(r.get("Estado","")).lower())
        unicos = len(set(str(r.get("Telegram_ID","")) for r in registros if r.get("Telegram_ID")))
        return (
            "📊 *PANEL DE CONTROL INDUSTRIAL*\n\n"
            f"👥 *Clientes únicos:* {unicos}\n"
            f"📺 *Total pantallas:* {len(registros)}\n"
            f"🟢 *Activas:* {activos}\n"
            f"🟡 *Pendientes:* {pendientes}"
        )
    except Exception as e:
        return f"❌ Error: {e}"

def get_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📲 Ver mis datos / Pantallas", "callback_data": "ver_datos"}],
            [{"text": "🔑 Solicitar Código Disney", "callback_data": "obtener_codigo"}],
            [{"text": "🔄 Renovar (+30 días)", "callback_data": "renovar_suscripcion"}, {"text": "➕ Otra Pantalla", "callback_data": "comprar_extra"}],
            [{"text": "💬 Soporte / Pagos", "callback_data": "soporte"}]
        ]
    }

def get_datos_keyboard(mostrar_renovar=False):
    botones = []
    if mostrar_renovar: botones.append([{"text": "🔄 Renovar Suscripción", "callback_data": "renovar_suscripcion"}])
    botones.append([{"text": "➕ Comprar Pantalla Adicional", "callback_data": "comprar_extra"}])
    botones.append([{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}])
    return {"inline_keyboard": botones}

def get_back_keyboard():
    return {
        "inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]
    }
