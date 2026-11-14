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
PRECIO_DISNEY_USD = 5.0
PRECIO_NETFLIX_USD = 4.5
TASA_RESPALDO_BS = 65.0

PAGO_MOVIL_BANCO = "🏦 Provincial (0108)"
PAGO_MOVIL_CEDULA = "27538779"
PAGO_MOVIL_TELEFONO = "04247091547"

control_intentos_otp = {}
MAX_INTENTOS_RAPIDOS = 2
COOLDOWN_SEGUNDOS = 180

# Control de estados temporales y asistentes
esperando_captura_pago = {}
esperando_nuevo_nombre_perfil = {}
esperando_busqueda_admin = {}
asistente_cuenta_datos = {}
admin_editando_cliente = {}


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
    except Exception:
        pass

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
    """Cerebro industrial con selector manual de cuentas y perfiles específicos para el administrador."""
    
    str_chat_id = str(chat_id).strip()
    accion = callback_data if es_callback else texto.lower().strip()

    # -------------------------------------------------------------
    # ASISTENTE ADMIN: CARGA PASO A PASO DE CUENTA Y PINS
    # -------------------------------------------------------------
    if not es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and str_chat_id in asistente_cuenta_datos and texto:
        estado_actual = asistente_cuenta_datos[str_chat_id]
        paso = estado_actual.get("paso")

        if paso == "esperando_correo":
            estado_actual["correo"] = texto.strip()
            limite = estado_actual["limite"]
            estado_actual["paso"] = "esperando_pin"
            estado_actual["perfil_actual"] = 1
            estado_actual["pins"] = {}

            enviar_mensaje_callback(
                chat_id,
                f"🔑 *CONFIGURACIÓN DE PINS DE SEGURIDAD*\n\n"
                f"Servicio: *{estado_actual['servicio']}* ({limite} perfiles en total).\n\n"
                f"Por favor, escribe el PIN correspondiente al *Perfil 1* (Ej: `1234`):"
            )
            return

        elif paso == "esperando_pin":
            p_num = estado_actual["perfil_actual"]
            limite = estado_actual["limite"]
            pin_ingresado = texto.strip()
            
            estado_actual["pins"][f"Perfil {p_num}"] = pin_ingresado
            p_num += 1
            estado_actual["perfil_actual"] = p_num

            if p_num <= limite:
                enviar_mensaje_callback(
                    chat_id,
                    f"✅ PIN del Perfil {p_num - 1} guardado.\n\n"
                    f"Ahora escribe el PIN correspondiente al *Perfil {p_num}*:"
                )
                return
            else:
                srv = estado_actual["servicio"]
                correo = estado_actual["correo"]
                pins_dict = estado_actual["pins"]
                pins_formato_texto = " | ".join([f"{k}: {v}" for k, v in pins_dict.items()])

                try:
                    sheet_principal = conectar_sheets()
                    spreadsheet = sheet_principal.spreadsheet
                    
                    try:
                        sheet_cuentas = spreadsheet.worksheet("Cuentas")
                    except Exception:
                        sheet_cuentas = spreadsheet.add_worksheet(title="Cuentas", rows="1000", cols="7")
                        sheet_cuentas.append_row(["Servicio", "Correo", "Contraseña", "Capacidad Total", "Perfiles Ocupados", "Estado", "PINs de Perfiles"])

                    try:
                        fila_1 = sheet_cuentas.row_values(1)
                        if len(fila_1) < 7:
                            sheet_cuentas.update("A1:G1", [["Servicio", "Correo", "Contraseña", "Capacidad Total", "Perfiles Ocupados", "Estado", "PINs de Perfiles"]])
                    except Exception:
                        pass

                    sheet_cuentas.append_row([srv, correo, "", str(limite), "0", "Activa", pins_formato_texto])
                    asistente_cuenta_datos.pop(str_chat_id)

                    enviar_mensaje_callback(
                        chat_id,
                        f"✅ *¡CUENTA MAESTRA Y PINS CONFIGURADOS!*\n\n"
                        f"• *Servicio:* {srv}\n"
                        f"• *Correo:* `{correo}`\n"
                        f"• *PINs:* `{pins_formato_texto}`",
                        {
                            "inline_keyboard": [
                                [{"text": "📦 Asignar Stock Pendiente", "callback_data": "admin_asignar_stock"}],
                                [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                            ]
                        }
                    )
                except Exception as e:
                    asistente_cuenta_datos.pop(str_chat_id)
                    enviar_mensaje_callback(chat_id, f"❌ Error guardando: {e}", {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_volver"}]]})
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
            enviar_mensaje_callback(chat_id, f"❌ No se encontró ningún cliente activo con: *{texto}*.", {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_volver"}]]})
            return

        enviar_mensaje_callback(chat_id, f"🔍 *Resultados para:* `{texto}` ({len(encontrados)} encontrados)")
        
        for row_idx, act in encontrados:
            srv_a = safe_get(act, "Servicio", "Disney+")
            pnt_a = safe_get(act, "Pantalla", "Perfil 1")
            cta_a = safe_get(act, "Cuenta", "Cuenta")
            nom_a = safe_get(act, "Nombre", "Cliente")
            tid_a = safe_get(act, "Telegram_ID", "")
            fec_a = safe_get(act, "Vencimiento", "N/A")
            pin_a = obtener_pin_asignado_cliente(cta_a, pnt_a)
            
            txt = (
                f"🟢 *Fila {row_idx}*\n"
                f"• *Cliente:* {nom_a}\n"
                f"• *Telegram ID:* `{tid_a}`\n"
                f"• *Servicio:* {srv_a} ({pnt_a})\n"
                f"• *Correo:* `{cta_a}`\n"
                f"• *PIN:* `{pin_a}` 🔒\n"
                f"• *Vence el:* `{fec_a}`"
            )
            teclado_gestion = {
                "inline_keyboard": [
                    [{"text": "✏️ Editar Datos Manualmente", "callback_data": f"admin_editar_{row_idx}"}],
                    [{"text": "🚨 Expulsar y Liberar Cupo", "callback_data": f"admin_expulsar_{row_idx}"}]
                ]
            }
            enviar_mensaje_callback(chat_id, txt, teclado_gestion)
            
        enviar_mensaje_callback(chat_id, "Búsqueda finalizada.", {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]})
        return

    # -------------------------------------------------------------
    # CAPTURA DE FECHA MANUAL PARA EDICIÓN
    # -------------------------------------------------------------
    if not es_callback and ADMIN_ID and str_chat_id == ADMIN_ID and str_chat_id in admin_editando_cliente and texto:
        modo_edicion = admin_editando_cliente[str_chat_id].get("modo")
        row_idx_edit = admin_editando_cliente[str_chat_id].get("row_idx")

        if modo_edicion == "cambiar_fecha":
            nueva_fecha = texto.strip()
            try:
                datetime.datetime.strptime(nueva_fecha, "%Y-%m-%d")
                sheet = conectar_sheets()
                sheet.update_cell(row_idx_edit, 5, nueva_fecha)
                admin_editando_cliente.pop(str_chat_id)

                enviar_mensaje_callback(chat_id, f"✅ *Fecha actualizada con éxito:* `{nueva_fecha}`", {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_volver"}]]})
            except ValueError:
                enviar_mensaje_callback(chat_id, "⚠️ Formato incorrecto. Escríbela en formato `YYYY-MM-DD` (Ej: `2026-12-31`):")
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
        if str_chat_id in asistente_cuenta_datos:
            asistente_cuenta_datos.pop(str_chat_id)
        if str_chat_id in admin_editando_cliente:
            admin_editando_cliente.pop(str_chat_id)
            
        texto_menu = "🤖 *Menú Principal*\nSelecciona una opción:"
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, texto_menu, get_main_menu_keyboard())
        else:
            enviar_mensaje_callback(chat_id, texto_menu, get_main_menu_keyboard())
        return

    # -------------------------------------------------------------
    # CAPTURA DE FOTO / COMPROBANTE
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
                "🔔 *¡NUEVO COMPROBANTE!* 🔔\n\n"
                f"• *Cliente:* {nombre} (@{username}) (`{str_chat_id}`)\n"
                f"• *Servicio:* {servicio_asociado} ({pantalla_asociada})"
            )
            teclado_admin = {
                "inline_keyboard": [
                    [{"text": "✅ Aprobar y Activar", "callback_data": f"aprobar_{row_idx_pendiente}_digital"}],
                    [{"text": "❌ Rechazar", "callback_data": f"rechazar_{row_idx_pendiente}"}]
                ]
            }
            enviar_foto_callback(int(ADMIN_ID), photo_file_id, caption_admin, teclado_admin)

        enviar_mensaje_callback(chat_id, "✅ Comprobante recibido. En breve será verificado.", {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "menu_principal"}]]})
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
        botones_selector.append([{"text": "🔙 Cancelar", "callback_data": "menu_principal"}])

        enviar_mensaje_callback(chat_id, "💵 *PAGO EN EFECTIVO*\nSelecciona qué pantalla vas a renovar o adquirir:", {"inline_keyboard": botones_selector})
        return

    elif accion.startswith("efectivo_fila_"):
        try:
            row_idx_elegido = int(accion.split("_")[-1])
            notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, row_idx_elegido, "Renovación", enviar_mensaje_callback, editar_mensaje_callback, message_id, es_callback)
        except Exception:
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error.", get_back_keyboard())
        return

    elif accion.startswith("efectivo_nuevo_"):
        try:
            servicio_elegido = "Netflix" if "netflix" in accion else "Disney+"
            nueva_fila_idx = crear_nueva_fila_pendiente(str_chat_id, nombre, username, servicio_elegido, enviar_mensaje_callback)
            esperando_captura_pago[str_chat_id] = nueva_fila_idx
            notificar_pago_efectivo(chat_id, str_chat_id, nombre, username, nueva_fila_idx, "Pantalla Nueva", enviar_mensaje_callback, editar_mensaje_callback, message_id, es_callback)
        except Exception:
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error.", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # PANEL DE ADMINISTRADOR Y EDITOR MANUAL CON SELECCIÓN DE PERFIL
    # -------------------------------------------------------------
    if accion == "/admin" or accion == "admin_volver":
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)
        if str_chat_id in esperando_busqueda_admin:
            esperando_busqueda_admin.pop(str_chat_id)
        if str_chat_id in asistente_cuenta_datos:
            asistente_cuenta_datos.pop(str_chat_id)
        if str_chat_id in admin_editando_cliente:
            admin_editando_cliente.pop(str_chat_id)

        if ADMIN_ID and str_chat_id == ADMIN_ID:
            reporte = generar_reporte_admin()
            teclado = {
                "inline_keyboard": [
                    [{"text": "📊 Resumen General del Negocio", "callback_data": "admin_resumen_negocio"}],
                    [{"text": "📋 Ver Pagos Pendientes", "callback_data": "admin_ver_pendientes"}],
                    [{"text": "➕ Cargar Cuenta y PINs (Stock)", "callback_data": "admin_cargar_cuenta"}],
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
            enviar_mensaje_callback(chat_id, "⛔ No tienes permisos.", get_main_menu_keyboard())
        return

    elif accion == "admin_resumen_negocio":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            resumen_detallado = generar_resumen_completo_negocio()
            teclado_resumen = {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_volver"}]]}
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, resumen_detallado, teclado_resumen)
            else:
                enviar_mensaje_callback(chat_id, resumen_detallado, teclado_resumen)
        return

    elif accion == "admin_cargar_cuenta":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            mensaje_carga = "➕ *CARGAR NUEVA CUENTA Y PINS*\nSelecciona la plataforma:"
            teclado_servicios = {
                "inline_keyboard": [
                    [{"text": "📺 Netflix (5 Perfiles)", "callback_data": "admin_cuenta_netflix"}],
                    [{"text": "📺 Disney+ (7 Perfiles)", "callback_data": "admin_cuenta_disney"}],
                    [{"text": "🔙 Volver", "callback_data": "admin_volver"}]
                ]
            }
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_carga, teclado_servicios)
            else:
                enviar_mensaje_callback(chat_id, mensaje_carga, teclado_servicios)
        return

    elif accion == "admin_cuenta_netflix" or accion == "admin_cuenta_disney":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            es_netflix = "netflix" in accion
            servicio_elegido = "Netflix" if es_netflix else "Disney+"
            limite_perfiles = 5 if es_netflix else 7

            asistente_cuenta_datos[str_chat_id] = {
                "servicio": servicio_elegido,
                "limite": limite_perfiles,
                "paso": "esperando_correo"
            }

            mensaje_peticion = f"➕ *NUEVA CUENTA DE {servicio_elegido.upper()}*\nPaso 1/2: Escribe el **correo y contraseña**:"
            teclado_canc = {"inline_keyboard": [[{"text": "🔙 Cancelar", "callback_data": "admin_volver"}]]}
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_peticion, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, mensaje_peticion, teclado_canc)
        return

    elif accion == "admin_pedir_busqueda":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            esperando_busqueda_admin[str_chat_id] = True
            mensaje_busqueda = "🔍 *BUSCAR CLIENTE ACTIVO*\nEscribe el nombre, usuario (@), ID o correo:"
            teclado_canc = {"inline_keyboard": [[{"text": "🔙 Cancelar", "callback_data": "admin_volver"}]]}
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_busqueda, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, mensaje_busqueda, teclado_canc)
        return

    elif accion == "admin_asignar_stock":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            resultado_asignacion = procesar_asignacion_stock_masivo(enviar_mensaje_callback)
            enviar_mensaje_callback(chat_id, resultado_asignacion, {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_volver"}]]})
        return

    elif accion == "admin_ver_pendientes":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            pendientes = obtener_clientes_pendientes()
            if not pendientes:
                enviar_mensaje_callback(chat_id, "✅ No hay pagos pendientes.", {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_volver"}]]})
            else:
                for idx, row_idx, p in pendientes:
                    srv_p = safe_get(p, "Servicio", "Disney+")
                    pnt_p = safe_get(p, "Pantalla", "Perfil 1")
                    txt = f"🟡 *Pago Pendiente #{idx}* (Fila {row_idx})\n• *Cliente:* {safe_get(p, 'Nombre')}\n• *Servicio:* {srv_p} ({pnt_p})"
                    teclado_aprobar = {
                        "inline_keyboard": [
                            [{"text": "✅ Aprobar", "callback_data": f"aprobar_{row_idx}_digital"}],
                            [{"text": "❌ Rechazar", "callback_data": f"rechazar_{row_idx}"}]
                        ]
                    }
                    enviar_mensaje_callback(chat_id, txt, teclado_aprobar)
        return

    elif accion.startswith("admin_editar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx_edit = int(accion.split("_")[-1])
                sheet = conectar_sheets()
                registros = sheet.get_all_records()
                fila_obj = registros[row_idx_edit - 2] if (row_idx_edit - 2) < len(registros) else {}

                nom = safe_get(fila_obj, "Nombre", "Cliente")
                srv = safe_get(fila_obj, "Servicio", "Disney+")
                cta = safe_get(fila_obj, "Cuenta", "Correo")
                pnt = safe_get(fila_obj, "Pantalla", "Perfil 1")
                fec = safe_get(fila_obj, "Vencimiento", "N/A")
                pin = obtener_pin_asignado_cliente(cta, pnt)

                msg_editor = (
                    f"✏️ *EDITOR MANUAL DE CLIENTE* (Fila {row_idx_edit})\n\n"
                    f"• *Cliente:* {nom}\n"
                    f"• *Servicio:* {srv}\n"
                    f"• *Cuenta actual:* `{cta}`\n"
                    f"• *Perfil actual:* {pnt}\n"
                    f"• *PIN actual:* `{pin}` 🔒\n"
                    f"• *Vencimiento:* `{fec}`\n\n"
                    "Selecciona qué deseas modificar:"
                )
                teclado_editor = {
                    "inline_keyboard": [
                        [{"text": "📧 Cambiar de Cuenta y Elegir Perfil", "callback_data": f"edit_mudar_{row_idx_edit}"}],
                        [{"text": "📅 Cambiar Fecha de Vencimiento", "callback_data": f"edit_fecha_{row_idx_edit}"}],
                        [{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]
                    ]
                }
                if editar_mensaje_callback and message_id:
                    editar_mensaje_callback(chat_id, message_id, msg_editor, teclado_editor)
                else:
                    enviar_mensaje_callback(chat_id, msg_editor, teclado_editor)
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    # Paso 1 para mudar: Elegir la nueva cuenta
    elif accion.startswith("edit_mudar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx_edit = int(accion.split("_")[-1])
                sheet = conectar_sheets()
                registros = sheet.get_all_records()
                fila_obj = registros[row_idx_edit - 2] if (row_idx_edit - 2) < len(registros) else {}
                srv_cliente = safe_get(fila_obj, "Servicio", "Disney+")

                cuentas_libres = obtener_cuentas_con_cupos_libres(srv_cliente)
                if not cuentas_libres:
                    enviar_mensaje_callback(chat_id, f"⚠️ No hay cuentas activas con cupos libres para *{srv_cliente}*.", {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": f"admin_editar_{row_idx_edit}"}]]})
                    return

                botones_cuentas = []
                for correo_disp in cuentas_libres:
                    botones_cuentas.append([{"text": f"📺 {correo_disp}", "callback_data": f"elegir_cuenta_{row_idx_edit}_{correo_disp}"}])
                botones_cuentas.append([{"text": "🔙 Volver", "callback_data": f"admin_editar_{row_idx_edit}"}])

                msg_mudanza = f"📧 *PASO 1: ELEGIR NUEVA CUENTA ({srv_cliente})*\nSelecciona la cuenta maestra de destino:"
                if editar_mensaje_callback and message_id:
                    editar_mensaje_callback(chat_id, message_id, msg_mudanza, {"inline_keyboard": botones_cuentas})
                else:
                    enviar_mensaje_callback(chat_id, msg_mudanza, {"inline_keyboard": botones_cuentas})
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    # Paso 2 para mudar: Mostrar los perfiles libres de esa cuenta para que el admin elija manualmente
    elif accion.startswith("elegir_cuenta_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                partes = accion.replace("elegir_cuenta_", "").split("_")
                row_idx_edit = int(partes[0])
                cuenta_destino = "_".join(partes[1:])

                sheet = conectar_sheets()
                registros = sheet.get_all_records()
                fila_obj = registros[row_idx_edit - 2] if (row_idx_edit - 2) < len(registros) else {}
                srv_cliente = safe_get(fila_obj, "Servicio", "Disney+")

                perfiles_libres = obtener_perfiles_libres_especificos(sheet, srv_cliente, cuenta_destino)
                if not perfiles_libres:
                    enviar_mensaje_callback(chat_id, "⚠️ Esta cuenta ya no tiene perfiles libres disponibles.", {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": f"edit_mudar_{row_idx_edit}"}]]})
                    return

                botones_perfiles = []
                for p_libre in perfiles_libres:
                    pin_del_p = obtener_pin_asignado_cliente(cuenta_destino, p_libre)
                    botones_perfiles.append([{"text": f"👤 {p_libre} (PIN: {pin_del_p})", "callback_data": f"asignar_manual_{row_idx_edit}_{cuenta_destino}_{p_libre}"}])

                botones_perfiles.append([{"text": "🔙 Volver", "callback_data": f"edit_mudar_{row_idx_edit}"}])

                msg_perfiles = f"👤 *PASO 2: ELEGIR PERFIL ESPECÍFICO*\nCuenta: `{cuenta_destino}`\n\nSelecciona el perfil exacto que deseas asignarle:"
                if editar_mensaje_callback and message_id:
                    editar_mensaje_callback(chat_id, message_id, msg_perfiles, {"inline_keyboard": botones_perfiles})
                else:
                    enviar_mensaje_callback(chat_id, msg_perfiles, {"inline_keyboard": botones_perfiles})
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    # Paso 3: Aplicar el cambio manual con cuenta y perfil exacto seleccionado
    elif accion.startswith("asignar_manual_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                resto = accion.replace("asignar_manual_", "")
                # Separamos el row_idx (primer valor antes del primer guion bajo)
                partes_rev = resto.split("_")
                row_idx_edit = int(partes_rev[0])
                
                # Lo demás contiene el correo y el perfil (ej: "correo@gmail.com_Perfil_2")
                resto_correo_perfil = "_".join(partes_rev[1:])
                
                # El perfil siempre es el último fragmento ("Perfil 1", "Perfil 2", etc.)
                if "perfil " in resto_correo_perfil.lower():
                    idx_p = resto_correo_perfil.lower().rfind("perfil ")
                    nuevo_correo = resto_correo_perfil[:idx_p].strip("_")
                    nuevo_perfil = resto_correo_perfil[idx_p:].replace("_", " ").title()
                else:
                    nuevo_correo = resto_correo_perfil
                    nuevo_perfil = "Perfil 1"

                sheet = conectar_sheets()
                spreadsheet = sheet.spreadsheet
                sheet_cuentas = spreadsheet.worksheet("Cuentas")

                registros = sheet.get_all_records()
                fila_vieja = registros[row_idx_edit - 2] if (row_idx_edit - 2) < len(registros) else {}
                correo_viejo = safe_get(fila_vieja, "Cuenta", "")
                srv_cliente = safe_get(fila_vieja, "Servicio", "Disney+")
                tid_cliente = safe_get(fila_vieja, "Telegram_ID", "")

                # 1. Liberamos cupo en la cuenta vieja
                if correo_viejo and "pendiente" not in correo_viejo.lower():
                    liberar_cupo_cuenta_maestra(sheet_cuentas, correo_viejo)

                # 2. Ocupamos cupo en la cuenta nueva
                ocupar_cuenta_maestra_especifica(sheet_cuentas, nuevo_correo)

                # 3. Guardamos los nuevos datos en la fila del cliente
                sheet.update_cell(row_idx_edit, 3, nuevo_correo)
                sheet.update_cell(row_idx_edit, 4, nuevo_perfil)
                pin_asignado = obtener_pin_asignado_cliente(nuevo_correo, nuevo_perfil)

                msg_exito = (
                    f"✅ *¡MUDANZA Y PERFIL ASIGNADO CON ÉXITO!* (Fila {row_idx_edit})\n\n"
                    f"• *Nueva Cuenta:* `{nuevo_correo}`\n"
                    f"• *Perfil Elegido:* {nuevo_perfil}\n"
                    f"• *PIN de seguridad:* `{pin_asignado}` 🔒"
                )
                if editar_mensaje_callback and message_id:
                    editar_mensaje_callback(chat_id, message_id, msg_exito, {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]})
                else:
                    enviar_mensaje_callback(chat_id, msg_exito, {"inline_keyboard": [[{"text": "🔙 Volver al Panel Admin", "callback_data": "admin_volver"}]]})

                if tid_cliente:
                    try:
                        msg_cli = (
                            "🔄 *ACTUALIZACIÓN DE TU CUENTA*\n\n"
                            f"Tu servicio de *{srv_cliente}* ha sido actualizado.\n\n"
                            f"• *Correo:* `{nuevo_correo}`\n"
                            f"• *Perfil:* `{nuevo_perfil}`\n"
                            f"• *PIN:* `{pin_asignado}` 🔒"
                        )
                        enviar_mensaje_callback(int(tid_cliente), msg_cli, get_main_menu_keyboard())
                    except Exception:
                        pass
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error aplicando asignación manual: {e}", get_back_keyboard())
        return

    elif accion.startswith("edit_fecha_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            row_idx_edit = int(accion.split("_")[-1])
            admin_editando_cliente[str_chat_id] = {"modo": "cambiar_fecha", "row_idx": row_idx_edit}

            msg_pide_fecha = "📅 *CAMBIAR FECHA DE VENCIMIENTO*\nEscribe la nueva fecha en formato `YYYY-MM-DD` (Ej: `2026-12-31`):"
            teclado_canc = {"inline_keyboard": [[{"text": "🔙 Cancelar", "callback_data": f"admin_editar_{row_idx_edit}"}]]}
            if editar_mensaje_callback and message_id:
                editar_mensaje_callback(chat_id, message_id, msg_pide_fecha, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, msg_pide_fecha, teclado_canc)
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

                enviar_mensaje_callback(chat_id, f"🚨 {resultado_expulsion}", {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_volver"}]]})
                if tid_cliente:
                    try:
                        enviar_mensaje_callback(int(tid_cliente), f"⚠️ Tu suscripción a *{srv_exp}* ({pnt_exp}) ha finalizado.", get_main_menu_keyboard())
                    except Exception:
                        pass
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    elif accion == "admin_ver_vencidos":
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            vencidos = obtener_suscripciones_vencidas()
            if not vencidos:
                enviar_mensaje_callback(chat_id, "✅ No hay pantallas vencidas.", {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_volver"}]]})
            else:
                for idx, row_idx, v in vencidos:
                    srv_v = safe_get(v, "Servicio", "Disney+")
                    pnt_v = safe_get(v, "Pantalla", "Perfil 1")
                    fec_v = safe_get(v, "Vencimiento", "N/A")
                    txt = f"🔴 *Vencida #{idx}* (Fila {row_idx})\n• *Cliente:* {safe_get(v, 'Nombre')}\n• *Servicio:* {srv_v} ({pnt_v})\n• *Venció:* `{fec_v}`"
                    teclado_borrar = {
                        "inline_keyboard": [
                            [{"text": "🗑️ Liberar y Borrar", "callback_data": f"admin_liberar_{row_idx}"}],
                            [{"text": "🔙 Volver", "callback_data": "admin_volver"}]
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
                enviar_mensaje_callback(chat_id, resultado_liberacion, {"inline_keyboard": [[{"text": "🔙 Volver", "callback_data": "admin_volver"}]]})
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
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
                    enviar_mensaje_callback(chat_id, "ℹ️ La suscripción ya estaba activa.", get_back_keyboard())
                    return

                if exito:
                    monto_venta = PRECIO_NETFLIX_USD if "netflix" in str(srv_aprobado).lower() else PRECIO_DISNEY_USD
                    registrar_venta_en_historial(nombre_cliente, tid_cliente, srv_aprobado, perfil_asignado, monto_venta, tipo_operacion, metodo_pago)

                    enviar_mensaje_callback(chat_id, f"✅ Fila {row_idx} activada y registrada.", get_back_keyboard())
                    if tid_cliente:
                        try:
                            pin_entregado = obtener_pin_asignado_cliente(cuenta_fila, perfil_asignado)
                            msg_cliente = (
                                "🎉 *¡Pago verificado y aprobado!*\n\n"
                                f"Tu servicio de *{srv_aprobado}* ({perfil_asignado}) está *Activo* por 30 días.\n"
                                f"• *PIN de seguridad:* `{pin_entregado}` 🔒"
                            )
                            enviar_mensaje_callback(int(tid_cliente), msg_cliente, get_main_menu_keyboard())
                        except Exception:
                            pass
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    elif accion.startswith("rechazar_"):
        if ADMIN_ID and str_chat_id == ADMIN_ID:
            try:
                row_idx = int(accion.split("_")[1])
                limpiar_fila_cancelada(row_idx)
                if message_id:
                    quitar_botones_telegram(chat_id, message_id)
                enviar_mensaje_callback(chat_id, "❌ Pago rechazado y fila eliminada.", get_back_keyboard())
            except Exception as e:
                enviar_mensaje_callback(chat_id, f"❌ Error: {e}", get_back_keyboard())
        return

    # -------------------------------------------------------------
    # MENÚ CLIENTE
    # -------------------------------------------------------------
    elif accion == "ver_datos" or "cuenta" in accion:
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

        suscripciones = obtener_suscripciones_por_id(chat_id)
        if not suscripciones:
            mensaje = "⚠️ No tienes pantallas registradas."
            teclado = get_back_keyboard()
        else:
            total = len(suscripciones)
            encabezado = f"📋 *TUS DATOS DE SUSCRIPCIÓN ({total})*\n\n"
            bloques = []
            tiene_por_renovar = False

            for idx, sub in enumerate(suscripciones, start=1):
                servicio = safe_get(sub, "Servicio", "Disney+")
                correo_raw = safe_get(sub, "Cuenta", "Por Asignar")
                pantalla = safe_get(sub, "Pantalla", "Perfil 1")
                vencimiento = safe_get(sub, "Vencimiento", "Sin fecha")
                estado = safe_get(sub, "Estado", "Pendiente Pago")
                
                pin_perfil = obtener_pin_asignado_cliente(correo_raw, pantalla)
                correo_mostrar = "⏳ En asignación" if "pendiente de stock" in correo_raw.lower() else f"`{correo_raw}`"
                pin_mostrar = "Pendiente" if "pendiente de stock" in correo_raw.lower() else f"`{pin_perfil}`"

                alerta_vencimiento = verificar_alerta_vencimiento(vencimiento, estado)
                if "Vencida" in alerta_vencimiento or "Vence" in alerta_vencimiento or estado.lower() != "activo":
                    tiene_por_renovar = True

                bloques.append(
                    f"🔹 *Suscripción #{idx} ({servicio})*\n"
                    f"• *Correo:* {correo_mostrar}\n"
                    f"• *Perfil:* {pantalla}\n"
                    f"• *PIN de seguridad:* {pin_mostrar} 🔒\n"
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
            if safe_get(s, "Estado", "").lower() == "activo" and "pendiente" not in safe_get(s, "Cuenta", "").lower()
        ]
        if not suscripciones_activas:
            enviar_mensaje_callback(chat_id, "⚠️ No tienes pantallas activas.", get_back_keyboard())
            return

        botones_selector = []
        for sub in suscripciones_activas:
            r_idx = sub.get("_row_index")
            srv = safe_get(sub, "Servicio", "Disney+")
            pnt = safe_get(sub, "Pantalla", "Perfil 1")
            cta = safe_get(sub, "Cuenta", "Cuenta")
            botones_selector.append([{"text": f"✏️ {srv} - {pnt} ({cta})", "callback_data": f"renombrar_perfil_{r_idx}"}])

        botones_selector.append([{"text": "🔙 Volver", "callback_data": "ver_datos"}])
        mensaje = "✏️ *PERSONALIZAR NOMBRE*\nSelecciona la pantalla:"
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, {"inline_keyboard": botones_selector})
        else:
            enviar_mensaje_callback(chat_id, mensaje, {"inline_keyboard": botones_selector})
        return

    elif accion.startswith("renombrar_perfil_"):
        try:
            row_idx_renombrar = int(accion.split("_")[-1])
            esperando_nuevo_nombre_perfil[str_chat_id] = row_idx_renombrar
            mensaje_peticion = "✏️ *ESCRIBE TU NUEVO NOMBRE* (Ej: *Papá*):"
            teclado_canc = {"inline_keyboard": [[{"text": "🔙 Cancelar", "callback_data": "menu_renombrar"}]]}
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje_peticion, teclado_canc)
            else:
                enviar_mensaje_callback(chat_id, mensaje_peticion, teclado_canc)
        except Exception:
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error.", get_back_keyboard())
        return

    elif accion == "obtener_codigo" or "codigo" in accion:
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

        if not verificar_cliente_activo(chat_id):
            registrar_intento_sospechoso_otp(chat_id, nombre, username, enviar_mensaje_callback)
            mensaje = "🔒 *ACCESO RESTRINGIDO*\nDebes tener una pantalla activa."
            teclado = get_datos_keyboard(mostrar_renovar=True)
            if es_callback and editar_mensaje_callback:
                editar_mensaje_callback(chat_id, message_id, mensaje, teclado)
            else:
                enviar_mensaje_callback(chat_id, mensaje, teclado)
            return

        suscripciones_activas = [
            s for s in obtener_suscripciones_por_id(chat_id)
            if safe_get(s, "Estado", "").lower() == "activo" and "pendiente" not in safe_get(s, "Cuenta", "").lower() and safe_get(s, "Cuenta", "").lower() not in ("", "por asignar")
        ]

        if len(suscripciones_activas) > 1 and not accion.startswith("pedir_otp_"):
            botones_selector = []
            for idx, sub in enumerate(suscripciones_activas):
                srv = safe_get(sub, "Servicio", "Disney+")
                cta = safe_get(sub, "Cuenta", "Cuenta")
                pnt = safe_get(sub, "Pantalla", "Perfil 1")
                botones_selector.append([{"text": f"📺 {srv} - {pnt} ({cta})", "callback_data": f"pedir_otp_{idx}"}])
            botones_selector.append([{"text": "🔙 Volver", "callback_data": "menu_principal"}])
            mensaje = "📺 Tienes varias pantallas. *¿Para cuál deseas solicitar el código?*:"
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
                if safe_get(s, "Estado", "").lower() == "activo" and "pendiente" not in safe_get(s, "Cuenta", "").lower()
            ]
            servicio_seleccionado = safe_get(suscripciones_activas[idx_sub], "Servicio", "Disney").lower() if idx_sub < len(suscripciones_activas) else "disney"
            ejecutar_busqueda_otp(chat_id, str_chat_id, servicio_seleccionado, message_id, enviar_mensaje_callback, editar_mensaje_callback, es_callback)
        except Exception:
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error.", get_back_keyboard())

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
            mensaje = "🔄 Tienes múltiples pantallas. *¿Cuál deseas renovar?*:"
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
        except Exception:
            enviar_mensaje_callback(chat_id, "⚠️ Ocurrió un error.", get_back_keyboard())

    elif accion == "comprar_extra":
        if str_chat_id in esperando_captura_pago:
            row_huerta = esperando_captura_pago.pop(str_chat_id)
            limpiar_fila_cancelada(row_huerta)

        mensaje = f"🛒 *SELECCIONA EL SERVICIO*\n• Disney+: `${PRECIO_DISNEY_USD:.2f}`\n• Netflix: `${PRECIO_NETFLIX_USD:.2f}`"
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

        texto_wa = f"Hola, necesito soporte. Mi ID es: {str_chat_id}."
        url_whatsapp = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_wa.replace(' ', '%20')}"
        teclado_whatsapp = {
            "inline_keyboard": [
                [{"text": "💬 Soporte WhatsApp", "url": url_whatsapp}],
                [{"text": "🔙 Volver", "callback_data": "menu_principal"}]
            ]
        }
        mensaje = "💬 *ATENCIÓN AL CLIENTE*\nComunícate por WhatsApp:"
        if es_callback and editar_mensaje_callback:
            editar_mensaje_callback(chat_id, message_id, mensaje, teclado_whatsapp)
        else:
            enviar_mensaje_callback(chat_id, mensaje, teclado_whatsapp)

    else:
        enviar_mensaje_callback(chat_id, "¡Hola! Selecciona una opción:", get_main_menu_keyboard())


# ==========================================
# FUNCIONES AUXILIARES DE GESTIÓN Y PINS
# ==========================================
def obtener_cuentas_con_cupos_libres(servicio_solicitado):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        sheet_cuentas = spreadsheet.worksheet("Cuentas")
        registros_cuentas = sheet_cuentas.get_all_records()
        
        libres = []
        for c in registros_cuentas:
            srv = safe_get(c, "Servicio", "").lower()
            est = safe_get(c, "Estado", "").lower()
            if servicio_solicitado.lower() in srv and est == "activa":
                try:
                    limite_def = 5 if "netflix" in srv else 7
                    cap = int(safe_get(c, "Capacidad Total", str(limite_def)))
                    ocu = int(safe_get(c, "Perfiles Ocupados", "0"))
                except ValueError:
                    cap = 5
                    ocu = 0
                if ocu < cap:
                    libres.append(safe_get(c, "Correo (Usuario)", safe_get(c, "Correo", "")))
        return libres
    except Exception:
        return []


def obtener_perfiles_libres_especificos(sheet_principal, servicio_solicitado, correo_cuenta):
    """Analiza qué perfiles (Perfil 1, Perfil 2, etc.) están libres en esa cuenta específica."""
    try:
        es_netflix = "netflix" in servicio_solicitado.lower()
        limite_maximo = 5 if es_netflix else 7

        registros = sheet_principal.get_all_records()
        perfiles_ocupados = set()

        for r in registros:
            srv = safe_get(r, "Servicio", "").lower()
            cta = safe_get(r, "Cuenta", "").lower()
            pnt = safe_get(r, "Pantalla", "").lower()
            
            if servicio_solicitado.lower() in srv and cta == correo_cuenta.lower():
                for num in range(1, limite_maximo + 1):
                    if f"perfil {num}" in pnt:
                        perfiles_ocupados.add(f"Perfil {num}")

        libres = []
        for num in range(1, limite_maximo + 1):
            p_nombre = f"Perfil {num}"
            if p_nombre not in perfiles_ocupados:
                libres.append(p_nombre)
        return libres
    except Exception:
        return ["Perfil 1"]


def liberar_cupo_cuenta_maestra(sheet_cuentas, correo_cuenta):
    try:
        registros = sheet_cuentas.get_all_records()
        for idx, c in enumerate(registros, start=2):
            correo_c = safe_get(c, "Correo (Usuario)", safe_get(c, "Correo", ""))
            if correo_c.lower() == correo_cuenta.lower():
                try:
                    ocu = int(safe_get(c, "Perfiles Ocupados", "1"))
                except ValueError:
                    ocu = 1
                nuevos_ocu = max(0, ocu - 1)
                sheet_cuentas.update_cell(idx, 5, nuevos_ocu)
                if safe_get(c, "Estado", "").lower() == "llena":
                    sheet_cuentas.update_cell(idx, 6, "Activa")
                break
    except Exception as e:
        print(f"Error liberando cupo: {e}")


def ocupar_cuenta_maestra_especifica(sheet_cuentas, correo_destino):
    try:
        registros = sheet_cuentas.get_all_records()
        for idx_c, c in enumerate(registros, start=2):
            correo_c = safe_get(c, "Correo (Usuario)", safe_get(c, "Correo", ""))
            if correo_c.lower() == correo_destino.lower():
                try:
                    ocu = int(safe_get(c, "Perfiles Ocupados", "0"))
                    cap = int(safe_get(c, "Capacidad Total", "5"))
                except ValueError:
                    ocu = 0
                    cap = 5
                
                nuevos_ocu = ocu + 1
                sheet_cuentas.update_cell(idx_c, 5, nuevos_ocu)
                if nuevos_ocu >= cap:
                    sheet_cuentas.update_cell(idx_c, 6, "Llena")
                break
    except Exception as e:
        print(f"Error ocupando cuenta: {e}")


def obtener_pin_asignado_cliente(correo_cuenta, nombre_perfil):
    if not correo_cuenta or "pendiente" in correo_cuenta.lower() or "asignar" in correo_cuenta.lower():
        return "N/A"
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        sheet_cuentas = spreadsheet.worksheet("Cuentas")
        registros = sheet_cuentas.get_all_records()

        num_perfil_limpio = "Perfil 1"
        for n in range(1, 10):
            if f"perfil {n}" in str(nombre_perfil).lower():
                num_perfil_limpio = f"Perfil {n}"
                break

        for c in registros:
            correo_c = safe_get(c, "Correo (Usuario)", safe_get(c, "Correo", ""))
            if correo_c.lower() == correo_cuenta.lower():
                pins_texto = safe_get(c, "PINs de Perfiles", "")
                for parte in pins_texto.split("|"):
                    if num_perfil_limpio.lower() in parte.lower():
                        if ":" in parte:
                            return parte.split(":")[-1].strip()
                return pins_texto if pins_texto else "Sin PIN"
        return "No registrado"
    except Exception as e:
        print(f"Error consultando PIN: {e}")
        return "S/N"


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
    except Exception:
        return "Perfil 1"


def asignar_correo_desde_stock(sheet_principal, servicio_solicitado, chat_id="", nombre_cliente="", enviar_mensaje_callback=None):
    try:
        spreadsheet = sheet_principal.spreadsheet
        sheet_cuentas = spreadsheet.worksheet("Cuentas")
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
                    sheet_cuentas.update_cell(idx_c, 5, ocupados + 1)
                    if (ocupados + 1) >= capacidad:
                        sheet_cuentas.update_cell(idx_c, 6, "Llena")
                    return correo_encontrado
        return "⚠️ Pendiente de Stock"
    except Exception:
        return "Por Asignar"


def procesar_asignacion_stock_masivo(enviar_msg_cb):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        sheet_cuentas = spreadsheet.worksheet("Cuentas")
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
                    ocupados_actuales = int(fila_c_actual[4]) if len(fila_c_actual) > 4 and fila_c_actual[4].isdigit() else 0
                    sheet_cuentas.update_cell(idx_cuenta_encontrada, 5, ocupados_actuales + 1)
                    
                    limite_defecto = 5 if "netflix" in servicio_cli.lower() else 7
                    capacidad_total = int(fila_c_actual[3]) if len(fila_c_actual) > 3 and fila_c_actual[3].isdigit() else limite_defecto
                    if (ocupados_actuales + 1) >= capacidad_total:
                        sheet_cuentas.update_cell(idx_cuenta_encontrada, 6, "Llena")

                    if tid_cliente and enviar_msg_cb and estado_cli == "activo":
                        try:
                            primer_nombre = nombre_cliente.split()[0] if nombre_cliente else "Cliente"
                            pin_asignado = obtener_pin_asignado_cliente(cuenta_encontrada, perfil_correcto)
                            mensaje_notif = (
                                f"🎉 *¡EXCELENTE NOTICIA, {primer_nombre}!*\n\n"
                                f"Tu cuenta de *{servicio_cli}* ya ha sido asignada.\n"
                                f"• *Correo:* `{cuenta_encontrada}`\n"
                                f"• *Perfil:* `{perfil_correcto}`\n"
                                f"• *PIN:* `{pin_asignado}` 🔒"
                            )
                            enviar_msg_cb(int(tid_cliente), mensaje_notif, get_main_menu_keyboard())
                        except Exception:
                            pass

                    asignados_count += 1
                    registros_cuentas = sheet_cuentas.get_all_records()

        if asignados_count > 0:
            return f"✅ Se han asignado cuentas a **{asignados_count}** cliente(s) en espera."
        else:
            return "ℹ️ No hay clientes pendientes de stock o cuentas con cupo."
    except Exception as e:
        return f"❌ Error: {e}"


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
    except Exception:
        return []


def crear_nueva_fila_pendiente(str_chat_id, nombre, username="", servicio="Disney", enviar_mensaje_cb=None):
    try:
        sheet = conectar_sheets()
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        correo_asignado = asignar_correo_desde_stock(sheet, servicio, str_chat_id, nombre_completo, enviar_mensaje_cb)
        perfil_asignado = obtener_primer_perfil_disponible(sheet, servicio, correo_asignado)
        sheet.append_row([str(str_chat_id), nombre_completo, correo_asignado, perfil_asignado, "", "Pendiente Pago", servicio])
        return len(sheet.get_all_records()) + 1
    except Exception:
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
            if "pendiente" in safe_get(row, "Estado", "").lower():
                pendientes.append((len(pendientes)+1, idx, row))
        return pendientes
    except Exception:
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
    except Exception:
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
    except Exception:
        return []


def liberar_y_eliminar_fila_suscripcion(row_idx):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        sheet_cuentas = spreadsheet.worksheet("Cuentas")
        fila_datos = sheet_principal.row_values(row_idx)
        if len(fila_datos) < 3:
            return "❌ Fila no válida."

        correo_a_liberar = safe_get({"Cuenta": fila_datos[2]}, "Cuenta", "")
        if correo_a_liberar and "pendiente de stock" not in correo_a_liberar.lower():
            liberar_cupo_cuenta_maestra(sheet_cuentas, correo_a_liberar)

        sheet_principal.delete_rows(row_idx)
        return f"✅ ¡Suscripción de la fila {row_idx} eliminada y cupo liberado!"
    except Exception as e:
        return f"❌ Error: {e}"


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
    except Exception:
        return False, None, False, "", "Disney+", "Perfil 1", "Renovación", "Por Asignar"


def registrar_venta_en_historial(nombre_cliente, tid_cliente, servicio, perfil, monto_usd, tipo_operacion, metodo_pago):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        encabezados_esperados = ["Fecha y Hora", "Cliente", "Telegram ID", "Servicio", "Perfil Asignado", "Monto USD", "Tipo", "Método Pago"]
        try:
            sheet_ventas = spreadsheet.worksheet("Ventas")
            if len(sheet_ventas.row_values(1)) < 8:
                sheet_ventas.update("A1:H1", [encabezados_esperados])
        except Exception:
            sheet_ventas = spreadsheet.add_worksheet(title="Ventas", rows="1000", cols="8")
            sheet_ventas.append_row(encabezados_esperados)

        fecha_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet_ventas.append_row([fecha_hora, str(nombre_cliente), str(tid_cliente), str(servicio), str(perfil), f"${float(monto_usd):.2f}", str(tipo_operacion), str(metodo_pago)])
    except Exception as e:
        print(f"Error registrando venta: {e}")


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
            f"🟢 *Activas:* {activos}\n"
            f"🟡 *Pagos pendientes:* {pendientes}\n"
            f"🔴 *Vencidas por depurar:* {vencidos_total}\n"
            f"⏳ *En espera de stock:* {en_espera_stock}"
        )
    except Exception as e:
        return f"❌ Error: {e}"


def generar_resumen_completo_negocio():
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
            for v in sheet_ventas.get_all_records():
                monto_str = safe_get(v, "Monto USD", "0").replace("$", "").strip()
                try:
                    total_ingresos_usd += float(monto_str)
                except ValueError:
                    pass
            ventas_totales_count = len(sheet_ventas.get_all_records())
        except Exception:
            pass

        cupos_disponibles = max(0, capacidad_total_perfiles - perfiles_totales_ocupados)
        return (
            "📈 *RESUMEN GENERAL DEL NEGOCIO* 📈\n\n"
            f"👤 Clientes únicos: `{clientes_unicos}`\n"
            f"📺 Pantallas alquiladas: `{total_pantallas}` (🟢 Activas: `{activas_cli}`)\n"
            f"• Netflix: `{netflix_cli}` | Disney+: `{disney_cli}`\n\n"
            f"📦 Cuentas maestras: `{total_cuentas_maestras}` (🟢 Activas: `{cuentas_activas_stock}`)\n"
            f"• Perfiles ocupados: `{perfiles_totales_ocupados} / {capacidad_total_perfiles}`\n"
            f"• Cupos libres: `{cupos_disponibles}` | En espera: `{en_espera_stock}`\n\n"
            f"💰 Ventas: `{ventas_totales_count}` | Ingresos: *`${total_ingresos_usd:.2f} USD`*\n"
            f"• Pagos pendientes: `{pendientes_pago}`"
        )
    except Exception as e:
        return f"❌ Error: {e}"


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
            mensaje = f"⏳ *LÍMITE ALCANZADO*\nEspera *{restante // 60}m {restante % 60}s*."
            if es_cb and editar_cb:
                editar_cb(chat_id, message_id, mensaje, get_back_keyboard())
            else:
                enviar_cb(chat_id, mensaje, get_back_keyboard())
            return

    datos_usuario["intentos"] += 1
    datos_usuario["ultimo_tiempo"] = ahora
    es_netflix = "netflix" in servicio
    nombre_plataforma = "Netflix" if es_netflix else "Disney+"

    msg_espera = f"🔍 Buscando código reciente en *{nombre_plataforma}*..."
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, msg_espera, get_back_keyboard())
    else:
        enviar_cb(chat_id, msg_espera)

    codigo = obtener_ultimo_codigo_netflix() if es_netflix else obtener_ultimo_codigo_disney()
    mensaje = f"🔑 *Tu código de {nombre_plataforma}:*\n\n`{codigo}`" if codigo else f"⚠️ No se encontró código reciente de *{nombre_plataforma}*."
    
    if es_cb and editar_cb:
        editar_cb(chat_id, message_id, mensaje, get_back_keyboard())
    else:
        enviar_cb(chat_id, mensaje, get_back_keyboard())


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

    if ADMIN_ID and enviar_foto_callback:
        texto_admin = (
            "🔔 *¡NUEVO REPORTE DE PAGO (TEXTO)!*\n\n"
            f"• *Cliente:* {nombre} (@{username}) (`{str_chat_id}`)\n"
            f"• *Servicio:* {servicio_asociado} ({pantalla_asociada})\n"
            f"• *Referencia:* `{texto}`"
        )
        teclado_admin = {
            "inline_keyboard": [
                [{"text": "✅ Aprobar y Activar", "callback_data": f"aprobar_{row_idx_pendiente}_digital"}],
                [{"text": "❌ Rechazar", "callback_data": f"rechazar_{row_idx_pendiente}"}]
            ]
        }
        enviar_foto_callback(int(ADMIN_ID), None, texto_admin, teclado_admin)

    enviar_cb(chat_id, "✅ Reporte enviado al administrador con éxito.", get_main_menu_keyboard())


def registrar_intento_sospechoso_otp(chat_id, nombre, username, enviar_mensaje_cb):
    str_chat_id = str(chat_id).strip()
    ahora = time.time()
    if "intentos_anormales" not in control_intentos_otp:
        control_intentos_otp["intentos_anormales"] = {}
    if str_chat_id not in control_intentos_otp["intentos_anormales"]:
        control_intentos_otp["intentos_anormales"][str_chat_id] = {"contador": 0, "primer_intento": ahora}
        
    registro = control_intentos_otp["intentos_anormales"][str_chat_id]
    if ahora - registro["primer_intento"] > 3600:
        registro["contador"] = 0
        registro["primer_intento"] = ahora
    registro["contador"] += 1
    
    if registro["contador"] >= 3 and ADMIN_ID and enviar_mensaje_cb:
        nombre_completo = f"{nombre} (@{username})" if username else nombre
        alerta_anomalia = (
            "🚨 *¡ALERTA DE COMPORTAMIENTO SOSPECHOSO!* 🚨\n\n"
            f"• *Usuario:* {nombre_completo} (`{str_chat_id}`)\n"
            "• *Incidente:* Múltiples solicitudes de códigos OTP sin suscripción activa."
        )
        try:
            enviar_mensaje_cb(int(ADMIN_ID), alerta_anomalia)
            registro["contador"] = 0
        except Exception:
            pass


def limpiar_fila_cancelada(row_idx):
    try:
        sheet_principal = conectar_sheets()
        spreadsheet = sheet_principal.spreadsheet
        fila_datos = sheet_principal.row_values(row_idx)
        if len(fila_datos) < 3:
            return
        estado_actual = safe_get({"Estado": fila_datos[5] if len(fila_datos) > 5 else ""}, "Estado", "").lower()
        if "pendiente" in estado_actual or estado_actual == "":
            correo_a_liberar = safe_get({"Cuenta": fila_datos[2]}, "Cuenta", "")
            if correo_a_liberar and "pendiente de stock" not in correo_a_liberar.lower():
                sheet_cuentas = spreadsheet.worksheet("Cuentas")
                liberar_cupo_cuenta_maestra(sheet_cuentas, correo_a_liberar)
            sheet_principal.delete_rows(row_idx)
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
        mensaje_cliente = (
            "💵 *PAGO EN EFECTIVO REGISTRADO*\n\n"
            f"• *Servicio:* {servicio_elegido} ({perfil_asignado})\n"
            f"• *Monto:* `${precio_usd:.2f} USD`\n\n"
            "👤 Entrega el efectivo al encargado del local para su verificación y activación."
        )
        if es_cb and editar_cb:
            editar_cb(chat_id, message_id, mensaje_cliente, get_back_keyboard())
        else:
            enviar_cb(chat_id, mensaje_cliente, get_back_keyboard())

        if ADMIN_ID:
            texto_admin = (
                "🔔 *¡NUEVO PAGO EN EFECTIVO!* 🔔\n\n"
                f"• *Cliente:* {nombre} (@{username}) (`{str_chat_id}`)\n"
                f"• *Servicio:* {servicio_elegido} ({perfil_asignado})"
            )
            teclado_admin = {
                "inline_keyboard": [
                    [{"text": "✅ Aprobar Efectivo", "callback_data": f"aprobar_{row_idx_target}_efectivo"}],
                    [{"text": "❌ Rechazar", "callback_data": f"rechazar_{row_idx_target}"}]
                ]
            }
            enviar_cb(int(ADMIN_ID), texto_admin, teclado_admin)
    except Exception:
        enviar_cb(chat_id, "⚠️ Ocurrió un error registrando el efectivo.", get_back_keyboard())


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
    except Exception:
        pass

    tasa_usdt = obtener_tasa_usdt_hoy()
    monto_bs = round(precio_usd * tasa_usdt, 2)
    texto_soporte = f"Hola, necesito asistencia con mi servicio. Mi ID es: {str_chat_id}."
    url_whatsapp_soporte = f"https://wa.me/{WHATSAPP_NUMERO}?text={texto_soporte.replace(' ', '%20')}"

    aviso_stock = "⏳ *En lista de espera prioritaria (Stock en curso)*\n\n" if sin_stock else ""
    mensaje = (
        f"💳 *DATOS DE PAGO — {servicio_elegido.upper()}*\n\n"
        f"{aviso_stock}"
        f"💵 *Monto:* `{precio_usd:.2f} USDT` ({monto_bs} Bs a tasa {tasa_usdt})\n\n"
        f"📲 *Pago Móvil:*\n"
        f"• Banco: {PAGO_MOVIL_BANCO}\n"
        f"• Cédula: `{PAGO_MOVIL_CEDULA}`\n"
        f"• Teléfono: `{PAGO_MOVIL_TELEFONO}`\n\n"
        "📸 *PASO FINAL:* Realiza el pago y **envía tu comprobante por este chat**."
    )
    teclado_pago = {
        "inline_keyboard": [
            [{"text": "💬 Soporte WhatsApp", "url": url_whatsapp_soporte}],
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
        requests.post(url, json={"chat_id": chat_id, "message_id": message_id, "reply_markup": {"inline_keyboard": []}}, timeout=3)
    except Exception:
        pass


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
