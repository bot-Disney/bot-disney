import os
import time
import datetime
import requests
from sheets_db import conectar_sheets
from gmail_otp import obtener_ultimo_codigo_disney, obtener_ultimo_codigo_netflix

WHATSAPP_NUMERO = "584247091547"
ADMIN_ID = str(os.getenv("ADMIN_TELEGRAM_ID", "")).strip()

# =============================================================
# CONFIGURACIÓN DE PRECIOS (USD/USDT) Y DATOS DE PAGO MÓVIL
# =============================================================
PRECIO_DISNEY_USD = 5.0   # Precio en USD de Disney+
PRECIO_NETFLIX_USD = 4.5  # Precio en USD de Netflix
TASA_RESPALDO_BS = 65.0   # Tasa de respaldo por si fallan las consultas externas

PAGO_MOVIL_BANCO = "🏦 Provincial (0108)"
PAGO_MOVIL_CEDULA = "27538779"
PAGO_MOVIL_TELEFONO = "04247091547"

control_intentos_otp = {}
MAX_INTENTOS_RAPIDOS = 2
COOLDOWN_SEGUNDOS = 180

# Control de usuarios que están esperando enviar captura de pago
esperando_captura_pago = set()


def safe_get(row_dict, key, default=""):
    """Lee de manera segura un diccionario de Google Sheets ignorando espacios y mayúsculas en los encabezados."""
    if not isinstance(row_dict, dict):
        return default
    for k, v in row_dict.items():
        if str(k).strip().lower() == str(key).strip().lower():
            val = str(v).strip()
            return val if val != "" else default
    return default


def obtener_tasa_usdt_hoy():
    """Consulta la tasa USDT/VES del día (Binance P2P con respaldo automático) sin bloquear el bot."""
    try:
        url_binance = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
        payload = {
            "asset": "USDT",
            "fiat": "VES",
            "merchantCheck": False,
            "page": 1,
            "payTypes": [],
            "publisherType": None,
            "rows": 5,
            "tradeType": "BUY"
        }
        res = requests.post(url_binance, json=payload, timeout=4)
        if res.status_code == 200:
            anuncios = res.json().get("data", [])
            precios = [float(a["adv"]["price"]) for a in anuncios if "adv" in a and "price" in a["adv"]]
            if precios:
                return round(sum(precios) / len(precios), 2)
    except Exception as e:
        print(f"Aviso: No se pudo leer Binance P2P ({e}), probando respaldo...")

    try:
        res_alt = requests.get("https://pydolarve.org/api/v1/dollar?monitor=enparalelovzla", timeout=3)
        if res_alt.status_code == 200:
            precio = res_alt.json().get("price")
            if precio:
                return round(float(precio), 2)
    except Exception:
        pass

    return TASA_RESPALDO_BS


def procesar_mensaje_bot(chat_id, texto, nombre, username, enviar_mensaje_callback, editar_mensaje_callback=None, message_id=None, es_callback=False, callback_data=None, photo_file_id=None, enviar_foto_callback=None):
    """Cerebro industrial multi-plataforma (Disney+ y Netflix) con soporte para múltiples pantallas, perfiles sucesivos y antidoble clic."""
    
    str_chat_id = str(chat_id).strip()
    accion = callback_data if es_callback else texto.lower().strip()

    # -------------------------------------------------------------
    # CAPTURA DE FOTO / COMPROBANTE ENVIADO POR EL CLIENTE
    # -------------------------------------------------------------
    if photo_file_id and str_chat_id in esperando_captura_pago:
        esperando_captura_pago.remove(str_chat_id)
        
        suscripciones = obtener_suscripciones_por_id(chat_id)
        cuenta_asociada = "Por Asignar"
        servicio_asociado = "Disney+"
        row_idx_pendiente = None
        
        if suscripciones:
            for s in suscripciones:
                if "pendiente" in safe_get(s, "Estado", "").lower():
                    cuenta_asociada = safe_get(s, "Cuenta", "Por Asignar")
                    servicio_asociado = safe_get(s, "Servicio", "Disney+")
                    row_idx_pendiente = s.get("_row_index")
                    break
            else:
                cuenta_asociada = safe_get(suscripciones[0], "Cuenta", "Por Asignar")
                servicio_asociado = safe_get(suscripciones[0], "Servicio", "Disney+")
                row_idx_pendiente = suscripciones[0].get("_row_index")

        if not row_idx_pendiente:
            row_idx_pendiente = obtener_o_crear_fila_pendiente(str_chat_id, nombre, cuenta_asociada, servicio_asociado, username)

        if ADMIN_ID and enviar_foto_callback:
            caption_admin = (
                "🔔 *¡NUEVO COMPROBANTE DE PAGO (FOTO)!* 🔔\n\n"
                f"• *Cliente:* {nombre} (@{username})\n"
                f"• *Telegram ID:* `{str_chat_id}`\n"
                f"• *Servicio:* {servicio_asociado}\n"
                f"• *Cuenta/Detalle:* {cuenta_asociada}"
            )
            
            teclado_admin = {
                "inline_keyboard": [
                    [{"text": "✅ Aprobar y Activar (+30 días)", "callback_data": f"aprobar_{row_idx_pendiente}_digital"}],
                    [{"text": "❌ Rechazar", "callback_data": f"rechazar_{row_idx_pendiente}"}]
                ]
            }
            enviar_foto_callback(int(ADMIN_ID), photo_file_id, caption_admin, teclado_admin)

        texto_confirmacion = (
            "✅ *¡Captura de pago recibida con éxito!*\n\n"
            "Se la hemos enviado al administrador. En breve tu pago será verificado y tu cuenta activada.\n\n"
            "💡 *Sugerencia:* Si deseas agilizarlo aún más, puedes avisarnos también por WhatsApp:"
        )
        texto_wa = f"Hola, acabo de enviar mi captura de pago por el bot. Mi ID es: {str_chat_id}."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        
        teclado_cliente = {
            "inline_keyboard": [
                [{"text": "💬 Avisar por WhatsApp", "url": url_whatsapp}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        enviar_mensaje_callback(chat_id, texto_confirmacion, teclado_cliente)
        return

    if not es_callback and str_chat_id in esperando_captura_pago and texto and texto.lower().strip() not in ("efectivo", "/efectivo"):
        esperando_captura_pago.remove(str_chat_id)
        procesar_texto_reporte(chat_id, texto, nombre, username, enviar_mensaje_callback, str_chat_id, suscripciones_asociadas=obtener_suscripciones_por_id(chat_id), enviar_foto_callback=enviar_foto_callback)
        return

    # -------------------------------------------------------------
    # COMANDO SECRETO / TEXTO: PAGO EN EFECTIVO
    # -------------------------------------------------------------
    if accion == "efectivo" or accion == "/efectivo":
        if str_chat_id in esperando_captura_pago:
            esperando_captura_pago.remove(str_chat_id)

        suscripciones = obtener_suscripciones_por_id(chat_id)
        botones_selector = []

        for sub in suscripciones:
            r_idx = sub.get("_row_index")
            srv = safe_get(sub, "Servicio", "Disney+")
            pnt = safe_get(sub, "Pantalla", "Perfil 1")
            cta = safe_get(sub, "Cuenta", "Cuenta")
            botones_selector.append([{"text": f"🔄 Renovar {srv} - {pnt} ({cta})", "callback_data": f"efectivo_fila_{r_idx}"}])

        botones_selector.append([{"text": f"➕ Nueva Pantalla Disney+ (${PRECIO_DISNEY_USD:.2f})", "callback_data": "efectivo_nuevo_disney"}])
        botones_selector.append([{"text": f"➕ Nueva Pantalla Netflix (${PRECIO_NETFLIX_USD:.2f})", "callback_data": "efectivo_nuevo_netflix"}])
        botones_selector.append([{"text": "🔙 Cancelar y Volver", "callback_data": "menu_principal"}])

        mensaje = (
            "💵 *PAGO EN EFECTIVO*\n\n"
            "Selecciona qué pantalla vas a renovar o si deseas adquirir una pantalla adicional nueva:"
        )
        enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})
        return

    elif accion.startswith("efectivo_fila_"):
        try:
            row_idx_elegido = int(accion.split("_")[-1])
            notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, row_idx_elegido, "Renovación", enviar_mensaje_callback, editar_mensaje_callback, message_id, es_callback)
        except Exception as e:
            print(f"Error en efectivo fila: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())
        return

    elif accion.startswith("efectivo_nuevo_"):
        try:
            servicio_elegido = "Netflix" if "netflix" in accion else "Disney+"
            nueva_fila_idx = crear_nueva_fila_pendiente(str_chat_id, nombre, username, servicio_elegido)
            notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, nueva_fila_idx, "Pantalla Nueva", enviar_mensaje_callback, editar_mensaje_callback, message_id, es_callback)
        except Exception as e:
            print(f"Error en efectivo nuevo: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # PANEL DE ADMINISTRADOR Y APROBACIÓN
    # -------------------------------------------------------------
    if accion == "/admin":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            reporte = generar_reporte_admin()
            teclado = {
                "inline_keyboard": [
                    [{"text": "📋 Ver Pagos Pendientes", "callback_data": "admin_ver_pendientes"}],
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
                    srv_p = safe_get(p, "Servicio", "Disney+")
                    pnt_p = safe_get(p, "Pantalla", "Perfil 1")
                    txt = (
                        f"🟡 *Pago Pendiente #{idx}* (Fila {row_idx})\n"
                        f"• *Cliente:* {safe_get(p, 'Nombre')}\n"
                        f"• *Telegram ID:* `{safe_get(p, 'Telegram_ID')}`\n"
                        f"• *Servicio:* {srv_p} ({pnt_p})\n"
                        f"• *Cuenta:* {safe_get(p, 'Cuenta')}"
                    )
                    teclado_aprobar = {
                        "inline_keyboard": [
                            [{"text": "✅ Aprobar y Activar (+30 días)", "callback_data": f"aprobar_{row_idx}_digital"}],
                            [{"text": "❌ Rechazar", "callback_data": f"rechazar_{row_idx}"}]
                        ]
                    }
                    enviar_mensaje_callback(chat_id, txt, teclado_aprobar)
        return

    elif accion.startswith("aprobar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                partes_ap = accion.split("_")
                row_idx = int(partes_ap[1])
                es_efectivo = (len(partes_ap) > 2 and partes_ap[2].strip() == "efectivo")
                metodo_pago = "Efectivo" if es_efectivo else "Pago Móvil / Digital"

                exito, tid_cliente, ya_estaba_activa, nombre_cliente, srv_aprobado, perfil_asignado, tipo_operacion = aprobar_suscripcion_sheet(row_idx)
                
                if message_id:
                    quitar_botones_telegram(chat_id, message_id)

                if ya_estaba_activa:
                    enviar_mensaje_callback(chat_id, f"ℹ️ La suscripción de la fila {row_idx} ya había sido aprobada previamente.", get_back_keyboard())
                    return

                if exito:
                    monto_venta = PRECIO_NETFLIX_USD if "netflix" in str(srv_aprobado).lower() else PRECIO_DISNEY_USD
                    
                    registrar_venta_en_historial(
                        nombre_cliente, tid_cliente, srv_aprobado, perfil_asignado,
                        monto_venta, tipo_operacion, metodo_pago
                    )

                    enviar_mensaje_callback(
                        chat_id,
                        f"✅ ¡Fila {row_idx} activada y registrada en *Ventas*!\n"
                        f"• *Servicio:* {srv_aprobado}\n"
                        f"• *Perfil:* {perfil_asignado}\n"
                        f"• *Tipo:* {tipo_operacion}\n"
                        f"• *Método:* {metodo_pago}",
                        get_back_keyboard()
                    )
                    if tid_cliente:
                        try:
                            enviar_mensaje_callback(int(tid_cliente), "🎉 *¡Tu pago ha sido verificado y aprobado!*\n\nTu servicio ya se encuentra *Activo* por 30 días más. ¡Disfruta tu contenido!", get_main_menu_keyboard())
                        except Exception:
                            pass
                else:
                    enviar_mensaje_callback(chat_id, "❌ Error al actualizar la hoja de cálculo.", get_back_keyboard())
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    elif accion.startswith("rechazar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            row_idx = int(accion.split("_")[1])
            if message_id:
                quitar_botones_telegram(chat_id, message_id)
            enviar_mensaje_callback(chat_id, f"❌ Pago de la fila {row_idx} marcado como rechazado/revisar.", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # MENÚ PRINCIPAL Y CLIENTE
    # -------------------------------------------------------------
    elif accion == "menu_principal" or accion == "/start" or accion == "/menu":
        if str_chat_id in esperando_captura_pago:
            esperando_captura_pago.remove(str_chat_id)
            
        texto_menu = (
            "🤖 *Bienvenido al servicio de Streaming*\n\n"
            "Gestiona tus pantallas, códigos de acceso y renovaciones desde los botones de abajo:"
        )
        teclado = get_main_menu_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, texto_menu, teclado)
        else:
            enviar_mensaje_callback(chat_id, texto_menu, teclado)

    elif accion == "ver_datos" or "cuenta" in accion:
        suscripciones = obtener_suscripciones_por_id(chat_id)
        if not suscripciones:
            mensaje = "⚠️ Aún no tienes ninguna pantalla registrada con este ID de Telegram.\n\nSelecciona *➕ Otra Pantalla* o *🔄 Renovar* en el menú para comenzar."
            teclado = get_back_keyboard()
        else:
            total = len(suscripciones)
            encabezado = f"📋 *TUS DATOS DE SUSCRIPCIÓN ({total} {'pantalla' if total == 1 else 'pantallas'})*\n\n"
            bloques = []
            tiene_por_renovar = False

            for idx, sub in enumerate(suscripciones, start=1):
                servicio = safe_get(sub, "Servicio", "Disney+")
                cuenta = safe_get(sub, "Cuenta", "Por Asignar")
                pantalla = safe_get(sub, "Pantalla", "Perfil 1")
                vencimiento = safe_get(sub, "Vencimiento", "Sin fecha")
                estado = safe_get(sub, "Estado", "Pendiente Pago")
                
                alerta_vencimiento = verificar_alerta_vencimiento(vencimiento, estado)
                if "Vencida" in alerta_vencimiento or "Vence" in alerta_vencimiento or estado.lower() != "activo":
                    tiene_por_renovar = True

                bloques.append(
                    f"🔹 *Suscripción #{idx} ({servicio})*\n"
                    f"• *Cuenta:* `{cuenta}`\n"
                    f"• *Perfil Asignado:* {pantalla}\n"
                    f"• *Vencimiento:* {vencimiento} {alerta_vencimiento}\n"
                    f"• *Estado:* {estado}"
                )

            mensaje = encabezado + "\n\n".join(bloques)
            teclado = get_datos_keyboard(mostrar_renovar=tiene_por_renovar)
            
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)

    elif accion == "obtener_codigo" or "codigo" in accion:
        if not verificar_cliente_activo(chat_id):
            mensaje = "🔒 *ACCESO RESTRINGIDO*\n\nPara solicitar códigos, debes tener al menos una pantalla en estado *Activo*."
            teclado = get_datos_keyboard(mostrar_renovar=True)
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
            else:
                enviar_mensaje_callback(chat_id, mensaje, teclado)
            return

        suscripciones_activas = [s for s in obtener_suscripciones_por_id(chat_id) if safe_get(s, "Estado", "").lower() == "activo"]

        if len(suscripciones_activas) > 1 and not accion.startswith("pedir_otp_"):
            botones_selector = []
            for idx, sub in enumerate(suscripciones_activas):
                srv = safe_get(sub, "Servicio", "Disney+")
                cta = safe_get(sub, "Cuenta", "Cuenta")
                pnt = safe_get(sub, "Pantalla", "Perfil 1")
                botones_selector.append([{"text": f"📺 {srv} - {pnt} ({cta})", "callback_data": f"pedir_otp_{idx}"}])
            botones_selector.append([{"text": "🔙 Volver", "callback_data": "menu_principal"}])
            
            mensaje = "📺 Tienes varias pantallas activas. *¿Para cuál pantalla deseas solicitar el código?*:"
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, {"inline_keyboard": botones_selector})
            else:
                enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})
            return

        servicio_seleccionado = safe_get(suscripciones_activas[0], "Servicio", "Disney").lower() if suscripciones_activas else "disney"
        ejecutar_busqueda_otp(chat_id, str_chat_id, servicio_seleccionado, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)

    elif accion.startswith("pedir_otp_"):
        try:
            idx_sub = int(accion.split("_")[-1])
            suscripciones_activas = [s for s in obtener_suscripciones_por_id(chat_id) if safe_get(s, "Estado", "").lower() == "activo"]
            if idx_sub < len(suscripciones_activas):
                servicio_seleccionado = safe_get(suscripciones_activas[idx_sub], "Servicio", "Disney").lower()
            else:
                servicio_seleccionado = "disney"
            ejecutar_busqueda_otp(chat_id, str_chat_id, servicio_seleccionado, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)
        except Exception as e:
            print(f"Error en selector OTP: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error al seleccionar la pantalla. Intenta de nuevo.", get_back_keyboard())

    elif accion == "renovar_suscripcion":
        suscripciones = obtener_suscripciones_por_id(chat_id)
        if not suscripciones:
            procesar_mensaje_bot(chat_id, texto, nombre, username, enviar_mensaje_callback, editar_mensaje_callback, message_id, True, "comprar_extra", None, enviar_foto_callback)
            return

        if len(suscripciones) == 1:
            sub_unica = suscripciones[0]
            row_idx_unico = sub_unica.get("_row_index")
            srv_unico = safe_get(sub_unica, "Servicio", "Disney+").lower()
            iniciar_proceso_pago(chat_id, str_chat_id, nombre, username, "netflix" if "netflix" in srv_unico else "disney", "renovar", row_idx_unico, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)
        else:
            botones_selector = []
            for sub in suscripciones:
                r_idx = sub.get("_row_index")
                srv = safe_get(sub, "Servicio", "Disney+")
                pnt = safe_get(sub, "Pantalla", "Perfil 1")
                cta = safe_get(sub, "Cuenta", "Cuenta")
                botones_selector.append([{"text": f"🔄 {srv} - {pnt} ({cta})", "callback_data": f"renovar_fila_{r_idx}"}])
            
            botones_selector.append([{"text": "🔙 Volver", "callback_data": "menu_principal"}])
            mensaje = "🔄 Tienes múltiples pantallas. *¿Cuál de ellas deseas renovar por 30 días?*:"
            
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, {"inline_keyboard": botones_selector})
            else:
                enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})

    elif accion.startswith("renovar_fila_"):
        try:
            row_idx_elegido = int(accion.split("_")[-1])
            sheet = conectar_sheets()
            registros = sheet.get_all_records()
            fila_obj = registros[row_idx_elegido - 2] if (row_idx_elegido - 2) < len(registros) else {}
            srv_fila = safe_get(fila_obj, "Servicio", "Disney+").lower()
            
            iniciar_proceso_pago(chat_id, str_chat_id, nombre, username, "netflix" if "netflix" in srv_fila else "disney", "renovar", row_idx_elegido, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)
        except Exception as e:
            print(f"Error procesando renovación de fila específica: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error al seleccionar la pantalla. Intenta de nuevo.", get_back_keyboard())

    elif accion == "comprar_extra":
        mensaje = (
            "🛒 *SELECCIONA EL SERVICIO A COMPRAR*\n\n"
            "¿Qué plataforma deseas comprar como nueva pantalla?\n\n"
            f"• *Disney+:* `${PRECIO_DISNEY_USD:.2f} USDT`\n"
            f"• *Netflix:* `${PRECIO_NETFLIX_USD:.2f} USDT`"
        )
        teclado_servicios = {
            "inline_keyboard": [
                [{"text": f"📺 Disney+ (${PRECIO_DISNEY_USD:.2f})", "callback_data": "pagar_servicio_disney_nueva"}],
                [{"text": f"📺 Netflix (${PRECIO_NETFLIX_USD:.2f})", "callback_data": "pagar_servicio_netflix_nueva"}],
                [{"text": "🔙 Volver", "callback_data": "menu_principal"}]
            ]
        }
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_servicios)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_servicios)

    elif accion.startswith("pagar_servicio_"):
        es_netflix = "netflix" in accion
        servicio_elegido = "Netflix" if es_netflix else "Disney+"
        
        nueva_fila_idx = crear_nueva_fila_pendiente(str_chat_id, nombre, username, servicio_elegido)
        iniciar_proceso_pago(chat_id, str_chat_id, nombre, username, "netflix" if es_netflix else "disney", "nueva", nueva_fila_idx, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)

    elif accion == "soporte" or "pago" in accion:
        texto_wa = f"Hola, necesito soporte con mi servicio de Streaming. Mi ID es: {str_chat_id}."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        teclado_whatsapp = {
            "inline_keyboard": [
                [{"text": "💬 Abrir WhatsApp", "url": url_whatsapp}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = "💬 *ATENCIÓN AL CLIENTE*\n\nComunícate directamente con nosotros por WhatsApp:"
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_whatsapp)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_whatsapp)

    else:
        mensaje = "¡Hola! Selecciona una opción del menú de abajo:"
        teclado = get_main_menu_keyboard()
        enviar_mensaje_callback(chat_id, mensaje, teclado)


def notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, row_idx_target, detalle_operacion, enviar_cb, editar_cb=None, message_id=None, es_cb=False):
    """Actualiza la fila en Google Sheets como Pendiente y notifica al Admin el pago en efectivo."""
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        fila_obj = registros[row_idx_target - 2] if (row_idx_target - 2) < len(registros) else {}
        servicio_elegido = safe_get(fila_obj, "Servicio", "Disney+")
        perfil_asignado = safe_get(fila_obj, "Pantalla", "Perfil 1")
        cuenta_asignada = safe_get(fila_obj, "Cuenta", "Por Asignar")
        precio_usd = PRECIO_NETFLIX_USD if "netflix" in str(servicio_elegido).lower() else PRECIO_DISNEY_USD

        sheet.update_cell(row_idx_target, 6, "Pendiente Pago")

        mensaje_cliente = (
            "💵 *PAGO EN EFECTIVO REGISTRADO*\n\n"
            f"• *Operación:* {detalle_operacion}\n"
            f"• *Servicio:* {servicio_elegido} ({perfil_asignado})\n"
            f"• *Monto a cancelar:* `${precio_usd:.2f} USD`\n\n"
            "👤 Entrega el efectivo al encargado del local para que proceda a verificar y activar tu cuenta."
        )
        if es_cb and editar_cb:
            editar_cb(chat_id, message_id, mensaje_cliente, get_back_keyboard())
        else:
            enviar_cb(chat_id, mensaje_cliente, get_back_keyboard())

        if ADMIN_ID:
            texto_admin = (
                "🔔 *¡NUEVO PAGO EN EFECTIVO REPORTADO!* 🔔\n\n"
                f"• *Cliente:* {nombre} (@{username})\n"
                f"• *Telegram ID:* `{str_chat_id}`\n"
                f"• *Tipo:* {detalle_operacion}\n"
                f"• *Servicio:* {servicio_elegido} ({perfil_asignado})\n"
                f"• *Cuenta:* {cuenta_asignada}\n"
                f"• *Monto esperado:* `${precio_usd:.2f} USD`"
            )
            teclado_admin = {
                "inline_keyboard": [
                    [{"text": "✅ Aprobar Efectivo (+30 días)", "callback_data": f"aprobar_{row_idx_target}_efectivo"}],
                    [{"text": "❌ Rechazar", "callback_data": f"rechazar_{row_idx_target}"}]
                ]
            }
            enviar_cb(int(ADMIN_ID), texto_admin, teclado_admin)
    except Exception as e:
        print(f"Error procesando notificación de efectivo: {e}")
        enviar_cb(chat_id, "⚠️ Ocurrió un error al registrar el pago en efectivo.", get_back_keyboard())


def iniciar_proceso_pago(chat_id, str_chat_id, nombre, username, servicio_clave, tipo_operacion, row_idx_target, message_id, enviar_cb, editar_cb, es_cb):
    """Muestra los datos de pago móvil y tasa USDT configurando exactamente la fila objetivo."""
    esperando_captura_pago.add(str_chat_id)
    
    es_netflix = (servicio_clave == "netflix")
    servicio_elegido = "Netflix" if es_netflix else "Disney+"
    precio_usd = PRECIO_NETFLIX_USD if es_netflix else PRECIO_DISNEY_USD

    try:
        sheet = conectar_sheets()
        sheet.update_cell(row_idx_target, 6, "Pendiente Pago")
        sheet.update_cell(row_idx_target, 7, servicio_elegido)
    except Exception as e:
        print(f"Error actualizando celda de pago: {e}")

    tasa_usdt = obtener_tasa_usdt_hoy()
    monto_bs = round(precio_usd * tasa_usdt, 2)

    texto_wa = f"Hola, acabo de realizar el pago móvil de {monto_bs} Bs ({precio_usd} USDT) para {servicio_elegido}. Mi ID es: {str_chat_id}."
    url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
    
    mensaje = (
        f"💳 *DATOS DE PAGO — {servicio_elegido.upper()}*\n\n"
        f"💵 *Monto:* `{precio_usd:.2f} USDT`\n"
        f"📈 *Tasa del día:* `{tasa_usdt} Bs`\n"
        f"💰 *Total a transferir:* `{monto_bs} Bs`\n\n"
        f"📲 *Datos de Pago Móvil (Toca para copiar):*\n"
        f"• *Banco:* {PAGO_MOVIL_BANCO}\n"
        f"• *Cédula:* `{PAGO_MOVIL_CEDULA}`\n"
        f"• *Teléfono:* `{PAGO_MOVIL_TELEFONO}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📸 *PASO FINAL:* Realiza el pago y **envía la captura de pantalla (o el número de referencia)** directamente por este chat para activar tus 30 días."
    )
    teclado_renovar = {
        "inline_keyboard": [
            [{"text": "💬 Enviar comprobante por WhatsApp", "url": url_whatsapp}],
            [{"text": "🔙 Cancelar y Volver", "callback_data": "menu_principal"}]
        ]
    }
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, mensaje, teclado_renovar)
    else:
        enviar_cb(chat_id, mensaje, teclado_renovar)


def quitar_botones_telegram(chat_id, message_id):
    token = os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/editMessageReplyMarkup"
    try:
        requests.post(url, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": {"inline_keyboard": []}
        }, timeout=3)
    except Exception as e:
        print(f"No se pudieron quitar los botones: {e}")


def ejecutar_busqueda_otp(chat_id, str_chat_id, servicio, message_id, enviar_cb, editar_cb, es_cb):
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
            if es_cb and editar_cb:
                editar_cb(chat_id, message_id, mensaje, teclado)
            else:
                enviar_cb(chat_id, mensaje, teclado)
            return

    datos_usuario["intentos"] += 1
    datos_usuario["ultimo_tiempo"] = ahora

    es_netflix = "netflix" in servicio
    nombre_plataforma = "Netflix" if es_netflix else "Disney+"

    msg_espera = f"🔍 Buscando código reciente en el correo de *{nombre_plataforma}*, un momento..."
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, msg_espera, get_back_keyboard())
    else:
        enviar_cb(msg_espera)

    codigo = obtener_ultimo_codigo_netflix() if es_netflix else obtener_ultimo_codigo_disney()

    if codigo:
        mensaje = f"🔑 *Tu código de acceso de {nombre_plataforma} es:*\n\n`{codigo}`\n\n_(Cópialo e ingrésalo en tu pantalla)_"
    else:
        mensaje = f"⚠️ No se encontraron códigos recientes de *{nombre_plataforma}*. Asegúrate de haberlo solicitado en tu TV hace unos segundos e intenta de nuevo."

    teclado = get_back_keyboard()
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, mensaje, teclado)
    else:
        enviar_cb(chat_id, mensaje, teclado)


def procesar_texto_reporte(chat_id, texto, nombre, username, enviar_cb, str_chat_id, suscripciones_asociadas, enviar_foto_callback):
    cuenta_asociada = "Por Asignar"
    servicio_asociado = "Disney+"
    row_idx_pendiente = None
    
    if suscripciones_asociadas:
        for s in suscripciones_asociadas:
            if "pendiente" in safe_get(s, "Estado", "").lower():
                cuenta_asociada = safe_get(s, "Cuenta", "Por Asignar")
                servicio_asociado = safe_get(s, "Servicio", "Disney+")
                row_idx_pendiente = s.get("_row_index")
                break
        else:
            cuenta_asociada = safe_get(suscripciones_asociadas[0], "Cuenta", "Por Asignar")
            servicio_asociado = safe_get(suscripciones_asociadas[0], "Servicio", "Disney+")
            row_idx_pendiente = suscripciones_asociadas[0].get("_row_index")

    if not row_idx_pendiente:
        row_idx_pendiente = obtener_o_crear_fila_pendiente(str_chat_id, nombre, cuenta_asociada, servicio_asociado, username)

    if ADMIN_ID:
        texto_admin = (
            "🔔 *¡NUEVO REPORTE DE PAGO (TEXTO/REFERENCIA)!* 🔔\n\n"
            f"• *Cliente:* {nombre} (@{username})\n"
            f"• *Telegram ID:* `{str_chat_id}`\n"
            f"• *Servicio:* {servicio_asociado}\n"
            f"• *Cuenta:* {cuenta_asociada}\n"
            f"• *Referencia/Detalle:* `{texto}`"
        )
        
        teclado_admin = {
            "inline_keyboard": [
                [{"text": "✅ Aprobar y Activar (+30 días)", "callback_data": f"aprobar_{row_idx_pendiente}_digital"}],
                [{"text": "❌ Rechazar", "callback_data": f"rechazar_{row_idx_pendiente}"}]
            ]
        }
        enviar_cb(int(ADMIN_ID), texto_admin, teclado_admin)

    enviar_cb(chat_id, "✅ Reporte enviado con éxito al administrador. En breve verificaremos tu referencia.", get_main_menu_keyboard())


# ==========================================
# FUNCIONES AUXILIARES DE GOOGLE SHEETS
# ==========================================
def obtener_siguiente_perfil_sucesivo(sheet, servicio="Disney"):
    """Calcula el siguiente perfil correlativo contando exclusivamente las filas de esa misma plataforma."""
    try:
        registros = sheet.get_all_records()
        count = 0
        for r in registros:
            srv = safe_get(r, "Servicio", "")
            if servicio.lower() in srv.lower():
                count += 1
        return f"Perfil {count + 1}"
    except Exception:
        return "Perfil 1"

def obtener_suscripciones_por_id(chat_id):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        str_chat_id = str(chat_id).strip()
        resultados = []
        for idx, r in enumerate(registros, start=2):
            tid = safe_get(r, "Telegram_ID", "")
            if tid == str_chat_id:
                r["_row_index"] = idx
                resultados.append(r)
        return resultados
    except Exception as e:
        print(f"Error: {e}")
        return []

def crear_nueva_fila_pendiente(str_chat_id, nombre, username="", servicio="Disney"):
    try:
        sheet = conectar_sheets()
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        perfil_asignado = obtener_siguiente_perfil_sucesivo(sheet, servicio)
        sheet.append_row([str(str_chat_id), nombre_completo, "Por Asignar", perfil_asignado, "", "Pendiente Pago", servicio])
        return len(sheet.get_all_records()) + 1
    except Exception as e:
        print(f"Error creando fila nueva: {e}")
        return 2

def obtener_o_crear_fila_pendiente(str_chat_id, nombre, cuenta, servicio="Disney", username=""):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        for idx, row in enumerate(registros, start=2):
            tid = safe_get(row, "Telegram_ID", "")
            if tid == str_chat_id:
                srv_fila = safe_get(row, "Servicio", "").lower()
                est_fila = safe_get(row, "Estado", "").lower()
                if srv_fila == servicio.lower() or "pendiente" in est_fila:
                    sheet.update_cell(idx, 6, "Pendiente Pago")
                    sheet.update_cell(idx, 7, servicio)
                    return idx
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        perfil_asignado = obtener_siguiente_perfil_sucesivo(sheet, servicio)
        sheet.append_row([str(str_chat_id), nombre_completo, cuenta, perfil_asignado, "", "Pendiente Pago", servicio])
        return len(sheet.get_all_records()) + 1
    except Exception as e:
        print(f"Error en fila pendiente: {e}")
        return 2

def verificar_cliente_activo(chat_id):
    for sub in obtener_suscripciones_por_id(chat_id):
        estado = safe_get(sub, "Estado", "").lower()
        cuenta = safe_get(sub, "Cuenta", "").lower()
        if estado == "activo" and cuenta not in ("", "por asignar"):
            return True
    return False

def obtener_clientes_pendientes():
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        pendientes = []
        for idx, row in enumerate(registros, start=2):
            estado = safe_get(row, "Estado", "").lower()
            if "pendiente" in estado:
                pendientes.append((len(pendientes)+1, idx, row))
        return pendientes
    except Exception as e:
        print(f"Error obteniendo pendientes: {e}")
        return []

def aprobar_suscripcion_sheet(row_idx):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        fila_actual = registros[row_idx - 2] if (row_idx - 2) < len(registros) else {}
        tid_cliente = safe_get(fila_actual, "Telegram_ID", "")
        nombre_cliente = safe_get(fila_actual, "Nombre", "Cliente")
        servicio_fila = safe_get(fila_actual, "Servicio", "Disney+")
        perfil_asignado = safe_get(fila_actual, "Pantalla", "Perfil 1")
        vencimiento_actual_str = safe_get(fila_actual, "Vencimiento", "")
        estado_actual = safe_get(fila_actual, "Estado", "").lower()

        if estado_actual == "activo":
            return True, tid_cliente, True, nombre_cliente, servicio_fila, perfil_asignado, "Renovación"

        tipo_operacion = "Renovación" if vencimiento_actual_str and vencimiento_actual_str.lower() not in ("", "sin fecha") else "Pantalla Nueva"

        fecha_base = datetime.date.today()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                if vencimiento_actual_str:
                    fecha_venc_actual = datetime.datetime.strptime(vencimiento_actual_str, fmt).date()
                    if fecha_venc_actual >= datetime.date.today():
                        fecha_base = fecha_venc_actual
                break
            except ValueError:
                continue

        nueva_fecha = (fecha_base + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        
        sheet.update_cell(row_idx, 5, nueva_fecha)
        sheet.update_cell(row_idx, 6, "Activo")
        
        return True, tid_cliente, False, nombre_cliente, servicio_fila, perfil_asignado, tipo_operacion
    except Exception as e:
        print(f"Error aprobando suscripción: {e}")
        return False, None, False, "", "Disney+", "Perfil 1", "Renovación"

def registrar_venta_en_historial(nombre_cliente, tid_cliente, servicio, perfil, monto_usd, tipo_operacion, metodo_pago):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        encabezados_esperados = ["Fecha y Hora", "Cliente", "Telegram ID", "Servicio", "Perfil Asignado", "Monto USD", "Tipo", "Método Pago"]
        try:
            sheet_ventas = spreadsheet.worksheet("Ventas")
            fila_1 = sheet_ventas.row_values(1)
            if len(fila_1) < 8:
                sheet_ventas.update("A1:H1", [encabezados_esperados])
        except Exception:
            sheet_ventas = spreadsheet.add_worksheet(title="Ventas", rows="1000", cols="8")
            sheet_ventas.append_row(encabezados_esperados)

        fecha_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet_ventas.append_row([
            fecha_hora,
            str(nombre_cliente),
            str(tid_cliente),
            str(servicio),
            str(perfil),
            f"${float(monto_usd):.2f}",
            str(tipo_operacion),
            str(metodo_pago)
        ])
    except Exception as e:
        print(f"Error al registrar la venta en el historial: {e}")

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
        activos = sum(1 for r in registros if safe_get(r, "Estado", "").lower() == "activo")
        pendientes = sum(1 for r in registros if "pendiente" in safe_get(r, "Estado", "").lower())
        unicos = len(set(safe_get(r, "Telegram_ID", "") for r in registros if safe_get(r, "Telegram_ID", "")))
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
            [{"text": "📲 Ver mis datos / pantallas", "callback_data": "ver_datos"}],
            [{"text": "🔑 Solicitar Código", "callback_data": "obtener_codigo"}],
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
