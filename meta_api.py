import time
from config import META_BASE_URL, API_VERSION, META_TOKEN, PHONE_NUMBER_ID, REQUEST_TIMEOUT, log, session


def _post_json(url: str, payload: dict, headers: dict, timeout: float = REQUEST_TIMEOUT):
    try:
        response = session.post(url, json=payload, headers=headers, timeout=timeout)
        if response.status_code >= 400:
            log.warning(
                f"⚠️ Error HTTP {response.status_code} en POST a {url}: {response.text}"
            )
        return response
    except Exception as e:
        log.warning(f"⚠️ Error de red en POST a {url}: {e}")
        return None


def marcar_como_leido(message_id: str, phone_number_id: str):
    if not message_id or not phone_number_id:
        return
    url = f"{META_BASE_URL}/{API_VERSION}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
    _post_json(url, payload, headers)


def enviar_whatsapp(number: str, text: str, phone_number_id: str = None, reintentos: int = 2):
    if not number:
        return None
    if not phone_number_id:
        phone_number_id = PHONE_NUMBER_ID

    url = f"{META_BASE_URL}/{API_VERSION}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": number,
        "type": "text",
        "text": {"body": text},
    }

    for intento in range(1, reintentos + 2):
        try:
            res = session.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
            if res is not None and res.status_code >= 400:
                log.error(
                    f"❌ Error enviando WhatsApp a {number} (status {res.status_code}): {res.text}"
                )
            return res
        except Exception as e:
            log.warning(f"⚠️ Intento {intento} fallido enviando WhatsApp a {number}: {e}")
            if intento <= reintentos:
                time.sleep(2 * intento)
    log.error(f"❌ No se pudo enviar el mensaje a {number} tras {reintentos + 1} intentos.")
    return None
