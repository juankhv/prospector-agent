"""
Cloud Function para disparar el agente de prospección diariamente.

Verifica que sea día hábil (no feriado en Colombia), elige un sector
rotativo, y llamá al servicio del agente para ejecutar la prospección.
"""

import os
import json
import logging
from datetime import datetime, timezone
import requests
import functions_framework


logger = logging.getLogger(__name__)


def _es_fin_de_semana(fecha):
    """Retorna True si es sábado (5) o domingo (6)."""
    return fecha.weekday() >= 5


def _es_feriado_colombia(fecha):
    """Verifica si la fecha es feriado en Colombia usando nager.at API."""
    try:
        año = fecha.year
        url = f"https://date.nager.at/api/v3/PublicHolidays/{año}/CO"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        feriados = resp.json()

        fecha_str = fecha.strftime("%Y-%m-%d")
        for feriado in feriados:
            if feriado.get("date") == fecha_str:
                return True
        return False
    except Exception as e:
        logger.warning(f"Error verificando feriados: {e}. Asumiendo día hábil.")
        return False


def _elegir_sector(fecha):
    """Elige un sector rotativo basado en el día del año."""
    sectores = ["TI", "Banca", "Consumo Masivo", "Utilities"]
    día_del_año = fecha.timetuple().tm_yday
    índice = (día_del_año - 1) % len(sectores)
    return sectores[índice]


@functions_framework.http
def trigger_prospector(request):
    """Dispara la prospección diaria si es día hábil."""
    try:
        # Verificar si es fin de semana
        ahora = datetime.now(timezone.utc)
        if _es_fin_de_semana(ahora):
            return ("Fin de semana, no se ejecuta", 200)

        # Verificar si es feriado en Colombia
        if _es_feriado_colombia(ahora):
            return ("Feriado, no se ejecuta", 200)

        # Obtener URL del servicio del agente
        agent_service_url = os.environ.get("AGENT_SERVICE_URL")
        if not agent_service_url:
            logger.error("AGENT_SERVICE_URL no configurado")
            return ("Error de configuración", 500)

        # Elegir sector y crear session_id
        sector = _elegir_sector(ahora)
        session_id = ahora.strftime("auto-%Y%m%d-%H%M%S")

        # POST 1: Crear sesión
        crear_sesion_url = f"{agent_service_url}/apps/prospector_agent/users/scheduler/sessions/{session_id}"
        try:
            resp1 = requests.post(
                crear_sesion_url,
                json={},
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            resp1.raise_for_status()
            logger.info(f"Sesión creada: {session_id}")
        except Exception as e:
            logger.error(f"Error creando sesión: {e}")
            return ("Error creando sesión", 500)

        # POST 2: Ejecutar agente
        run_url = f"{agent_service_url}/run"
        mensaje = f"Prospectá 10 empresas del sector {sector}"
        body = {
            "appName": "prospector_agent",
            "userId": "scheduler",
            "sessionId": session_id,
            "newMessage": {
                "role": "user",
                "parts": [{"text": mensaje}],
            },
        }
        try:
            resp2 = requests.post(
                run_url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=540,
            )
            resp2.raise_for_status()
            logger.info(f"Agente ejecutado para sector {sector}")
        except requests.exceptions.Timeout:
            logger.info(f"Timeout esperado: agente sigue corriendo en background para sector {sector}")
            return ("OK, agente disparado (corriendo en background)", 200)
        except Exception as e:
            logger.error(f"Error ejecutando agente: {e}")
            return ("Error ejecutando agente", 500)

        return ("OK", 200)

    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return ("Error inesperado", 500)


@functions_framework.http
def trigger_revision_aprobaciones(request):
    """Dispara la revisión de aprobaciones pendientes."""
    try:
        # Obtener URL del servicio del agente
        agent_service_url = os.environ.get("AGENT_SERVICE_URL")
        if not agent_service_url:
            logger.error("AGENT_SERVICE_URL no configurado")
            return ("Error de configuración", 500)

        # Crear session_id único con fecha y hora
        ahora = datetime.now(timezone.utc)
        session_id = ahora.strftime("aprob-%Y%m%d-%H%M%S")

        # POST 1: Crear sesión
        crear_sesion_url = f"{agent_service_url}/apps/prospector_agent/users/scheduler/sessions/{session_id}"
        try:
            resp1 = requests.post(
                crear_sesion_url,
                json={},
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            resp1.raise_for_status()
            logger.info(f"Sesión creada: {session_id}")
        except Exception as e:
            logger.error(f"Error creando sesión: {e}")
            return ("Error creando sesión", 500)

        # POST 2: Ejecutar agente para revisar aprobaciones
        run_url = f"{agent_service_url}/run"
        mensaje = "Revisá las aprobaciones pendientes"
        body = {
            "appName": "prospector_agent",
            "userId": "scheduler",
            "sessionId": session_id,
            "newMessage": {
                "role": "user",
                "parts": [{"text": mensaje}],
            },
        }
        try:
            resp2 = requests.post(
                run_url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=540,
            )
            resp2.raise_for_status()
            logger.info(f"Agente ejecutado para revisar aprobaciones")
        except requests.exceptions.Timeout:
            logger.info(f"Timeout esperado: agente sigue corriendo en background para revisión de aprobaciones")
            return ("OK, agente disparado (corriendo en background)", 200)
        except Exception as e:
            logger.error(f"Error ejecutando agente: {e}")
            return ("Error ejecutando agente", 500)

        return ("OK", 200)

    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return ("Error inesperado", 500)


@functions_framework.http
def trigger_reintento_rechazados(request):
    """Dispara el reintento de leads rechazados."""
    try:
        # Obtener URL del servicio del agente
        agent_service_url = os.environ.get("AGENT_SERVICE_URL")
        if not agent_service_url:
            logger.error("AGENT_SERVICE_URL no configurado")
            return ("Error de configuración", 500)

        # Crear session_id único con fecha y hora
        ahora = datetime.now(timezone.utc)
        session_id = ahora.strftime("reint-%Y%m%d-%H%M%S")

        # POST 1: Crear sesión
        crear_sesion_url = f"{agent_service_url}/apps/prospector_agent/users/scheduler/sessions/{session_id}"
        try:
            resp1 = requests.post(
                crear_sesion_url,
                json={},
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            resp1.raise_for_status()
            logger.info(f"Sesión creada: {session_id}")
        except Exception as e:
            logger.error(f"Error creando sesión: {e}")
            return ("Error creando sesión", 500)

        # POST 2: Ejecutar agente para reintentar rechazados
        run_url = f"{agent_service_url}/run"
        mensaje = "Reintentá los rechazados"
        body = {
            "appName": "prospector_agent",
            "userId": "scheduler",
            "sessionId": session_id,
            "newMessage": {
                "role": "user",
                "parts": [{"text": mensaje}],
            },
        }
        try:
            resp2 = requests.post(
                run_url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=540,
            )
            resp2.raise_for_status()
            logger.info(f"Agente ejecutado para reintentar rechazados")
        except requests.exceptions.Timeout:
            logger.info(f"Timeout esperado: agente sigue corriendo en background para reintento de rechazados")
            return ("OK, agente disparado (corriendo en background)", 200)
        except Exception as e:
            logger.error(f"Error ejecutando agente: {e}")
            return ("Error ejecutando agente", 500)

        return ("OK", 200)

    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return ("Error inesperado", 500)


@functions_framework.http
def trigger_revision_respuestas(request):
    """Dispara la revisión de respuestas y rebotes en la bandeja."""
    try:
        # Obtener URL del servicio del agente
        agent_service_url = os.environ.get("AGENT_SERVICE_URL")
        if not agent_service_url:
            logger.error("AGENT_SERVICE_URL no configurado")
            return ("Error de configuración", 500)

        # Crear session_id único con fecha y hora
        ahora = datetime.now(timezone.utc)
        session_id = ahora.strftime("resp-%Y%m%d-%H%M%S")

        # POST 1: Crear sesión
        crear_sesion_url = f"{agent_service_url}/apps/prospector_agent/users/scheduler/sessions/{session_id}"
        try:
            resp1 = requests.post(
                crear_sesion_url,
                json={},
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            resp1.raise_for_status()
            logger.info(f"Sesión creada: {session_id}")
        except Exception as e:
            logger.error(f"Error creando sesión: {e}")
            return ("Error creando sesión", 500)

        # POST 2: Ejecutar agente para revisar respuestas y rebotes
        run_url = f"{agent_service_url}/run"
        mensaje = "Revisá la bandeja de respuestas y rebotes"
        body = {
            "appName": "prospector_agent",
            "userId": "scheduler",
            "sessionId": session_id,
            "newMessage": {
                "role": "user",
                "parts": [{"text": mensaje}],
            },
        }
        try:
            resp2 = requests.post(
                run_url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=540,
            )
            resp2.raise_for_status()
            logger.info(f"Agente ejecutado para revisar respuestas y rebotes")
        except requests.exceptions.Timeout:
            logger.info(f"Timeout esperado: agente sigue corriendo en background para revisión de respuestas")
            return ("OK, agente disparado (corriendo en background)", 200)
        except Exception as e:
            logger.error(f"Error ejecutando agente: {e}")
            return ("Error ejecutando agente", 500)

        return ("OK", 200)

    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return ("Error inesperado", 500)


@functions_framework.http
def trigger_seguimiento(request):
    """Dispara el seguimiento a leads sin respuesta."""
    try:
        # Obtener URL del servicio del agente
        agent_service_url = os.environ.get("AGENT_SERVICE_URL")
        if not agent_service_url:
            logger.error("AGENT_SERVICE_URL no configurado")
            return ("Error de configuración", 500)

        # Crear session_id único con fecha y hora
        ahora = datetime.now(timezone.utc)
        session_id = ahora.strftime("segui-%Y%m%d-%H%M%S")

        # POST 1: Crear sesión
        crear_sesion_url = f"{agent_service_url}/apps/prospector_agent/users/scheduler/sessions/{session_id}"
        try:
            resp1 = requests.post(
                crear_sesion_url,
                json={},
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            resp1.raise_for_status()
            logger.info(f"Sesión creada: {session_id}")
        except Exception as e:
            logger.error(f"Error creando sesión: {e}")
            return ("Error creando sesión", 500)

        # POST 2: Ejecutar agente para hacer seguimiento
        run_url = f"{agent_service_url}/run"
        mensaje = "Hacé seguimiento"
        body = {
            "appName": "prospector_agent",
            "userId": "scheduler",
            "sessionId": session_id,
            "newMessage": {
                "role": "user",
                "parts": [{"text": mensaje}],
            },
        }
        try:
            resp2 = requests.post(
                run_url,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=540,
            )
            resp2.raise_for_status()
            logger.info(f"Agente ejecutado para seguimiento")
        except requests.exceptions.Timeout:
            logger.info(f"Timeout esperado: agente sigue corriendo en background para seguimiento")
            return ("OK, agente disparado (corriendo en background)", 200)
        except Exception as e:
            logger.error(f"Error ejecutando agente: {e}")
            return ("Error ejecutando agente", 500)

        return ("OK", 200)

    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return ("Error inesperado", 500)



