from flask import Flask, jsonify, request
import json
from config import executor, log, VERIFY_TOKEN, NUMERO_ASESOR, ASISTENTE_INSCRIPCION_NUMERO, ASISTENTE_INSCRIPCION_WA
from db import guardar_mensaje, obtener_historial, limpiar_historial_antiguo, intentar_marcar_procesado, limpiar_mensajes_procesados_antiguos
from contexto import cargar_contexto
from meta_api import marcar_como_leido, enviar_whatsapp
from openai_service import generar_respuesta, extraer_texto_respuesta, parsear_llamadas_funcion, MENSAJES_RESPALDO, MENSAJE_RESPALDO_GENERICO, MENSAJE_ERROR_TECNICO, get_inscripcion_instruccion

app = Flask(__name__)


@app.route('/', methods=['GET'])
def inicio():
    return "¡Servidor de WhatsApp e IA activo correctamente!", 200


@app.route('/webhook', methods=['GET'])
def verificar_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return challenge, 200
        return 'Validación fallida', 403
    return 'Mal formato', 400


def firma_valida(payload_bytes: bytes, signature_header: str) -> bool:
    import hmac
    import hashlib
    from config import META_APP_SECRET

    if not signature_header or not signature_header.startswith("sha256="):
        return False
    firma_recibida = signature_header.split("sha256=", 1)[1]
    firma_esperada = hmac.new(
        META_APP_SECRET.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(firma_esperada, firma_recibida)


@app.route('/webhook', methods=['POST'])
def recibir_webhook():
    firma_header = request.headers.get("X-Hub-Signature-256", "")
    if not firma_valida(request.get_data(), firma_header):
        log.warning("⚠️ Webhook recibido con firma inválida — descartado.")
        return jsonify({"status": "invalid signature"}), 403

    data = request.get_json(silent=True) or {}
    future = executor.submit(procesar_payload, data)
    future.add_done_callback(_log_future_exception)
    return jsonify({"status": "success"}), 200


def _log_future_exception(future):
    try:
        exc = future.exception()
    except Exception as err:
        log.exception("❌ Error revisando la tarea de fondo", exc_info=(type(err), err, err.__traceback__))
        return

    if exc:
        log.error("❌ Error en la tarea de fondo", exc_info=(type(exc), exc, exc.__traceback__))


def procesar_payload(data: dict):
    try:
        entries = data.get('entry', [])
        for entry in entries:
            changes = entry.get('changes', [])
            for change in changes:
                value = change.get('value', {})

                if change.get('field') != 'messages' or value.get('messaging_product') != 'whatsapp':
                    continue

                contacts = value.get('contacts', [])
                nombre_usuario = "Usuario"
                if contacts:
                    nombre_usuario = contacts[0].get('profile', {}).get('name', 'Usuario')

                metadata = value.get('metadata', {})
                phone_number_id = metadata.get('phone_number_id')

                messages = value.get('messages', [])
                for message in messages:
                    procesar_mensaje_individual(message, nombre_usuario, phone_number_id)

    except Exception as e:
        log.exception(f"❌ Error interno procesando el flujo de Meta: {e}")


def procesar_mensaje_individual(message: dict, nombre_usuario: str, phone_number_id: str):
    numero_usuario = message.get('from')
    wamid = message.get('id')

    if not intentar_marcar_procesado(wamid):
        log.info(f"🔁 Mensaje {wamid} ya procesado antes, se ignora (reintento de Meta).")
        return

    marcar_como_leido(wamid, phone_number_id)

    texto_usuario = None
    tipo_mensaje = message.get('type')
    if tipo_mensaje == 'text':
        texto_usuario = message.get('text', {}).get('body')
    elif tipo_mensaje == 'interactive':
        interactive = message.get('interactive', {})
        if interactive.get('type') == 'button_reply':
            texto_usuario = interactive.get('button_reply', {}).get('title')
        elif interactive.get('type') == 'list_reply':
            texto_usuario = interactive.get('list_reply', {}).get('title')
    elif tipo_mensaje == 'button':
        texto_usuario = message.get('button', {}).get('text')

    referral = message.get('referral')
    ad_context = ""
    if referral:
        headline = referral.get('headline', '')
        body = referral.get('body', '')
        source_id = referral.get('source_id', '')
        ad_context = f"\n[El usuario hizo clic en el anuncio de Facebook: '{headline}' - '{body}' (ID: {source_id})]"
        if not texto_usuario:
            texto_usuario = f"Hola, me interesa el anuncio: {headline}"

    if texto_usuario:
        texto_usuario = texto_usuario.strip()
    if not texto_usuario:
        log.info(f"⚠️ Mensaje vacío o no textual desde {numero_usuario}; se ignora.")
        return

    log.info(f"📩 {nombre_usuario} ({numero_usuario}) dijo: {texto_usuario}")

    contexto_privado = cargar_contexto()

    instrucciones_sistema = (
        "Eres un asistente de servicio al cliente automatizado y amable.\n"
        "Usa ÚNICAMENTE el siguiente contexto para responder la pregunta del usuario.\n"
        "REGLA CRÍTICA: Si la respuesta no se encuentra explícitamente en el contexto, "
        "sigue las reglas de escalamiento definidas en el contexto (mensaje de escalación + "
        "llamada a la función notificar_traspaso). No inventes ni asumas información.\n\n"
        f"Contexto:\n{contexto_privado}"
    )

    if ad_context:
        instrucciones_sistema += (
            f"\n\nContexto de origen del anuncio:\n{ad_context}\n"
            "IMPORTANTE: Saluda amigablemente haciendo alusión al anuncio de forma natural "
            "y prioriza la información del contexto privado relacionada con el tema del anuncio."
        )

    historial_previo = obtener_historial(numero_usuario)
    entrada_modelo = historial_previo + [{"role": "user", "content": texto_usuario}]

    respuesta_final = ""
    tipo_traspaso_detectado = None

    try:
        response = generar_respuesta(instrucciones_sistema, entrada_modelo)
        respuesta_final = extraer_texto_respuesta(response)

        for item in parsear_llamadas_funcion(response):
            if item.name == "notificar_traspaso":
                try:
                    datos = json.loads(item.arguments)
                except json.JSONDecodeError:
                    datos = {}

                tipo_traspaso_detectado = datos.get("tipo")
                etiqueta = {
                    "listo_para_inscribir": "🔥 LISTO PARA INSCRIBIR",
                    "duda_sin_resolver": "❓ DUDA SIN RESOLVER",
                    "tramite_administrativo": "🗂 TRÁMITE ADMINISTRATIVO",
                }.get(tipo_traspaso_detectado, tipo_traspaso_detectado or "TRASPASO")

                aviso = (
                    f"{etiqueta}\n"
                    f"Programa: {datos.get('programa', 'N/A')}\n"
                    f"Cliente: {nombre_usuario} ({numero_usuario})\n"
                    f"Nota: {datos.get('resumen', 'Sin detalle')}"
                )
                enviar_whatsapp(NUMERO_ASESOR, aviso, phone_number_id)

    except Exception as e:
        log.exception(f"❌ Error llamando a OpenAI para {numero_usuario}: {e}")
        enviar_whatsapp(numero_usuario, MENSAJE_ERROR_TECNICO, phone_number_id)
        guardar_mensaje(numero_usuario, "user", texto_usuario)
        return

    if not respuesta_final:
        respuesta_final = MENSAJES_RESPALDO.get(tipo_traspaso_detectado, MENSAJE_RESPALDO_GENERICO)
    elif tipo_traspaso_detectado == "listo_para_inscribir":
        instruccion_inscripcion = get_inscripcion_instruccion()
        if ASISTENTE_INSCRIPCION_NUMERO not in respuesta_final and ASISTENTE_INSCRIPCION_WA not in respuesta_final:
            respuesta_final = respuesta_final.strip() + "\n\n" + instruccion_inscripcion

    enviar_whatsapp(numero_usuario, respuesta_final, phone_number_id)
    log.info(f"🤖 Chatbot respondió a {numero_usuario}: {respuesta_final}")

    guardar_mensaje(numero_usuario, "user", texto_usuario)
    guardar_mensaje(numero_usuario, "assistant", respuesta_final)
    limpiar_historial_antiguo(numero_usuario)
    limpiar_mensajes_procesados_antiguos()


if __name__ == '__main__':
    from config import PORT
    log.info(f"Servidor local arrancando en http://0.0.0.0:{PORT}")
    app.run(host='0.0.0.0', port=PORT)
