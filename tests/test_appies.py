import hashlib
import hmac
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

import appies
import db


@pytest.fixture(autouse=True)
def run_background_tasks_synchronously(monkeypatch):
    """Makes the webhook handler's background processing run inline for
    deterministic tests, instead of on the real thread pool."""

    def fake_submit(fn, *args, **kwargs):
        result_future = MagicMock()
        try:
            fn(*args, **kwargs)
            result_future.exception.return_value = None
        except Exception as exc:  # pragma: no cover - surfaced via assertions
            result_future.exception.return_value = exc

        def add_done_callback(callback):
            callback(result_future)

        result_future.add_done_callback = add_done_callback
        return result_future

    monkeypatch.setattr(appies.executor, "submit", fake_submit)


@pytest.fixture
def client():
    return appies.app.test_client()


def firmar(payload_bytes: bytes) -> str:
    firma = hmac.new(b"testsecret", payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={firma}"


def payload_mensaje(wamid, texto=None, numero="5216141234567", nombre="Ana", tipo="text", extra_message=None):
    message = {"id": wamid, "from": numero}
    if extra_message:
        message.update(extra_message)
    elif tipo == "text":
        message["type"] = "text"
        message["text"] = {"body": texto}

    return {
        "entry": [{
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "123456"},
                    "contacts": [{"profile": {"name": nombre}}],
                    "messages": [message],
                },
            }]
        }]
    }


def post_webhook(client, payload: dict):
    body = json.dumps(payload).encode()
    return client.post(
        "/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": firmar(body)},
    )


def fake_openai_response(texto="Respuesta de prueba.", function_calls=None):
    response = MagicMock()
    response.output_text = texto
    response.output = function_calls or []
    return response


def fake_function_call(name, **arguments):
    item = MagicMock()
    item.type = "function_call"
    item.name = name
    item.arguments = json.dumps(arguments)
    return item


def test_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_webhook_verification_valid_token(client):
    resp = client.get("/webhook", query_string={
        "hub.mode": "subscribe",
        "hub.verify_token": "test-verify-token",
        "hub.challenge": "12345",
    })
    assert resp.status_code == 200
    assert resp.data == b"12345"


def test_webhook_verification_invalid_token(client):
    resp = client.get("/webhook", query_string={
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong-token",
        "hub.challenge": "12345",
    })
    assert resp.status_code == 403


def test_webhook_post_rejects_invalid_signature(client):
    body = json.dumps({"entry": []}).encode()
    resp = client.post(
        "/webhook",
        data=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert resp.status_code == 403


def test_full_message_flow_sends_reply_and_saves_history(client):
    payload = payload_mensaje("wamid.FLOW1", texto="Hola, quiero informacion")
    respuesta = fake_openai_response("Aqui tienes la info.")

    with patch("openai_service.client.responses.create", return_value=respuesta) as mock_create, \
         patch("meta_api.session.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, text="{}")
        resp = post_webhook(client, payload)

    assert resp.status_code == 200
    assert mock_create.called
    urls_llamadas = [call.kwargs.get("json") for call in mock_post.call_args_list]
    assert any(body.get("status") == "read" for body in urls_llamadas)
    assert any(body.get("text", {}).get("body") == "Aqui tienes la info." for body in urls_llamadas)

    historial = db.obtener_historial("5216141234567")
    assert {"role": "user", "content": "Hola, quiero informacion"} in historial
    assert {"role": "assistant", "content": "Aqui tienes la info."} in historial


def test_escalation_notifies_advisor_and_appends_inscription_link(client):
    payload = payload_mensaje("wamid.ESCALA1", texto="Quiero inscribirme ya")
    llamada = fake_function_call(
        "notificar_traspaso",
        tipo="listo_para_inscribir",
        programa="Psicopedagogia",
        resumen="Quiere inscribirse ya",
    )
    respuesta = fake_openai_response("Genial, vamos a inscribirte.", function_calls=[llamada])

    with patch("openai_service.client.responses.create", return_value=respuesta), \
         patch("meta_api.session.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, text="{}")
        post_webhook(client, payload)

    cuerpos = [call.kwargs.get("json") for call in mock_post.call_args_list]
    aviso_asesor = next(b for b in cuerpos if b.get("to") == "5210000000000")
    assert "LISTO PARA INSCRIBIR" in aviso_asesor["text"]["body"]

    respuesta_usuario = next(b for b in cuerpos if b.get("to") == "5216141234567")
    assert "inscripción" in respuesta_usuario["text"]["body"]


def test_duplicate_wamid_is_processed_only_once(client):
    payload = payload_mensaje("wamid.DUP1", texto="Hola de nuevo")
    respuesta = fake_openai_response("Hola otra vez.")

    with patch("openai_service.client.responses.create", return_value=respuesta) as mock_create, \
         patch("meta_api.session.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, text="{}")
        post_webhook(client, payload)
        post_webhook(client, payload)

    assert mock_create.call_count == 1


def test_intentar_marcar_procesado_is_atomic_under_concurrency():
    """Regression test for the TOCTOU race between checking and marking a
    wamid as processed: concurrent callers for the same wamid must have
    exactly one winner."""
    wamid = "wamid.RACE1"
    resultados = []
    barrera = threading.Barrier(10)

    def intentar():
        barrera.wait()
        resultados.append(db.intentar_marcar_procesado(wamid))

    hilos = [threading.Thread(target=intentar) for _ in range(10)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert resultados.count(True) == 1
    assert resultados.count(False) == 9


def test_interactive_button_reply_generates_response(client):
    payload = payload_mensaje(
        "wamid.BTN1",
        numero="5216143333333",
        extra_message={
            "type": "interactive",
            "interactive": {"type": "button_reply", "button_reply": {"id": "opt1", "title": "Si, quiero info"}},
        },
    )
    respuesta = fake_openai_response("Claro, aqui tienes info.")

    with patch("openai_service.client.responses.create", return_value=respuesta) as mock_create, \
         patch("meta_api.session.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, text="{}")
        post_webhook(client, payload)

    assert mock_create.called
    entrada = mock_create.call_args.kwargs["input"]
    assert entrada[-1]["content"] == "Si, quiero info"


def test_non_interactive_unsupported_message_is_ignored(client):
    payload = payload_mensaje(
        "wamid.IMG1",
        numero="5216144444444",
        extra_message={"type": "image", "image": {"id": "media123"}},
    )

    with patch("openai_service.client.responses.create") as mock_create, \
         patch("meta_api.session.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, text="{}")
        post_webhook(client, payload)

    assert not mock_create.called


def test_limpiar_mensajes_procesados_antiguos_purges_old_entries():
    from datetime import datetime, timedelta, timezone

    con = db.conectar()
    try:
        vieja_fecha = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        con.execute(
            "INSERT OR REPLACE INTO mensajes_procesados (wamid, procesado_en) VALUES (?, ?)",
            ("wamid.OLD", vieja_fecha),
        )
        con.commit()
    finally:
        con.close()

    db.limpiar_mensajes_procesados_antiguos()

    con = db.conectar()
    try:
        fila = con.execute(
            "SELECT 1 FROM mensajes_procesados WHERE wamid = ?", ("wamid.OLD",)
        ).fetchone()
    finally:
        con.close()
    assert fila is None
