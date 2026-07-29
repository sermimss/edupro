# EduPro Bot

Repositorio listo para desplegar en Render con integración de WhatsApp Cloud API de Meta.

## Estructura principal

- `appies.py`: punto de entrada principal de Flask.
- `config.py`: carga de variables de entorno y configuración global.
- `db.py`: manejo de la base de datos SQLite local.
- `contexto.py`: carga y cache de la hoja de contexto.
- `openai_service.py`: llamadas a OpenAI y manejo de respuesta.
- `meta_api.py`: envío de mensajes y marcado de leídos a Meta/WhatsApp.
- `requirements.txt`: dependencias de Python.
- `Procfile`: comando de inicio para Render.
- `render.yaml`: definición del servicio Render.

## Despliegue en Render

1. Sube este proyecto a GitHub si aún no lo has hecho.

2. En Render, crea un nuevo servicio `Web Service`.

3. Conecta tu cuenta a este repositorio `https://github.com/sermimss/edupro`.

4. Selecciona la rama `main`.

5. Configura el build y start:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn appies:app --bind 0.0.0.0:$PORT --workers 2`

6. Agrega estas variables de entorno en Render:
   - `OPENAI_API_KEY`
   - `META_TOKEN`
   - `PHONE_NUMBER_ID`
   - `META_APP_SECRET`
   - `NUMERO_ASESOR`
   - `VERIFY_TOKEN` (por ejemplo `vibecode`)
   - `LOG_FILE=/tmp/cess_bot.log` (opcional)
   - `ASISTENTE_INSCRIPCION_NUMERO=6142015283` (opcional si quieres sobreescribir)
   - `ASISTENTE_INSCRIPCION_WA=526142015283` (opcional)
   - `OPENAI_MODEL=gpt-4o-mini` (opcional)

7. Despliega y espera a que Render construya el servicio.

8. Verifica que la URL pública responda en `/`.

## Conexión con Meta / WhatsApp Cloud API

1. En Facebook Developers, crea o usa tu app de WhatsApp Cloud API.
2. Consigue:
   - `META_TOKEN` (Access Token)
   - `META_APP_SECRET`
   - `PHONE_NUMBER_ID`

3. Configura Webhooks en la app de Meta:
   - Callback URL: `https://<tu-app>.onrender.com/webhook`
   - Verify Token: el valor de `VERIFY_TOKEN`
   - Suscribe los siguientes eventos:
     - `messages`
     - `message_deliveries`
     - `message_reactions`

4. Asegúrate de que el teléfono de WhatsApp esté conectado y activo.

5. Prueba enviando un mensaje al número de WhatsApp vinculado.

## Notas de producción

- El bot usa SQLite en `/tmp/historial_cess.db` por defecto. En Render, ese almacenamiento es temporal y se pierde al reiniciar el contenedor.
- Para producción, considera usar una base de datos externa si necesitas persistencia real.
- Asegúrate de no subir secretos; usa variables de entorno en Render.

## Ejecutar localmente

1. Crea un archivo `.env` con las variables necesarias.
2. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Ejecuta localmente:
   ```bash
   python appies.py
   ```

## URL del repositorio

`https://github.com/sermimss/edupro`
