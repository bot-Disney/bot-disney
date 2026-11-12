import datetime
from sheets_db import conectar_sheets

# Almacén temporal en memoria para evitar enviar varias alertas el mismo día al mismo usuario
_clientes_notificados_hoy = {"fecha": "", "ids": set()}

def revisar_y_enviar_alertas_vencimiento(enviar_mensaje_fn):
    """
    Revisa la hoja de Google Sheets y envía alertas automáticas 
    a los clientes cuyos servicios estén próximos a vencer (3 días, 1 día o vencidos).
    """
    try:
        sheet = conectar_sheets()
        registros = sheet.get_all_records()
        hoy = datetime.date.today()
        
        global _clientes_notificados_hoy
        fecha_hoy_str = hoy.strftime("%Y-%m-%d")
        
        # Reiniciar el registro de notificados si cambió el día
        if _clientes_notificados_hoy.get("fecha") != fecha_hoy_str:
            _clientes_notificados_hoy = {"fecha": fecha_hoy_str, "ids": set()}

        for idx, sub in enumerate(registros, start=2):
            telegram_id = str(sub.get("Telegram_ID", "")).strip()
            estado = str(sub.get("Estado", "")).strip().lower()
            vencimiento_str = str(sub.get("Vencimiento", "")).strip()
            servicio = str(sub.get("Servicio", "Streaming")).strip()
            cuenta = str(sub.get("Cuenta", "")).strip()

            # Validar que sea un cliente activo con ID y fecha de vencimiento válida
            if not telegram_id or telegram_id == "Por Asignar" or estado != "activo" or not vencimiento_str:
                continue

            # Identificador único para evitar spam al mismo cliente por la misma cuenta hoy
            clave_notificacion = f"{telegram_id}_{cuenta}_{vencimiento_str}"
            if clave_notificacion in _clientes_notificados_hoy["ids"]:
                continue

            # Intentar parsear la fecha de vencimiento soportando varios formatos comunes
            fecha_venc = None
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    fecha_venc = datetime.datetime.strptime(vencimiento_str, fmt).date()
                    break
                except ValueError:
                    continue

            if not fecha_venc:
                continue

            dias_restantes = (fecha_venc - hoy).days
            mensaje_alerta = None
            
            # Definir el tono del mensaje según los días restantes
            if dias_restantes == 3:
                mensaje_alerta = (
                    f"⚠️ *AVISO DE VENCIMIENTO*\n\n"
                    f"Hola 👋 Te recordamos que tu pantalla de *{servicio}* (Cuenta: `{cuenta}`) "
                    f"vence en *3 días* ({vencimiento_str}).\n\n"
                    f"Renueva a tiempo para que no pierdas tu acceso ni tus configuraciones."
                )
            elif dias_restantes == 1:
                mensaje_alerta = (
                    f"🟠 *¡ATENCIÓN! TU CUENTA VENCE MAÑANA*\n\n"
                    f"Tu pantalla de *{servicio}* está a punto de expirar mañana (*{vencimiento_str}*).\n\n"
                    f"Realiza tu pago y envía tu comprobante por el bot para mantener tu servicio activo sin interrupciones."
                )
            elif dias_restantes == 0:
                mensaje_alerta = (
                    f"🔴 *TU SERVICIO HA VENCIDO HOY*\n\n"
                    f"Tu pantalla de *{servicio}* ha expirado el día de hoy.\n\n"
                    f"Envía tu comprobante de renovación por el bot para reactivarla de inmediato."
                )

            # Si hay una alerta aplicable, se envía y se marca como notificada hoy
            if mensaje_alerta:
                try:
                    teclado_renovacion = {
                        "inline_keyboard": [
                            [{"text": "🔄 Renovar (+30 días)", "callback_data": "renovar_suscripcion"}],
                            [{"text": "🔙 Menú Principal", "callback_data": "menu_principal"}]
                        ]
                    }
                    enviar_mensaje_fn(int(telegram_id), mensaje_alerta, teclado_renovacion)
                    _clientes_notificados_hoy["ids"].add(clave_notificacion)
                    print(f"Alerta de {dias_restantes} días enviada con éxito al Telegram ID: {telegram_id}")
                except Exception as e:
                    print(f"No se pudo enviar la alerta al usuario {telegram_id}: {e}")

    except Exception as e:
        print(f"Error general en la revisión de alertas automáticas: {e}")
