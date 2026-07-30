import json
from urllib.parse import quote_plus
from openai import OpenAI
from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_STORE_RESPONSES,
    ASISTENTE_INSCRIPCION_NUMERO,
    ASISTENTE_INSCRIPCION_WA,
)

client = OpenAI(api_key=OPENAI_API_KEY)

tools_traspaso = [
    {
        "type": "function",
        "name": "notificar_traspaso",
        "description": (
            "Notifica a un asesor humano que un prospecto está siendo transferido. "
            "Llámala junto con tu respuesta normal al cliente, nunca en lugar de ella."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "enum": ["listo_para_inscribir", "duda_sin_resolver", "tramite_administrativo"],
                    "description": "Motivo del traspaso.",
                },
                "programa": {
                    "type": "string",
                    "description": "Programa de interés del prospecto, si se conoce.",
                },
                "resumen": {
                    "type": "string",
                    "description": "1 línea de contexto para el asesor.",
                },
            },
            "required": ["tipo", "resumen"],
        },
    }
]


def get_inscripcion_link() -> str:
    texto = quote_plus("estoy listo para la inscripcion")
    return f"https://wa.me/{ASISTENTE_INSCRIPCION_WA}?text={texto}"


def get_inscripcion_instruccion() -> str:
    return (
        f"Para continuar con tu inscripción, comunícate al número {ASISTENTE_INSCRIPCION_NUMERO} con el mensaje "
        f"\"estoy listo para la inscripcion\" o haz clic en este enlace: {get_inscripcion_link()}"
    )


MENSAJES_RESPALDO = {
    "listo_para_inscribir": (
        f"¡Perfecto! Para continuar con tu inscripción, comunícate al número {ASISTENTE_INSCRIPCION_NUMERO} "
        f"con el mensaje \"estoy listo para la inscripcion\" o haz clic en el siguiente enlace: {get_inscripcion_link()} 🙂"
    ),
    "duda_sin_resolver": "En un momento te atiende un asesor para resolver tu duda 🙂",
    "tramite_administrativo": "En un momento te atiende un asesor para ayudarte con ese trámite 🙂",
}
MENSAJE_RESPALDO_GENERICO = "En un momento te atiende un asesor 🙂"
MENSAJE_ERROR_TECNICO = "Disculpa, tuve un problema técnico. En un momento te contacta un asesor 🙂"


def extraer_texto_respuesta(response) -> str:
    texto = getattr(response, "output_text", None) or ""
    output_items = getattr(response, "output", []) or []
    if texto:
        return texto.strip()

    partes = []
    for item in output_items:
        if isinstance(item, dict):
            partes.append(item.get("content") or item.get("text") or "")
        else:
            partes.append(getattr(item, "content", "") or getattr(item, "text", ""))
    return " ".join([p for p in partes if p]).strip()


def generar_respuesta(instrucciones: str, entrada_modelo: list):
    return client.responses.create(
        model=OPENAI_MODEL,
        instructions=instrucciones,
        input=entrada_modelo,
        temperature=0.5,
        max_output_tokens=2048,
        store=OPENAI_STORE_RESPONSES,
        tools=tools_traspaso,
    )


def parsear_llamadas_funcion(response):
    output_items = getattr(response, "output", []) or []
    return [item for item in output_items if getattr(item, "type", None) == "function_call"]
