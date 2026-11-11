import os
import requests
from fastapi import FastAPI, Request
from datetime import datetime

# Importamos las funciones de los módulos auxiliares
from sheets_db import (
    registrar_en_cola_pagos,
    aprobar_pago_por_administrador,
    procesar_pago_efectivo_admin,
    revisar_y_notificar_vencimientos,
    liberar_perfiles_vencidos,
    obtener_mi_suscripcion
)
from gmail_otp import obtener_ultimo_codigo_disney

app = FastAPI()

# Variables de Entorno (Se configuran en Render)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "TU_BOT_TOKEN_AQUI")
ADMIN_TELEGRAM_ID = os.getenv("ADMIN_TELEGRAM_ID", "123456789")
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ==========================================
# FUNCIONES AUXILIARES DE TELEGRAM
# ==========================================

def enviar_mensaje(chat_id: str, texto: str):
    """Envía un mensaje formateado en Markdown a Telegram."""
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown"
    }
    requests.post(f"{TELEGRAM_URL}/sendMessage", json=payload)

def enviar_mensaje_con_botones(chat_id: str, texto: str, teclado: dict):
    """Envía un mensaje con Inline Keyboards a Telegram."""
    payload = {
        "chat_id": chat_id,
        "text": texto,
        "parse_mode": "Markdown",
        "reply_markup": teclado
    }
    requests.post(f"{TELEGRAM_URL}/sendMessage", json=payload)

# ==========================================
# MENÚS INTERACTIVOS (INLINE KEYBOARDS)
# ==========================================

teclado_inicio = {
    "inline_keyboard": [
        [
            {"text": "🛒 Comprar (Pago Móvil)", "callback_data": "metodo_pagomovil"},
            {"text": "🟡 Comprar (Binance Pay)", "callback_data": "metodo_binance"}
        ],
        [
            {"text": "🔑 Solicitar Código OTP", "callback_data": "pedir_codigo"},
            {"text": "📊 Mi Suscripción", "callback_data": "mi_cuenta"}
        ],
        [
            {
                "text": "💬 Soporte por WhatsApp",
                "url": "https://wa.me/584247091547?text=Hola,%20necesito%20soporte%20con%20mi%20cuenta%20de%20Disney"
            }
        ]
    ]
}

teclado_comprobante_pagomovil = {
    "inline_keyboard": [
        [
            {
                "text": "📤 Enviar Comprobante por WhatsApp",
                "url": "https://wa.me/584247091547?text=Hola,%20acabo%20de%20realizar%20mi%20Pago%20M%C3%B3vil.%20Aqu%C3%AD%20adjunto%20el%20comprobante:"
            }
        ],
        [{"text": "🔙 Volver al Menú", "callback_data": "menu_principal"}]
    ]
}

# ==========================================
# WEBHOOK PRINCIPAL DE TELEGRAM
# ==========================================

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    
    # --------------------------------------
    # 1. ATENCIÓN DE CALLBACK QUERIES (BOTONES)
    # --------------------------------------
    if "callback_query" in data:
        callback = data["callback_query"]
        usuario_id = str(callback["from"]["id"])
        callback_id = callback["id"]
        accion = callback["data"]
        chat_id = str(callback["message"]["chat"]["id"])
        
        # Agradecer callback para quitar animación de carga
        requests.post(f"{TELEGRAM_URL}/answerCallbackQuery", json={"callback_query_id": callback_id})
        
        if accion == "menu_principal":
            enviar_mensaje_con_botones(chat_id, "📌 *Menú Principal:* Selecciona una opción:", teclado_inicio)
            
        elif accion == "metodo_pagomovil":
            msg = (
                "📱 *Datos para Pago Móvil:*\n\n"
                "• *Banco:* Banco Provincial / Bancamiga\n"
                "• *Teléfono:* `04247091547`\n"
                "• *Cédula:* `V-XXXXXXXX` (Tu cédula)\n\n"
                "📌 *Instrucciones:* Una vez realizado el pago, reporta tu referencia ejecutando:\n"
                "`/pagomovil [Referencia] [Monto]`\n"
                "_(Ejemplo: `/pagomovil 4859 150`)_\n\n"
                "O si lo prefieres, envía directamente tu comprobante a nuestro WhatsApp:"
            )
            enviar_mensaje_con_botones(chat_id, msg, teclado_comprobante_pagomovil)
            
        elif accion == "metodo_binance":
            msg = (
                "🟡 *Datos para Binance Pay:*\n\n"
                "• *Pay ID / Correo:* `tucorreo@binance.com`\n\n"
                "📌 *Instrucciones:* Después de pagar, reporta el ID de transacción escribiendo:\n"
                "`/binance [ID_Transaccion] [Monto]`\n"
                "_(Ejemplo: `/binance 987654321 5.00`)_"
            )
            enviar_mensaje(chat_id, msg)
            
        elif accion == "pedir_codigo":
            enviar_mensaje(chat_id, "🔍 *Buscando código OTP reciente en Gmail...* Por favor espera un momento.")
            codigo = obtener_ultimo_codigo_disney()
            if codigo:
                enviar_mensaje(chat_id, f"🔑 *Tu código de Disney+ es:* `{codigo}`\n\n_(Cópialo e ingrésalo en tu pantalla)_")
            else:
                enviar_mensaje(chat_id, "⚠️ No se encontró ningún código reciente. Intenta solicitar el código en la pantalla de Disney e inténtalo de nuevo.")
                
        elif accion == "mi_cuenta":
            info = obtener_mi_suscripcion(chat_id)
            enviar_mensaje(chat_id, info)
            
        elif accion.startswith("aprobar_"):
            # 🔒 VALIDACIÓN DE SEGURIDAD PARA EL ADMIN
            if usuario_id != ADMIN_TELEGRAM_ID:
                requests.post(f"{TELEGRAM_URL}/answerCallbackQuery", json={
                    "callback_query_id": callback_id,
                    "text": "❌ Acción reservada para el Administrador.",
                    "show_alert": True
                })
                return {"status": "ok"}
                
            referencia = accion.replace("aprobar_", "")
            resultado = aprobar_pago_por_administrador(referencia)
            
            if resultado["status"] == "success":
                msg_id = callback["message"]["message_id"]
                texto_orig = callback["message"]["text"]
                nuevo_texto = f"{texto_orig}\n\n🟢 *ESTADO: APROBADO Y ENTREGADO EXITOSAMENTE* ✅"
                
                requests.post(f"{TELEGRAM_URL}/editMessageText", json={
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": nuevo_texto,
                    "parse_mode": "Markdown"
                })
            else:
                enviar_mensaje(ADMIN_TELEGRAM_ID, f"⚠️ Error aprobando pago: {resultado['mensaje']}")
                
        return {"status": "ok"}

    # --------------------------------------
    # 2. ATENCIÓN DE MENSAJES DE TEXTO
    # --------------------------------------
    if "message" in data:
        msg = data["message"]
        chat_id = str(msg["chat"]["id"])
        text = msg.get("text", "")
        text_lower = text.lower().strip()
        nombre_cliente = msg["from"].get("first_name", "Cliente")
        
        # COMANDO /start
        if text_lower == "/start":
            bienvenida = (
                f"👋 *¡Hola {nombre_cliente}! bienvenido al Bot de Disney+.*\n\n"
                "Aquí puedes adquirir tus pantallas, consultar tu estado de suscripción y solicitar tus códigos de acceso de forma rápida."
            )
            enviar_mensaje_con_botones(chat_id, bienvenida, teclado_inicio)
            return {"status": "ok"}

        # COMANDO /pagomovil [Referencia] [Monto]
        elif text_lower.startswith("/pagomovil"):
            partes = text.split(" ")
            if len(partes) < 3:
                enviar_mensaje(chat_id, "⚠️ *Formato incorrecto.*\nUsa: `/pagomovil [Referencia] [Monto]`\n_Ejemplo: `/pagomovil 4859 150`_")
                return {"status": "ok"}
                
            ref, monto = partes[1], partes[2]
            registrado = registrar_en_cola_pagos(chat_id, nombre_cliente, "Pago Móvil", ref, monto)
            
            if registrado:
                enviar_mensaje(chat_id, f"⏳ *Pago reportado.* Referencia: `{ref}`.\nEl administrador lo verificará en breve.")
                
                # Alerta privada con botón interactivo para el Admin
                teclado_admin = {
                    "inline_keyboard": [[{"text": "✅ Aprobar y Entregar Cuenta", "callback_data": f"aprobar_{ref}"}]]
                }
                msg_admin = (
                    "🔔 *¡Nuevo Pago Móvil pendiente!* 💰\n\n"
                    f"👤 *Cliente:* `{nombre_cliente}` (ID: `{chat_id}`)\n"
                    f"🔢 *Referencia:* `{ref}` | *Monto:* `{monto}`\n\n"
                    "Verifica la transacción y presiona el botón:"
                )
                enviar_mensaje_con_botones(ADMIN_TELEGRAM_ID, msg_admin, teclado_admin)
            else:
                enviar_mensaje(chat_id, "⚠️ Error al registrar tu pago. Inténtalo de nuevo o contacta al soporte por WhatsApp.")
            return {"status": "ok"}

        # COMANDO EXCLUSIVO ADMIN /efectivo [Chat_ID] [Monto]
        elif text_lower.startswith("/efectivo"):
            if chat_id != ADMIN_TELEGRAM_ID:
                enviar_mensaje(chat_id, "❌ No tienes permisos para ejecutar este comando.")
                return {"status": "ok"}
                
            partes = text.split(" ")
            if len(partes) < 3:
                enviar_mensaje(chat_id, "⚠️ *Formato incorrecto.*\nUsa: `/efectivo [Chat_ID_Cliente] [Monto]`")
                return {"status": "ok"}
                
            target_chat_id, monto = partes[1], partes[2]
            resultado = procesar_pago_efectivo_admin(target_chat_id, monto)
            enviar_mensaje(ADMIN_TELEGRAM_ID, resultado["mensaje"])
            return {"status": "ok"}

    return {"status": "ok"}

# ==========================================
# ENDPOINT DE MANTENIMIENTO DIARIO (CRON-JOB)
# ==========================================

@app.get("/ejecutar-mantenimiento-diario")
async def endpoint_mantenimiento():
    """Ejecutado automáticamente una vez al día por Cron-job.org"""
    res_avisos = revisar_y_notificar_vencimientos()
    res_liberacion = liberar_perfiles_vencidos()
    return {
        "status": "ok",
        "avisos_enviados": res_avisos,
        "perfiles_liberados": res_liberacion
    }
