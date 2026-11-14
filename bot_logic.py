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

# Control de estados temporales de los usuarios y administrador
esperando_captura_pago = {}
esperando_nuevo_nombre_perfil = {}
esperando_busqueda_admin = {}
esperando_nueva_cuenta_correo = {}


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
    """Cerebro industrial con alerta de comportamiento anormal de códigos OTP para el administrador."""
    
    str_chat_id = str(chat_id).strip()
    accion = callback_data if es_callback else texto.lower().strip()

    # -------------------------------------------------------------
    # ASISTENTE ADMIN: CARGAR NUEVA CUENTA MAESTRO (CORREO Y CLAVE)
    # -------------------------------------------------------------
    if not es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and str_chat_id in esperando_nueva_cuenta_correo and texto:
        servicio_cuenta = esperando_nueva_cuenta_correo.pop(str_chat_id)
        datos_cuenta = texto.strip()

        try:
            sheet_principal = conectar_sheets()
            spreadsheet = sheet_principal.spreadsheet
            
            try:
                sheet_cuentas = spreadsheet.worksheet("Cuentas")
            except Exception:
                sheet_cuentas = spreadsheet.add_worksheet(title="Cuentas", rows="1000", cols="6")
                sheet_cuentas.append_row(["Servicio", "Correo", "Contraseña", "Capacidad Total", "Perfiles Ocupados", "Estado"])

            capacidad_defecto = 5 if "netflix" in servicio_cuenta.lower() else 7
            
            sheet_cuentas.append_row([
                servicio_cuenta,
                datos_cuenta,
                "",
                str(capacidad_defecto),
                "0",
                "Activa"
            ])

            enviar_mensaje_callback(
                chat_id,
                f"✅ *¡CUENTA MAESTRA CARGADA CON ÉXITO!*\n\n"
                f"• *Servicio:* {servicio_cuenta}\n"
                f"• *Detalle:* `{datos_cuenta}`\n"
                f"• *Capacidad:* {capacidad_defecto} perfiles\n"
                f"• *Estado:* Activa (0 ocupados)\n\n"
                "La cuenta ya está disponible para recibir clientes o asignar stock pendiente.",
                {
                    "inline_keyboard": [
                        [{"text": "📦 Asignar Stock Pendiente Ahora", "callback_data": "admin_asignar_stock"}],
                        [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                    ]
                }
            )
        except Exception as e:
            print(f"Error cargando cuenta maestro: {e}")
            enviar_mensaje_callback(chat_id, f"❌ Ocurrió un error al guardar la cuenta en Google Sheets: {e}", {
                "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
            })
        return

    # -------------------------------------------------------------
    # BÚSQUEDA DE CLIENTE POR PARTE DEL ADMINISTRADOR
    # -------------------------------------------------------------
    if not es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and str_chat_id in esperando_busqueda_admin and texto:
        esperando_busqueda_admin.pop(str_chat_id)
        termino_busqueda = texto.strip().lower()
        
        activos = obtener_clientes_activos_general()
        encontrados = []
        
        for idx, row_idx, act in activos:
            nom_a = safe_get(act, "Nombre", "").lower()
            tid_a = safe_get(act, "Telegram_ID", "").lower()
            cta_a = safe_get(act, "Cuenta", "").lower()
            srv_a = safe_get(act, "Servicio", "").lower()
            
            if (termino_busqueda in nom_a or 
                termino_busqueda in tid_a or 
                termino_busqueda in cta_a or 
                termino_busqueda in srv_a):
                encontrados.append((row_idx, act))

        if not encontrados:
            enviar_mensaje_callback(
                chat_id, 
                f"❌ No se encontró ningún cliente activo que coincida con: *{texto}*.", 
                {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]}
            )
            return

        enviar_mensaje_callback(chat_id, f"🔍 *Resultados de la búsqueda para:* `{texto}` ({len(encontrados)} encontrados)")
        
        for row_idx, act in encontrados:
            srv_a = safe_get(act, "Servicio", "Disney+")
            pnt_a = safe_get(act, "Pantalla", "Perfil 1")
            cta_a = safe_get(act, "Cuenta", "Cuenta")
            nom_a = safe_get(act, "Nombre", "Cliente")
            tid_a = safe_get(act, "Telegram_ID", "")
            fec_a = safe_get(act, "Vencimiento", "N/A")
            
            txt = (
                f"🟢 *Fila {row_idx}*\n"
                f"• *Cliente:* {nom_a}\n"
                f"• *Telegram ID:* `{tid_a}`\n"
                f"• *Servicio:* {srv_a} ({pnt_a})\n"
                f"• *Correo:* `{cta_a}`\n"
                f"• *Vence el:* `{fec_a}`"
            )
            teclado_expulsar = {
                "inline_keyboard": [
                    [{"text": "🚨 Expulsar y Liberar Cupo", "callback_data": f"admin_expulsar_{row_idx}"}]
                ]
            }
            enviar_mensaje_callback(chat_id, txt, teclado_expulsar)
            
        enviar_mensaje_callback(chat_id, "Gestión de resultados finalizada.", {
            "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
        })
        return

    # -------------------------------------------------------------
    # CAPTURA DE TEXTO: NUEVO NOMBRE DE PERFIL PERSONALIZADO
    # -------------------------------------------------------------
    if not es_callback and str_chat_id in esperando_nuevo_nombre_perfil and texto:
        row_idx_perfil = esperando_nuevo_nombre_perfil.pop(str_chat_id)
        nuevo_nombre = texto.strip()

        if len(nuevo_nombre) > 20:
            enviar_mensaje_callback(chat_id, "⚠️ El nombre es demasiado largo (máximo 20 caracteres). Por favor escribe uno más corto:", get_back_keyboard())
            esperando_nuevo_nombre_perfil[str_chat_id] = row_idx_perfil
            return

        try:
            sheet = conectar_sheets()
            registros = sheet.get_all_records()
            fila_obj = registros[row_idx_perfil - 2] if (row_idx_perfil - 2) < len(registros) else {}
            
            servicio_perfil = safe_get(fila_obj, "Servicio", "Streaming")
            cuenta_perfil = safe_get(fila_obj, "Cuenta", "Correo")
            perfil_actual_texto = safe_get(fila_obj, "Pantalla", "Perfil 1")
            
            numero_base = "Perfil 1"
            for n in range(1, 8):
                if f"perfil {n}" in perfil_actual_texto.lower():
                    numero_base = f"Perfil {n}"
                    break

            nuevo_valor_celda = f"{numero_base} ({nuevo_nombre})"
            sheet.update_cell(row_idx_perfil, 4, nuevo_valor_celda)

            if ADMIN_ID:
                texto_admin = (
                    "✏️ *¡SOLICITUD DE CAMBIO DE NOMBRE DE PERFIL!* ✏️\n\n"
                    f"• *Cliente:* {nombre} (@{username})\n"
                    f"• *Telegram ID:* `{str_chat_id}`\n"
                    f"• *Servicio:* {servicio_perfil}\n"
                    f"• *Correo/Cuenta:* `{cuenta_perfil}`\n"
                    f"• *Perfil base:* {numero_base}\n"
                    f"• *Nuevo nombre solicitado:* `{nuevo_nombre}`\n\n"
                    "💡 *Acción:* Entra a la plataforma y cambia el nombre de este perfil para que coincida."
                )
                enviar_mensaje_callback(int(ADMIN_ID), texto_admin)

            enviar_mensaje_callback(
                chat_id,
                f"✅ *¡Nombre de perfil actualizado con éxito!*\n\n"
                f"Tu perfil ahora aparece como: *{nuevo_valor_celda}*.\n"
                "Hemos notificado al administrador para que aplique el cambio visual en la plataforma.",
                get_main_menu_keyboard()
            )
        except Exception as e:
            print(f"Error actualizando nombre de perfil: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error al actualizar el nombre. Intenta de nuevo.", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # CANCELAR Y VOLVER AL MENÚ
    # -------------------------------------------------------------
    if accion == "menu_principal" or accion == "/start" or accion == "/menu":
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)
        if str_chat_id in esperando_nuevo_nombre_perfil:
            esperando_nuevo_nombre_perfil.pop(str_chat_id)
        if str_chat_id in esperando_busqueda_admin:
            esperando_busqueda_admin.pop(str_chat_id)
        if str_chat_id in esperando_nueva_cuenta_correo:
            esperando_nueva_cuenta_correo.pop(str_chat_id)
            
        texto_menu = (
            "🤖 *Bienvenido al servicio de Streaming*\n\n"
            "Gestiona tus pantallas, códigos de acceso y renovaciones desde los botones de abajo:"
        )
        teclado = get_main_menu_keyboard()
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, texto_menu, teclado)
        else:
            enviar_mensaje_callback(chat_id, texto_menu, teclado)
        return

    # -------------------------------------------------------------
    # CAPTURA DE FOTO / COMPROBANTE ENVIADO POR EL CLIENTE
    # -------------------------------------------------------------
    if photo_file_id and str_chat_id in esperando_captura_pago:
        row_idx_pendiente = esperando_captura_pago.pop(str_chat_id)
        
        try:
            sheet = conectar_sheets()
            registros = sheet.get_all_records()
            fila_obj = registros[row_idx_pendiente - 2] if (row_idx_pendiente - 2) < len(registros) else {}
            cuenta_asociada = safe_get(fila_obj, "Cuenta", "Por Asignar")
            servicio_asociado = safe_get(fila_obj, "Servicio", "Disney+")
            pantalla_asociada = safe_get(fila_obj, "Pantalla", "Perfil 1")
        except Exception:
            cuenta_asociada = "Por Asignar"
            servicio_asociado = "Disney+"
            pantalla_asociada = "Perfil 1"

        if ADMIN_ID and enviar_foto_callback:
            caption_admin = (
                "🔔 *¡NUEVO COMPROBANTE DE PAGO (FOTO)!* 🔔\n\n"
                f"• *Cliente:* {nombre} (@{username})\n"
                f"• *Telegram ID:* `{str_chat_id}`\n"
                f"• *Servicio:* {servicio_asociado} ({pantalla_asociada})\n"
                f"• *Cuenta/Detalle:* {cuenta_asociada}"
            )
            
            teclado_admin = {
                "inline_keyboard": [
                    [{"text": "✅ Aprobar y Activar (+30 días)", "callback_data": f"aprobar_{row_idx_pendiente}_digital"}],
                    [{"text": "❌ Rechazar (Eliminar Fila)", "callback_data": f"rechazar_{row_idx_pendiente}"}]
                ]
            }
            enviar_foto_callback(int(ADMIN_ID), photo_file_id, caption_admin, teclado_admin)

        texto_confirmacion = (
            "✅ *¡Captura de pago recibida con éxito!*\n\n"
            "Se la hemos enviado al administrador. En breve tu pago será verificado y tu cuenta activada."
        )
        
        teclado_cliente = {
            "inline_keyboard": [
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        enviar_mensaje_callback(chat_id, texto_confirmacion, teclado_cliente)
        return

    if not es_callback and str_chat_id in esperando_captura_pago and texto and texto.lower().strip() not in ("efectivo", "/efectivo"):
        row_idx_pendiente = esperando_captura_pago.pop(str_chat_id)
        procesar_texto_reporte(chat_id, texto, nombre, username, enviar_mensaje_callback, str_chat_id, row_idx_pendiente, enviar_foto_callback)
        return

    # -------------------------------------------------------------
    # PAGO EN EFECTIVO
    # -------------------------------------------------------------
    if accion == "efectivo" or accion == "/efectivo":
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

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
            nueva_fila_idx = crear_nueva_fila_pendiente(str_chat_id, nombre, username, servicio_elegido, enviar_mensaje_callback)
            esperando_captura_pago[str_chat_id] = nueva_fila_idx
            notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, nueva_fila_idx, "Pantalla Nueva", enviar_mensaje_callback, editar_mensaje_callback, message_id, es_callback)
        except Exception as e:
            print(f"Error en efectivo nuevo: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # PANEL DE ADMINISTRADOR Y RESUMEN GENERAL DEL NEGOCIO
    # -------------------------------------------------------------
    if accion == "/admin" or accion == "admin_volver":
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)
        if str_chat_id in esperando_busqueda_admin:
            esperando_busqueda_admin.pop(str_chat_id)
        if str_chat_id in esperando_nueva_cuenta_correo:
            esperando_nueva_cuenta_correo.pop(str_chat_id)

        if ADMIN_ID and str_chat_id == ADMIN_ID:
            reporte = generar_reporte_admin()
            teclado = {
                "inline_keyboard": [
                    [{"text": "📊 Resumen General del Negocio", "callback_data": "admin_resumen_negocio"}],
                    [{"text": "📋 Ver Pagos Pendientes", "callback_data": "admin_ver_pendientes"}],
                    [{"text": "➕ Cargar Cuenta Maestro (Stock)", "callback_data": "admin_cargar_cuenta"}],
                    [{"text": "🔍 Buscar y Gestionar Cliente Activo", "callback_data": "admin_pedir_busqueda"}],
                    [{"text": "🗑️ Gestionar / Eliminar Vencidos", "callback_data": "admin_ver_vencidos"}],
                    [{"text": "📦 Asignar Stock Pendiente", "callback_data": "admin_asignar_stock"}],
                    [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
                ]
            }
            if es_callback and editar_mensaje_callback and accion == "admin_volver":
                editar_mensaje_callback(chat_id, message_id, reporte, teclado)
            else:
                enviar_mensaje_callback(chat_id, reporte, teclado)
        else:
            enviar_mensaje_callback(chat_id, "⛔ No tienes permisos para acceder a este panel.", get_main_menu_keyboard())
        return

    elif accion == "admin_resumen_negocio":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            resumen_detallado = generar_resumen_completo_negocio()
            teclado_resumen = {
                "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, resumen_detallado, teclado_resumen)
            else:
                enviar_mensaje_callback(chat_id, resumen_detallado, teclado_resumen)
        return

    elif accion == "admin_cargar_cuenta":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            mensaje_carga = "➕ *CARGAR NUEVA CUENTA MAESTRO*\n\nSelecciona a qué plataforma pertenece la cuenta que deseas agregar:"
            teclado_servicios = {
                "inline_keyboard": [
                    [{"text": "📺 Netflix (Capacidad: 5)", "callback_data": "admin_cuenta_netflix"}],
                    [{"text": "📺 Disney+ (Capacidad: 7)", "callback_data": "admin_cuenta_disney"}],
                    [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                ]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_carga, teclado_servicios)
            else:
                enviar_mensaje_callback(chat_id, mensaje_carga, teclado_servicios)
        return

    elif accion == "admin_cuenta_netflix" or accion == "admin_cuenta_disney":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            servicio_elegido = "Netflix" if "netflix" in accion else "Disney+"
            esperando_nueva_cuenta_correo[str_chat_id] = servicio_elegido

            mensaje_peticion = (
                f"➕ *NUEVA CUENTA DE {servicio_elegido.upper()}*\n\n"
                "Escribe o pega a continuación el correo y la contraseña de la cuenta\n(Ej: `correo@gmail.com : tucontraseña`):"
            )
            teclado_canc = {
                "inline_keyboard": [[{"text": "🔙 Cancelar y Volver", "callback_data": "admin_volver"}]]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_peticion, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, mensaje_peticion, teclado_canc)
        return

    elif accion == "admin_pedir_busqueda":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            esperando_busqueda_admin[str_chat_id] = True
            mensaje_busqueda = (
                "🔍 *BUSCAR CLIENTE ACTIVO*\n\n"
                "Escribe a continuación el **nombre**, **usuario (@)**, **ID de Telegram** o **correo** del cliente que deseas buscar:"
            )
            teclado_canc = {
                "inline_keyboard": [[{"text": "🔙 Cancelar y Volver", "callback_data": "admin_volver"}]]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_busqueda, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, mensaje_busqueda, teclado_canc)
        return

    elif accion == "admin_asignar_stock":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            resultado_asignacion = procesar_asignacion_stock_masivo(enviar_mensaje_callback)
            enviar_mensaje_callback(chat_id, resultado_asignacion, {
                "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
            })
        return

    elif accion == "admin_ver_pendientes":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            pendientes = obtener_clientes_pendientes()
            if not pendientes:
                enviar_mensaje_callback(chat_id, "✅ No hay pagos pendientes en este momento.", {
                    "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                })
            else:
                for idx, row_idx, p in pendientes:
                    srv_p = safe_get(p, "Servicio", "Disney+")
                    pnt_p = safe_get(p, "Pantalla", "Perfil 1")
                    txt = (
                        f"🟡 *Pago Pendiente #{idx}* (Fila {row_idx})\n"
                        f"• *Cliente:* {safe_get(p, 'Nombre')}\n"
                        f"• *Telegram ID:* `{safe_get(p, 'Telegram_ID')}`\n"
                        f"• *Servicio:* {srv_p} ({pnt_p})\n"
                        f"• *Cuenta/Correo:* {safe_get(p, 'Cuenta')}"
                    )
                    teclado_aprobar = {
                        "inline_keyboard": [
                            [{"text": "✅ Aprobar y Activar (+30 días)", "callback_data": f"aprobar_{row_idx}_digital"}],
                            [{"text": "❌ Rechazar (Eliminar Fila)", "callback_data": f"rechazar_{row_idx}"}]
                        ]
                    }
                    enviar_mensaje_callback(chat_id, txt, teclado_aprobar)
        return

    elif accion.startswith("admin_expulsar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx_expulsar = int(accion.split("_")[-1])
                
                sheet_principal = conectar_sheets()
                registros = sheet_principal.get_all_records()
                fila_obj = registros[row_idx_expulsar - 2] if (row_idx_expulsar - 2) < len(registros) else {}
                tid_cliente = safe_get(fila_obj, "Telegram_ID", "")
                srv_exp = safe_get(fila_obj, "Servicio", "Streaming")
                pnt_exp = safe_get(fila_obj, "Pantalla", "Perfil")

                resultado_expulsion = liberar_y_eliminar_fila_suscripcion(row_idx_expulsar)
                
                if message_id:
                    quitar_botones_telegram(chat_id, message_id)

                enviar_mensaje_callback(chat_id, f"🚨 {resultado_expulsion}", {
                    "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                })

                if tid_cliente:
                    try:
                        msg_usuario = (
                            "⚠️ *AVISO DE SUSPENSIÓN*\n\n"
                            f"Tu suscripción a *{srv_exp}* ({pnt_exp}) ha sido finalizada por el administrador.\n"
                            "Si consideras que se trata de un error, comunícate con soporte."
                        )
                        enviar_mensaje_callback(int(tid_cliente), msg_usuario, get_main_menu_keyboard())
                    except Exception:
                        pass
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al expulsar el usuario: {e}", get_back_keyboard())
        return

    elif accion == "admin_ver_vencidos":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            vencidos = obtener_suscripciones_vencidas()
            if not vencidos:
                enviar_mensaje_callback(chat_id, "✅ No hay pantallas vencidas para depurar.", {
                    "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                })
            else:
                for idx, row_idx, v in vencidos:
                    srv_v = safe_get(v, "Servicio", "Disney+")
                    pnt_v = safe_get(v, "Pantalla", "Perfil 1")
                    cta_v = safe_get(v, "Cuenta", "Cuenta")
                    fec_v = safe_get(v, "Vencimiento", "N/A")
                    txt = (
                        f"🔴 *Pantalla Vencida #{idx}* (Fila {row_idx})\n"
                        f"• *Cliente:* {safe_get(v, 'Nombre')}\n"
                        f"• *Servicio:* {srv_v} ({pnt_v})\n"
                        f"• *Correo:* `{cta_v}`\n"
                        f"• *Venció el:* `{fec_v}`"
                    )
                    teclado_borrar = {
                        "inline_keyboard": [
                            [{"text": "🗑️ Liberar Perfil y Borrar Fila", "callback_data": f"admin_liberar_{row_idx}"}],
                            [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                        ]
                    }
                    enviar_mensaje_callback(chat_id, txt, teclado_borrar)
        return

    elif accion.startswith("admin_liberar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx_a_borrar = int(accion.split("_")[-1])
                resultado_liberacion = liberar_y_eliminar_fila_suscripcion(row_idx_a_borrar)
                if message_id:
                    quitar_botones_telegram(chat_id, message_id)
                enviar_mensaje_callback(chat_id, resultado_liberacion, {
                    "inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]
                })
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al liberar la fila: {e}", get_back_keyboard())
        return

    elif accion.startswith("aprobar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                partes_ap = accion.split("_")
                row_idx = int(partes_ap[1])
                es_efectivo = (len(partes_ap) > 2 and partes_ap[2].strip() == "efectivo")
                metodo_pago = "Efectivo" if es_efectivo else "Pago Móvil / Digital"

                exito, tid_cliente, ya_estaba_activa, nombre_cliente, srv_aprobado, perfil_asignado, tipo_operacion, cuenta_fila = aprobar_suscripcion_sheet(row_idx)
                
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
                        f"• *Cliente:* {nombre_cliente}\n"
                        f"• *Servicio:* {srv_aprobado} ({perfil_asignado})\n"
                        f"• *Cuenta:* `{cuenta_fila}`\n"
                        f"• *Tipo:* {tipo_operacion}\n"
                        f"• *Método:* {metodo_pago}",
                        get_back_keyboard()
                    )
                    if tid_cliente:
                        try:
                            if "pendiente de stock" in str(cuenta_fila).lower():
                                msg_cliente = (
                                    "🎉 *¡Tu pago ha sido verificado y aprobado!*\n\n"
                                    f"Tu suscripción de *{srv_aprobado}* ({perfil_asignado}) está **Activa** con **prioridad #1**.\n"
                                    "⏳ Estamos preparando tu cuenta; te notificaremos en cuanto tu correo quede asignado."
                                )
                            else:
                                msg_cliente = (
                                    "🎉 *¡Tu pago ha sido verificado y aprobado!*\n\n"
                                    f"Tu servicio de *{srv_aprobado}* ({perfil_asignado}) ya se encuentra *Activo* por 30 días más. ¡Disfruta tu contenido!"
                                )
                            enviar_mensaje_callback(int(tid_cliente), msg_cliente, get_main_menu_keyboard())
                        except Exception:
                            pass
                else:
                    enviar_mensaje_callback(chat_id, f"❌ Error al actualizar la hoja de cálculo.", get_back_keyboard())
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    elif accion.startswith("rechazar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx = int(accion.split("_")[1])
                
                sheet_principal = conectar_sheets()
                registros = sheet_principal.get_all_records()
                fila_obj = registros[row_idx - 2] if (row_idx - 2) < len(registros) else {}
                tid_cliente = safe_get(fila_obj, "Telegram_ID", "")
                srv_rechazado = safe_get(fila_obj, "Servicio", "Streaming")

                limpiar_fila_cancelada(row_idx)

                if message_id:
                    quitar_botones_telegram(chat_id, message_id)

                enviar_mensaje_callback(chat_id, f"❌ Pago de la fila {row_idx} rechazado. Fila eliminada y cupo liberado con éxito.", get_back_keyboard())

                if tid_cliente:
                    try:
                        msg_rechazo = (
                            "⚠️ *COMPROBANTE RECHAZADO*\n\n"
                            f"Tu comprobante de pago para *{srv_rechazado}* no pudo ser verificado (puede ser ilegible, incorrecto o duplicado).\n\n"
                            "Por favor, verifica los datos e intenta realizar la compra o reporte nuevamente desde el menú."
                        )
                        enviar_mensaje_callback(int(tid_cliente), msg_rechazo, get_main_menu_keyboard())
                    except Exception:
                        pass
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error al rechazar: {e}", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # MENÚ PRINCIPAL Y CLIENTE
    # -------------------------------------------------------------
    elif accion == "ver_datos" or "cuenta" in accion:
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

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
                correo_raw = safe_get(sub, "Cuenta", "Por Asignar")
                pantalla = safe_get(sub, "Pantalla", "Perfil 1")
                vencimiento = safe_get(sub, "Vencimiento", "Sin fecha")
                estado = safe_get(sub, "Estado", "Pendiente Pago")
                
                if "pendiente de stock" in correo_raw.lower():
                    correo_mostrar = "⏳ En asignación prioritaria (Stock en curso)"
                else:
                    correo_mostrar = f"`{correo_raw}`"

                alerta_vencimiento = verificar_alerta_vencimiento(vencimiento, estado)
                if "Vencida" in alerta_vencimiento or "Vence" in alerta_vencimiento or estado.lower() != "activo":
                    tiene_por_renovar = True

                bloques.append(
                    f"🔹 *Suscripción #{idx} ({servicio})*\n"
                    f"• *Correo:* {correo_mostrar}\n"
                    f"• *Perfil:* {pantalla}\n"
                    f"• *Vencimiento:* {vencimiento} {alerta_vencimiento}\n"
                    f"• *Estado:* {estado}"
                )

            mensaje = encabezado + "\n\n".join(bloques)
            teclado = get_datos_keyboard(mostrar_renovar=tiene_por_renovar, suscripciones=suscripciones)
            
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado)

    elif accion == "menu_renombrar":
        suscripciones_activas = [
            s for s in obtener_suscripciones_por_id(chat_id)
            if safe_get(s, "Estado", "").lower() == "activo"
            and "pendiente" not in safe_get(s, "Cuenta", "").lower()
        ]

        if not suscripciones_activas:
            enviar_mensaje_callback(chat_id, "⚠️ No tienes pantallas activas disponibles para renombrar.", get_back_keyboard())
            return

        botones_selector = []
        for sub in suscripciones_activas:
            r_idx = sub.get("_row_index")
            srv = safe_get(sub, "Servicio", "Disney+")
            pnt = safe_get(sub, "Pantalla", "Perfil 1")
            cta = safe_get(sub, "Cuenta", "Cuenta")
            botones_selector.append([{"text": f"✏️ {srv} - {pnt} ({cta})", "callback_data": f"renombrar_perfil_{r_idx}"}])

        botones_selector.append([{"text": "🔙 Volver", "callback_data": "ver_datos"}])
        mensaje = "✏️ *PERSONALIZAR NOMBRE DE PERFIL*\n\nSelecciona la pantalla a la que deseas cambiarle el nombre:"
        
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, {"inline_keyboard": botones_selector})
        else:
            enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})
        return

    elif accion.startswith("renombrar_perfil_"):
        try:
            row_idx_renombrar = int(accion.split("_")[-1])
            esperando_nuevo_nombre_perfil[str_chat_id] = row_idx_renombrar

            mensaje_peticion = (
                "✏️ *ESCRIBE TU NUEVO NOMBRE*\n\n"
                "Escribe a continuación el nombre que deseas asignarle a tu perfil (Ej: *Papá*, *Sofía*, *Cine*).\n\n"
                "⚠️ *Nota:* Solo puedes cambiar el nombre de tu perfil una vez por ciclo de suscripción."
            )
            teclado_canc = {
                "inline_keyboard": [[{"text": "🔙 Cancelar y Volver", "callback_data": "menu_renombrar"}]]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_peticion, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, mensaje_peticion, teclado_canc)
        except Exception as e:
            print(f"Error iniciando renombrado: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error. Intenta de nuevo.", get_back_keyboard())
        return

    elif accion == "obtener_codigo" or "codigo" in accion:
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

        if not verificar_cliente_activo(chat_id):
            # Registrar intento sospechoso o no autorizado de pedir código sin estar activo
            registrar_intento_sospechoso_otp(chat_id, nombre, username, enviar_mensaje_callback)

            mensaje = "🔒 *ACCESO RESTRINGIDO*\n\nPara solicitar códigos, debes tener al menos una pantalla en estado *Activo* y con correo asignado."
            teclado = get_datos_keyboard(mostrar_renovar=True)
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
            else:
                enviar_mensaje_callback(chat_id, mensaje, teclado)
            return

        suscripciones_activas = [
            s for s in obtener_suscripciones_por_id(chat_id)
            if safe_get(s, "Estado", "").lower() == "activo"
            and "pendiente" not in safe_get(s, "Cuenta", "").lower()
            and safe_get(s, "Cuenta", "").lower() not in ("", "por asignar")
        ]

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
            suscripciones_activas = [
                s for s in obtener_suscripciones_por_id(chat_id)
                if safe_get(s, "Estado", "").lower() == "activo"
                and "pendiente" not in safe_get(s, "Cuenta", "").lower()
            ]
            if idx_sub < len(suscripciones_activas):
                servicio_seleccionado = safe_get(suscripciones_activas[idx_sub], "Servicio", "Disney").lower()
            else:
                servicio_seleccionado = "disney"
            ejecutar_busqueda_otp(chat_id, str_chat_id, servicio_seleccionado, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)
        except Exception as e:
            print(f"Error en selector OTP: {e}")
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error al seleccionar la pantalla. Intenta de nuevo.", get_back_keyboard())

    elif accion == "renovar_suscripcion":
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

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
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

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
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

        es_netflix = "netflix" in accion
        servicio_elegido = "Netflix" if es_netflix else "Disney+"
        
        nueva_fila_idx = crear_nueva_fila_pendiente(str_chat_id, nombre, username, servicio_elegido, enviar_mensaje_callback)
        iniciar_proceso_pago(chat_id, str_chat_id, nombre, username, "netflix" if es_netflix else "disney", "nueva", nueva_fila_idx, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)

    elif accion == "soporte" or "pago" in accion:
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

        texto_wa = f"Hola, necesito soporte con mi servicio de Streaming. Mi ID es: {str_chat_id}."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        teclado_whatsapp = {
            "inline_keyboard": [
                [{"text": "💬 Soporte Técnico en WhatsApp", "url": url_whatsapp}],
                [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = "💬 *ATENCIÓN AL CLIENTE*\n\nSi tienes dudas o requieres soporte técnico, comunícate con nosotros por WhatsApp:"
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_whatsapp)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_whatsapp)

    else:
        mensaje = "¡Hola! Selecciona una opción del menú de abajo:"
        teclado = get_main_menu_keyboard()
        enviar_mensaje_callback(chat_id, mensaje, teclado)


def registrar_intento_sospechoso_otp(chat_id, nombre, username, enviar_mensaje_cb):
    """Monitorea y alerta al administrador si un usuario intenta solicitar códigos de forma anormal sin estar activo."""
    str_chat_id = str(chat_id).strip()
    ahora = time.time()
    
    if "intentos_anormales" not in control_intentos_otp:
        control_intentos_otp["intentos_anormales"] = {}
        
    if str_chat_id not in control_intentos_otp["intentos_anormales"]:
        control_intentos_otp["intentos_anormales"][str_chat_id] = {"contador": 0, "primer_intento": ahora}
        
    registro = control_intentos_otp["intentos_anormales"][str_chat_id]
    
    # Reiniciar contador si pasa más de 1 hora
    if ahora - registro["primer_intento"] > 3600:
        registro["contador"] = 0
        registro["primer_intento"] = ahora
        
    registro["contador"] += 1
    
    # Si acumula 3 o más intentos sospechosos, alertamos al administrador
    if registro["contador"] >= 3 and ADMIN_ID and enviar_mensaje_cb:
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        alerta_anomalia = (
            "🚨 *¡ALERTA DE COMPORTAMIENTO SOSPECHOSO!* 🚨\n\n"
            f"• *Usuario:* {nombre_completo}\n"
            f"• *Telegram ID:* `{str_chat_id}`\n"
            f"• *Incidente:* Ha intentado solicitar códigos de acceso múltiples veces sin tener una suscripción activa o con cuenta vencida.\n\n"
            "💡 Es posible que este usuario esté intentando acceder sin pagar o buscando filtrar accesos. Puedes buscar su ID en `/admin` para verificarlo."
        )
        try:
            enviar_mensaje_cb(int(ADMIN_ID), alerta_anomalia)
            # Reseteamos temporalmente para no saturar con spam al admin
            registro["contador"] = 0
        except Exception as e:
            print(f"Error enviando alerta de anomalía al admin: {e}")


def limpiar_fila_cancelada(row_idx):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        
        try:
            fila_datos = sheet_principal.row_values(row_idx)
        except Exception:
            return

        if len(fila_datos) < 3:
            return

        estado_actual = safe_get({"Estado": fila_datos[5] if len(fila_datos) > 5 else ""}, "Estado", "").lower()
        
        if "pendiente" in estado_actual or estado_actual == "":
            correo_a_liberar = safe_get({"Cuenta": fila_datos[2]}, "Cuenta", "")
            
            if correo_a_liberar and "pendiente de stock" not in correo_a_liberar.lower():
                try:
                    sheet_cuentas = spreadsheet.worksheet("Cuentas")
                    registros_cuentas = sheet_cuentas.get_all_records()
                    for idx_c, c_row in enumerate(registros_cuentas, start=2):
                        correo_cta = safe_get(c_row, "Correo (Usuario)", safe_get(c_row, "Correo", ""))
                        if correo_cta.lower() == correo_a_liberar.lower():
                            ocupados = int(safe_get(c_row, "Perfiles Ocupados", "1"))
                            nuevos_ocupados = max(0, ocupados - 1)
                            sheet_cuentas.update_cell(idx_c, 5, nuevos_ocupados)
                            
                            if safe_get(c_row, "Estado", "").lower() == "llena":
                                sheet_cuentas.update_cell(idx_c, 6, "Activa")
                            break
                except Exception as e:
                    print(f"Aviso al liberar stock en cancelación/rechazo: {e}")

            sheet_principal.delete_rows(row_idx)
            print(f"Fila {row_idx} eliminada por cancelación o rechazo.")
    except Exception as e:
        print(f"Error limpiando fila: {e}")


def notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, row_idx_target, detalle_operacion, enviar_cb, editar_cb=None, message_id=None, es_cb=False):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        fila_obj = registros[row_idx_target - 2] if (row_idx_target - 2) < len(registros) else {}
        servicio_elegido = safe_get(fila_obj, "Servicio", "Disney+")
        perfil_asignado = safe_get(fila_obj, "Pantalla", "Perfil 1")
        cuenta_asignada = safe_get(fila_obj, "Cuenta", "Por Asignar")
        precio_usd = PRECIO_NETFLIX_USD if "netflix" in str(servicio_elegido).lower() else PRECIO_DISNEY_USD

        sheet.update_cell(row_idx_target, 6, "Pendiente Pago")

        aviso_stock = ""
        if "pendiente de stock" in str(cuenta_asignada).lower():
            aviso_stock = (
                "\n⏳ *Nota de Disponibilidad:* Nuestras cuentas inmediatas están llenas, "
                "pero al entregar tu pago quedas asegurado con **prioridad #1** en la asignación.\n"
            )

        mensaje_cliente = (
            "💵 *PAGO EN EFECTIVO REGISTRADO*\n\n"
            f"• *Operación:* {detalle_operacion}\n"
            f"• *Servicio:* {servicio_elegido} ({perfil_asignado})\n"
            f"• *Monto a cancelar:* `${precio_usd:.2f} USD`\n"
            f"{aviso_stock}\n"
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
                f"• *Correo/Cuenta:* {cuenta_asignada}\n"
                f"• *Monto esperado:* `${precio_usd:.2f} USD`"
            )
            teclado_admin = {
                "inline_keyboard": [
                    [{"text": "✅ Aprobar Efectivo (+30 días)", "callback_data": f"aprobar_{row_idx_target}_efectivo"}],
                    [{"text": "❌ Rechazar (Eliminar Fila)", "callback_data": f"rechazar_{row_idx_target}"}]
                ]
            }
            enviar_cb(int(ADMIN_ID), texto_admin, teclado_admin)
    except Exception as e:
        print(f"Error procesando notificación de efectivo: {e}")
        enviar_cb(chat_id, "⚠️ Ocurrió un error al registrar el pago en efectivo.", get_back_keyboard())


def iniciar_proceso_pago(chat_id, str_chat_id, nombre, username, servicio_clave, tipo_operacion, row_idx_target, message_id, enviar_cb, editar_cb, es_cb):
    esperando_captura_pago[str_chat_id] = row_idx_target
    
    es_netflix = (servicio_clave == "netflix")
    servicio_elegido = "Netflix" if es_netflix else "Disney+"
    precio_usd = PRECIO_NETFLIX_USD if es_netflix else PRECIO_DISNEY_USD
    sin_stock = False

    try:
        sheet = conectar_sheets()
        sheet.update_cell(row_idx_target, 6, "Pendiente Pago")
        sheet.update_cell(row_idx_target, 7, servicio_elegido)
        
        registros = sheet.get_all_records()
        fila_obj = registros[row_idx_target - 2] if (row_idx_target - 2) < len(registros) else {}
        if "pendiente de stock" in safe_get(fila_obj, "Cuenta", "").lower():
            sin_stock = True
    except Exception as e:
        print(f"Error actualizando celda de pago: {e}")

    tasa_usdt = obtener_tasa_usdt_hoy()
    monto_bs = round(precio_usd * tasa_usdt, 2)

    texto_soporte = f"Hola, tengo dudas o necesito asistencia técnica con mi servicio de Streaming. Mi ID de Telegram es: {str_chat_id}."
    url_whatsapp_soporte = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_soporte.replace(' ', '%20')}"

    aviso_stock = ""
    if sin_stock:
        aviso_stock = (
            "⏳ *NOTA DE DISPONIBILIDAD:* Nuestras cuentas de entrega inmediata para "
            f"*{servicio_elegido}* están al 100% en este instante, pero puedes realizar tu pago "
            "para asegurar **prioridad #1** en la asignación de nuestra próxima cuenta.\n\n"
        )
    
    mensaje = (
        f"💳 *DATOS DE PAGO — {servicio_elegido.upper()}*\n\n"
        f"{aviso_stock}"
        f"💵 *Monto:* `{precio_usd:.2f} USDT`\n"
        f"📈 *Tasa del día:* `{tasa_usdt} Bs`\n"
        f"💰 *Total a transferir:* `{monto_bs} Bs`\n\n"
        f"📲 *Datos de Pago Móvil (Toca para copiar):*\n"
        f"• *Banco:* {PAGO_MOVIL_BANCO}\n"
        f"• *Cédula:* `{PAGO_MOVIL_CEDULA}`\n"
        f"• *Teléfono:* `{PAGO_MOVIL_TELEFONO}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📸 *PASO FINAL:* Realiza el pago y **envía tu captura o referencia por este mismo chat**. (No es necesario enviarlo por WhatsApp)."
    )
    teclado_pago = {
        "inline_keyboard": [
            [{"text": "💬 Soporte Técnico (Solo dudas)", "url": url_whatsapp_soporte}],
            [{"text": "🔙 Cancelar y Volver", "callback_data": "menu_principal"}]
        ]
    }
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, mensaje, teclado_pago)
    else:
        enviar_cb(chat_id, mensaje, teclado_pago)


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
        mensaje = f"⚠️ No se encontraron códigos recientes de *{nombre_plataforma}*. Asegúrate de haberlo solicitado in tu TV hace unos segundos e intenta de nuevo."

    teclado = get_back_keyboard()
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, mensaje, teclado)
    else:
        enviar_cb(chat_id, mensaje, teclado)


def procesar_texto_reporte(chat_id, texto, nombre, username, enviar_cb, str_chat_id, row_idx_pendiente, enviar_foto_callback):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        fila_obj = registros[row_idx_pendiente - 2] if (row_idx_pendiente - 2) < len(registros) else {}
        cuenta_asociada = safe_get(fila_obj, "Cuenta", "Por Asignar")
        servicio_asociado = safe_get(fila_obj, "Servicio", "Disney+")
        pantalla_asociada = safe_get(fila_obj, "Pantalla", "Perfil 1")
    except Exception:
        cuenta_asociada = "Por Asignar"
        servicio_asociado = "Disney+"
        pantalla_asociada = "Perfil 1"

    if ADMIN_ID:
        texto_admin = (
            "🔔 *¡NUEVO REPORTE DE PAGO (TEXTO/REFERENCIA)!* 🔔\n\n"
            f"• *Cliente:* {nombre} (@{username})\n"
            f"• *Telegram ID:* `{str_chat_id}`\n"
            f"• *Servicio:* {servicio_asociado} ({pantalla_asociada})\n"
            f"• *Cuenta/Correo:* {cuenta_asociada}\n"
            f"• *Referencia/Detalle:* `{texto}`"
        )
        
        teclado_admin = {
            "inline_keyboard": [
                [{"text": "✅ Aprobar y Activar (+30 días)", "callback_data": f"aprobar_{row_idx_pendiente}_digital"}],
                [{"text": "❌ Rechazar (Eliminar Fila)", "callback_data": f"rechazar_{row_idx_pendiente}"}]
            ]
        }
        enviar_foto_callback(int(ADMIN_ID), photo_file_id, caption_admin, teclado_admin)

    enviar_cb(chat_id, "✅ Reporte enviado con éxito al administrador. En breve verificaremos tu referencia.", get_main_menu_keyboard())


# ==========================================
# FUNCIONES AUXILIARES DE GOOGLE SHEETS
# ==========================================
def obtener_primer_perfil_disponible(sheet, servicio_solicitado, correo_asignado):
    try:
        es_netflix = "netflix" in servicio_solicitado.lower()
        limite_maximo = 5 if es_netflix else 7

        registros = sheet.get_all_records()
        perfiles_ocupados_en_cuenta = set()

        for r in registros:
            srv = safe_get(r, "Servicio", "").lower()
            cta = safe_get(r, "Cuenta", "").lower()
            pnt = safe_get(r, "Pantalla", "").lower()
            
            if servicio_solicitado.lower() in srv and cta == correo_asignado.lower():
                for num in range(1, limite_maximo + 1):
                    if f"perfil {num}" in pnt:
                        perfiles_ocupados_en_cuenta.add(num)

        for num in range(1, limite_maximo + 1):
            if num not in perfiles_ocupados_en_cuenta:
                return f"Perfil {num}"

        return f"Perfil {limite_maximo + 1}"
    except Exception as e:
        print(f"Error buscando perfil disponible: {e}")
        return "Perfil 1"


def asignar_correo_desde_stock(sheet_principal, servicio_solicitado, chat_id="", nombre_cliente="", enviar_mensaje_callback=None):
    try:
        spreadsheet = sheet_principal.spreadsheet
        try:
            sheet_cuentas = spreadsheet.worksheet("Cuentas")
        except Exception:
            return "Por Asignar"

        registros_cuentas = sheet_cuentas.get_all_records()
        
        for idx_c, cuenta_row in enumerate(registros_cuentas, start=2):
            srv_cuenta = safe_get(cuenta_row, "Servicio", "").lower()
            estado_cuenta = safe_get(cuenta_row, "Estado", "").lower()
            
            if servicio_solicitado.lower() in srv_cuenta and estado_cuenta == "activa":
                try:
                    limite_defecto = 5 if "netflix" in servicio_solicitado.lower() else 7
                    capacidad = int(safe_get(cuenta_row, "Capacidad Total", str(limite_defecto)))
                    ocupados = int(safe_get(cuenta_row, "Perfiles Ocupados", "0"))
                except ValueError:
                    capacidad = 5 if "netflix" in servicio_solicitado.lower() else 7
                    ocupados = 0

                if ocupados < capacidad:
                    correo_encontrado = safe_get(cuenta_row, "Correo (Usuario)", safe_get(cuenta_row, "Correo", ""))
                    
                    nuevos_ocupados = ocupados + 1
                    sheet_cuentas.update_cell(idx_c, 5, nuevos_ocupados)
                    
                    if nuevos_ocupados >= capacidad:
                        sheet_cuentas.update_cell(idx_c, 6, "Llena")
                        if ADMIN_ID and enviar_mensaje_callback:
                            alerta_stock = (
                                f"⚠️ *¡ALERTA DE STOCK AGOTADO!* ⚠️\n\n"
                                f"La cuenta de *{servicio_solicitado}* (`{correo_encontrado}`) ha llegado al 100% de su capacidad y está *Llena*.\n\n"
                                f"💡 *Acción recomendada:* Carga una nueva cuenta en la pestaña 'Cuentas' lo antes posible."
                            )
                            try:
                                enviar_mensaje_callback(int(ADMIN_ID), alerta_stock)
                            except Exception:
                                pass
                        
                    return correo_encontrado
                    
        if ADMIN_ID and enviar_mensaje_callback:
            alerta_sin_stock = (
                f"🚨 *¡COMPRA CON STOCK AGOTADO (LISTA DE ESPERA)!* 🚨\n\n"
                f"• *Cliente:* {nombre_cliente}\n"
                f"• *Telegram ID:* `{chat_id}`\n"
                f"• *Servicio:* {servicio_solicitado}\n\n"
                f"💡 El cliente avanzó a pagar pero no había cuentas activas. Quedó marcado como *Pendiente de Stock*. ¡Carga una cuenta nueva y usa el botón *Asignar Stock Pendiente* en `/admin`!"
            )
            try:
                enviar_mensaje_callback(int(ADMIN_ID), alerta_sin_stock)
            except Exception:
                pass

        return "⚠️ Pendiente de Stock"
    except Exception as e:
        print(f"Error asignando correo desde stock: {e}")
        return "Por Asignar"


def procesar_asignacion_stock_masivo(enviar_msg_cb):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        
        try:
            sheet_cuentas = spreadsheet.worksheet("Cuentas")
        except Exception:
            return "❌ No se encontró la pestaña 'Cuentas' en el Google Sheets."

        registros_clientes = sheet_principal.get_all_records()
        registros_cuentas = sheet_cuentas.get_all_records()
        
        asignados_count = 0

        for idx_cli, cli_row in enumerate(registros_clientes, start=2):
            cuenta_actual = safe_get(cli_row, "Cuenta", "")
            
            if "pendiente de stock" in cuenta_actual.lower():
                servicio_cli = safe_get(cli_row, "Servicio", "Disney+")
                tid_cliente = safe_get(cli_row, "Telegram_ID", "")
                nombre_cliente = safe_get(cli_row, "Nombre", "Cliente")
                estado_cli = safe_get(cli_row, "Estado", "").lower()
                
                cuenta_encontrada = None
                idx_cuenta_encontrada = None
                
                for idx_c, cuenta_row in enumerate(registros_cuentas, start=2):
                    srv_cuenta = safe_get(cuenta_row, "Servicio", "").lower()
                    estado_cuenta = safe_get(cuenta_row, "Estado", "").lower()
                    
                    if servicio_cli.lower() in srv_cuenta and estado_cuenta == "activa":
                        try:
                            limite_defecto = 5 if "netflix" in servicio_cli.lower() else 7
                            capacidad = int(safe_get(cuenta_row, "Capacidad Total", str(limite_defecto)))
                            ocupados = int(safe_get(cuenta_row, "Perfiles Ocupados", "0"))
                        except ValueError:
                            capacidad = 5 if "netflix" in servicio_cli.lower() else 7
                            ocupados = 0

                        if ocupados < capacidad:
                            cuenta_encontrada = safe_get(cuenta_row, "Correo (Usuario)", safe_get(cuenta_row, "Correo", ""))
                            idx_cuenta_encontrada = idx_c
                            break
                
                if cuenta_encontrada and idx_cuenta_encontrada:
                    perfil_correcto = obtener_primer_perfil_disponible(sheet_principal, servicio_cli, cuenta_encontrada)
                    
                    sheet_principal.update_cell(idx_cli, 3, cuenta_encontrada)
                    sheet_principal.update_cell(idx_cli, 4, perfil_correcto)
                    
                    fila_c_actual = sheet_cuentas.row_values(idx_cuenta_encontrada)
                    try:
                        ocupados_actuales = int(fila_c_actual[4])
                    except (IndexError, ValueError):
                        ocupados_actuales = 0
                        
                    nuevos_ocupados = ocupados_actuales + 1
                    sheet_cuentas.update_cell(idx_cuenta_encontrada, 5, nuevos_ocupados)
                    
                    limite_defecto = 5 if "netflix" in servicio_cli.lower() else 7
                    capacidad_total = int(fila_c_actual[3]) if len(fila_c_actual) > 3 and fila_c_actual[3].isdigit() else limite_defecto
                    if nuevos_ocupados >= capacidad_total:
                        sheet_cuentas.update_cell(idx_cuenta_encontrada, 6, "Llena")

                    if tid_cliente and enviar_msg_cb and estado_cli == "activo":
                        try:
                            primer_nombre = nombre_cliente.split()[0] if nombre_cliente else "Cliente"
                            mensaje_notif = (
                                f"🎉 *¡EXCELENTE NOTICIA, {primer_nombre}!*\n\n"
                                f"Tu cuenta de *{servicio_cli}* ya ha sido asignada y se encuentra 100% **Activa**.\n\n"
                                f"• *Correo asignado:* `{cuenta_encontrada}`\n"
                                f"• *Perfil:* `{perfil_correcto}`\n\n"
                                "Puedes ingresar al bot y presionar **📲 Ver mis datos / pantallas** para consultar los detalles completos de tu acceso."
                            )
                            enviar_msg_cb(int(tid_cliente), mensaje_notif, get_main_menu_keyboard())
                        except Exception as e:
                            print(f"No se pudo notificar al cliente {tid_cliente}: {e}")

                    asignados_count += 1
                    registros_cuentas = sheet_cuentas.get_all_records()

        if asignados_count > 0:
            return f"✅ ¡Proceso exitoso! Se han asignado cuentas nuevas a **{asignados_count}** cliente(s) que estaban en lista de espera."
        else:
            return "ℹ️ No hay clientes pendientes de stock o no hay suficientes cuentas activas con cupo en la pestaña 'Cuentas'."

    except Exception as e:
        print(f"Error en asignación masiva de stock: {e}")
        return f"❌ Ocurrió un error al procesar la asignación: {e}"


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


def crear_nueva_fila_pendiente(str_chat_id, nombre, username="", servicio="Disney", enviar_mensaje_cb=None):
    try:
        sheet = conectar_sheets()
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        
        correo_asignado = asignar_correo_desde_stock(sheet, servicio, str_chat_id, nombre_completo, enviar_mensaje_cb)
        perfil_asignado = obtener_primer_perfil_disponible(sheet, servicio, correo_asignado)
        
        sheet.append_row([str(str_chat_id), nombre_completo, correo_asignado, perfil_asignado, "", "Pendiente Pago", servicio])
        return len(sheet.get_all_records()) + 1
    except Exception as e:
        print(f"Error creando fila nueva: {e}")
        return 2


def verificar_cliente_activo(chat_id):
    for sub in obtener_suscripciones_por_id(chat_id):
        estado = safe_get(sub, "Estado", "").lower()
        cuenta = safe_get(sub, "Cuenta", "").lower()
        if estado == "activo" and cuenta not in ("", "por asignar") and "pendiente" not in cuenta:
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


def obtener_clientes_activos_general():
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        activos = []
        for idx, row in enumerate(registros, start=2):
            estado = safe_get(row, "Estado", "").lower()
            cuenta = safe_get(row, "Cuenta", "")
            if estado == "activo" and cuenta and cuenta.lower() not in ("por asignar", "pendiente de stock"):
                activos.append((len(activos)+1, idx, row))
        return activos
    except Exception as e:
        print(f"Error obteniendo clientes activos: {e}")
        return []


def obtener_suscripciones_vencidas():
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        vencidos = []
        hoy = datetime.date.today()

        for idx, row in enumerate(registros, start=2):
            vencimiento_str = safe_get(row, "Vencimiento", "")
            estado = safe_get(row, "Estado", "").lower()
            cuenta = safe_get(row, "Cuenta", "")

            if cuenta and cuenta.lower() not in ("por asignar", "pendiente de stock"):
                for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                    try:
                        fecha_venc = datetime.datetime.strptime(vencimiento_str, fmt).date()
                        if fecha_venc < hoy or estado == "vencido":
                            vencidos.append((len(vencidos)+1, idx, row))
                        break
                    except ValueError:
                        continue
        return vencidos
    except Exception as e:
        print(f"Error obteniendo vencidos: {e}")
        return []


def liberar_y_eliminar_fila_suscripcion(row_idx):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        
        try:
            sheet_cuentas = spreadsheet.worksheet("Cuentas")
        except Exception:
            return "❌ No se encontró la pestaña 'Cuentas'."

        fila_datos = sheet_principal.row_values(row_idx)
        if len(fila_datos) < 3:
            return "❌ La fila seleccionada no es válida o está vacía."

        correo_a_liberar = safe_get({"Cuenta": fila_datos[2]}, "Cuenta", "")
        
        registros_cuentas = sheet_cuentas.get_all_records()
        cuenta_encontrada = False

        for idx_c, c_row in enumerate(registros_cuentas, start=2):
            correo_cta = safe_get(c_row, "Correo (Usuario)", safe_get(c_row, "Correo", ""))
            if correo_cta.lower() == correo_a_liberar.lower():
                try:
                    ocupados = int(safe_get(c_row, "Perfiles Ocupados", "1"))
                except ValueError:
                    ocupados = 1

                nuevos_ocupados = max(0, ocupados - 1)
                sheet_cuentas.update_cell(idx_c, 5, nuevos_ocupados)

                estado_actual = safe_get(c_row, "Estado", "").lower()
                if estado_actual == "llena":
                    sheet_cuentas.update_cell(idx_c, 6, "Activa")

                cuenta_encontrada = True
                break

        sheet_principal.delete_rows(row_idx)

        msg_extra = " y se liberó un cupo en la cuenta maestra" if cuenta_encontrada else ""
        return f"✅ ¡Suscripción de la fila {row_idx} eliminada con éxito{msg_extra}!"

    except Exception as e:
        print(f"Error liberando suscripción: {e}")
        return f"❌ Ocurrió un error al liberar la suscripción: {e}"


def aprobar_suscripcion_sheet(row_idx):
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        fila_actual = registros[row_idx - 2] if (row_idx - 2) < len(registros) else {}
        tid_cliente = safe_get(fila_actual, "Telegram_ID", "")
        nombre_cliente = safe_get(fila_actual, "Nombre", "Cliente")
        servicio_fila = safe_get(fila_actual, "Servicio", "Disney+")
        perfil_asignado = safe_get(fila_actual, "Pantalla", "Perfil 1")
        cuenta_fila = safe_get(fila_actual, "Cuenta", "Por Asignar")
        vencimiento_actual_str = safe_get(fila_actual, "Vencimiento", "")
        estado_actual = safe_get(fila_actual, "Estado", "").lower()

        if estado_actual == "activo":
            return True, tid_cliente, True, nombre_cliente, servicio_fila, perfil_asignado, "Renovación", cuenta_fila

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
        
        return True, tid_cliente, False, nombre_cliente, servicio_fila, perfil_asignado, tipo_operacion, cuenta_fila
    except Exception as e:
        print(f"Error aprobando suscripción: {e}")
        return False, None, False, "", "Disney+", "Perfil 1", "Renovación", "Por Asignar"


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
        en_espera_stock = sum(1 for r in registros if "pendiente de stock" in safe_get(r, "Cuenta", "").lower())
        vencidos_total = len(obtener_suscripciones_vencidas())
        unicos = len(set(safe_get(r, "Telegram_ID", "") for r in registros if safe_get(r, "Telegram_ID", "")))
        return (
            "📊 *PANEL DE CONTROL INDUSTRIAL*\n\n"
            f"👥 *Clientes únicos:* {unicos}\n"
            f"📺 *Total pantallas:* {len(registros)}\n"
            f"🟢 *Activas:* {activas}\n"
            f"🟡 *Pagos pendientes:* {pendientes}\n"
            f"🔴 *Vencidas por depurar:* {vencidos_total}\n"
            f"⏳ *En espera de stock:* {en_espera_stock}"
        )
    except Exception as e:
        return f"❌ Error: {e}"


def generar_resumen_completo_negocio():
    """Calcula y extrae métricas detalladas de inventario, cuentas maestras, ventas y recaudación de Google Sheets."""
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        
        registros_clientes = sheet_principal.get_all_records()
        total_pantallas = len(registros_clientes)
        activas_cli = sum(1 for r in registros_clientes if safe_get(r, "Estado", "").lower() == "activo")
        pendientes_pago = sum(1 for r in registros_clientes if "pendiente" in safe_get(r, "Estado", "").lower())
        en_espera_stock = sum(1 for r in registros_clientes if "pendiente de stock" in safe_get(r, "Cuenta", "").lower())
        clientes_unicos = len(set(safe_get(r, "Telegram_ID", "") for r in registros_clientes if safe_get(r, "Telegram_ID", "")))

        netflix_cli = sum(1 for r in registros_clientes if "netflix" in safe_get(r, "Servicio", "").lower())
        disney_cli = sum(1 for r in registros_clientes if "disney" in safe_get(r, "Servicio", "").lower())

        total_cuentas_maestras = 0
        cuentas_activas_stock = 0
        cuentas_llenas_stock = 0
        capacidad_total_perfiles = 0
        perfiles_totales_ocupados = 0

        try:
            sheet_cuentas = spreadsheet.worksheet("Cuentas")
            registros_cuentas = sheet_cuentas.get_all_records()
            total_cuentas_maestras = len(registros_cuentas)
            for c in registros_cuentas:
                est_c = safe_get(c, "Estado", "").lower()
                if est_c == "activa":
                    cuentas_activas_stock += 1
                elif est_c == "llena":
                    cuentas_llenas_stock += 1
                
                try:
                    cap = int(safe_get(c, "Capacidad Total", "5"))
                    ocu = int(safe_get(c, "Perfiles Ocupados", "0"))
                except ValueError:
                    cap = 5
                    ocu = 0
                
                capacidad_total_perfiles += cap
                perfiles_totales_ocupados += ocu
        except Exception:
            pass

        total_ingresos_usd = 0.0
        ventas_totales_count = 0
        try:
            sheet_ventas = spreadsheet.worksheet("Ventas")
            registros_ventas = sheet_ventas.get_all_records()
            ventas_totales_count = len(registros_ventas)
            for v in registros_ventas:
                monto_str = safe_get(v, "Monto USD", "0").replace("$", "").strip()
                try:
                    total_ingresos_usd += float(monto_str)
                except ValueError:
                    pass
        except Exception:
            pass

        cupos_disponibles = max(0, capacidad_total_perfiles - perfiles_totales_ocupados)

        resumen_texto = (
            "📈 *RESUMEN GENERAL DEL NEGOCIO* 📈\n\n"
            f"👤 *Clientes y Demografía:*\n"
            f"• Clientes únicos: `{clientes_unicos}`\n"
            f"• Pantallas alquiladas: `{total_pantallas}` (🟢 Activas: `{activas_cli}`)\n"
            f"• Desglose: 📺 Netflix: `{netflix_cli}` | 📺 Disney+: `{disney_cli}`\n\n"
            f"📦 *Estado del Inventario (Cuentas Maestras):*\n"
            f"• Cuentas totales: `{total_cuentas_maestras}` (🟢 Activas: `{cuentas_activas_stock}` | 🔴 Llenas: `{cuentas_llenas_stock}`)\n"
            f"• Capacidad de perfiles: `{perfiles_totales_ocupados} / {capacidad_total_perfiles}`\n"
            f"• Cupos libres en stock: `{cupos_disponibles}`\n"
            f"• Clientes en lista de espera (Sin stock): `{en_espera_stock}`\n\n"
            f"💰 *Finanzas y Rendimiento:*\n"
            f"• Transacciones registradas: `{ventas_totales_count}`\n"
            f"• Ingresos acumulados: *`${total_ingresos_usd:.2f} USD`*\n"
            f"• Pagos pendientes por verificar: `{pendientes_pago}`"
        )
        return resumen_texto
    except Exception as e:
        return f"❌ Error al generar el resumen del negocio: {e}"


def get_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📲 Ver mis datos / pantallas", "callback_data": "ver_datos"}],
            [{"text": "🔑 Solicitar Código", "callback_data": "obtener_codigo"}],
            [{"text": "🔄 Renovar (+30 días)", "callback_data": "renovar_suscripcion"}, {"text": "➕ Otra Pantalla", "callback_data": "comprar_extra"}],
            [{"text": "💬 Soporte / Pagos", "callback_data": "soporte"}]
        ]
    }


def get_datos_keyboard(mostrar_renovar=False, suscripciones=None):
    botones = []
    if suscripciones:
        tiene_activas = any(safe_get(s, "Estado", "").lower() == "activo" and "pendiente" not in safe_get(s, "Cuenta", "").lower() for s in suscripciones)
        if tiene_activas:
            botones.append([{"text": "✏️ Personalizar Nombres de Perfil", "callback_data": "menu_renombrar"}])

    if mostrar_renovar: 
        botones.append([{"text": "🔄 Renovar Suscripción", "callback_data": "renovar_suscripcion"}])
        
    botones.append([{"text": "➕ Comprar Pantalla Adicional", "callback_data": "comprar_extra"}])
    botones.append([{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}])
    return {"inline_keyboard": botones}


def get_back_keyboard():
    return {
        "inline_keyboard": [[{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]]
    }
