"""
Herramientas (tools) del agente de prospección.

Todas conectadas a servicios reales: Apollo.io, Gemini (Vertex AI),
Microsoft Graph (Outlook), y Google Sheets (sustituto temporal de HubSpot
para no mezclar con el pipeline de producción en n8n).
"""

import os
import re
import json
import html
from datetime import datetime, timezone, timedelta

import requests

# ---------------------------------------------------------------------------
# Apollo.io
# ---------------------------------------------------------------------------

APOLLO_SECTOR_TAGS = {
    "TI": ["Information Technology", "IT Services"],
    "Banca": ["Banking"],
    "Consumo Masivo": ["Food & Beverages"],
    "Utilities": ["Utilities"],
}

CLIENTES_ACTUALES = [
    "sutherland", "bancolombia", "manpower", "teleperformance", "eficacia",
    "bavaria", "nequi", "covestro", "indra", "hsbc", "veolia",
    "electroequipos", "adecco",
]

PAISES_LATAM_HISPANO = [
    "Colombia", "Mexico", "Argentina", "Chile", "Peru", "Ecuador", "Venezuela",
    "Guatemala", "Costa Rica", "Panama", "Republica Dominicana", "Uruguay",
    "Paraguay", "Bolivia", "El Salvador", "Honduras", "Nicaragua"
]


def _es_cliente_actual(nombre_empresa: str) -> bool:
    nombre = (nombre_empresa or "").lower()
    if any(s in nombre for s in CLIENTES_ACTUALES):
        return True
    if re.search(r"\btp\b", nombre):
        return True
    return False


def _hace_n_dias_habiles(fecha_str: str, n: int) -> bool:
    """Verifica si han pasado al menos n días hábiles desde fecha_str hasta ahora.

    Args:
        fecha_str: Fecha en formato "%Y-%m-%d %H:%M UTC"
        n: Número de días hábiles a verificar

    Returns:
        True si han pasado >= n días hábiles, False si no o si falla el parseo.
    """
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
        ahora = datetime.now(timezone.utc)
        dias_habiles = 0
        fecha_actual = fecha.date()
        while fecha_actual < ahora.date():
            if fecha_actual.weekday() < 5:
                dias_habiles += 1
            fecha_actual += timedelta(days=1)
        return dias_habiles >= n
    except Exception:
        return False


def _obtener_config_prueba() -> dict:
    """Lee la configuración de modo de prueba desde "Demo Config" en Sheets.

    Returns:
        {"activo": bool, "email_prueba": str, "idioma": str, "empresa": str, "pais": str}
        Si no existe la pestaña o Active != "SI", devuelve {"activo": False}.
    """
    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not credenciales_json or not sheet_id:
        return {"activo": False}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)

        try:
            hoja = hoja_principal.worksheet("Demo Config")
        except Exception:
            return {"activo": False}

        header = hoja.row_values(1)
        if not header or "Active" not in header:
            return {"activo": False}

        fila = hoja.row_values(2)
        if not fila or len(fila) < 1:
            return {"activo": False}

        idx_active = header.index("Active")
        idx_email = header.index("TestEmail") if "TestEmail" in header else None
        idx_idioma = header.index("Language") if "Language" in header else None
        idx_empresa = header.index("CompanyName") if "CompanyName" in header else None
        idx_pais = header.index("Country") if "Country" in header else None

        activo = (fila[idx_active].strip().upper() == "SI") if idx_active < len(fila) else False

        return {
            "activo": activo,
            "email_prueba": fila[idx_email].strip() if idx_email and idx_email < len(fila) else "",
            "idioma": fila[idx_idioma].strip() if idx_idioma and idx_idioma < len(fila) else "es",
            "empresa": fila[idx_empresa].strip() if idx_empresa and idx_empresa < len(fila) else "Aptitude",
            "pais": fila[idx_pais].strip() if idx_pais and idx_pais < len(fila) else "Latinoamérica (todos los países hispanohablantes)",
        }
    except Exception:
        return {"activo": False}


def activar_modo_prueba(email_prueba: str, empresa: str = None, idioma: str = "en", pais: str = None) -> dict:
    """Activa el modo de prueba guardando configuración en "Demo Config" de Sheets.

    Args:
        email_prueba: Email donde se enviarán los correos de prueba.
        empresa: Nombre de la empresa en modo prueba (default: "Aptitude").
        idioma: Idioma de redacción ("es" o "en", default: "en").
        pais: País o mercado para búsqueda de leads (default: "Latinoamérica (todos los países hispanohablantes)").

    Returns:
        {"status": "activado", "config": {...valores guardados...}} o error claro.
    """
    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not credenciales_json or not sheet_id:
        return {"status": "error", "error": "Faltan credenciales de Sheets"}

    empresa = empresa or "Aptitude"
    pais = pais or "Latinoamérica (todos los países hispanohablantes)"

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)

        try:
            hoja = hoja_principal.worksheet("Demo Config")
        except gspread.exceptions.WorksheetNotFound:
            hoja = hoja_principal.add_worksheet(title="Demo Config", rows=10, cols=6)
            hoja.append_row(["Active", "TestEmail", "Language", "CompanyName", "ConfiguredAt", "Country"])

        hoja.resize(cols=6)
        fecha_ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        header = hoja.row_values(1)
        idx_active = header.index("Active") + 1 if "Active" in header else 1
        idx_email = header.index("TestEmail") + 1 if "TestEmail" in header else 2
        idx_idioma = header.index("Language") + 1 if "Language" in header else 3
        idx_empresa = header.index("CompanyName") + 1 if "CompanyName" in header else 4
        idx_fecha = header.index("ConfiguredAt") + 1 if "ConfiguredAt" in header else 5
        idx_pais = header.index("Country") + 1 if "Country" in header else 6

        hoja.update_cell(2, idx_active, "SI")
        hoja.update_cell(2, idx_email, email_prueba)
        hoja.update_cell(2, idx_idioma, idioma)
        hoja.update_cell(2, idx_empresa, empresa)
        hoja.update_cell(2, idx_fecha, fecha_ahora)
        hoja.update_cell(2, idx_pais, pais)

        return {
            "status": "activado",
            "config": {
                "email_prueba": email_prueba,
                "empresa": empresa,
                "idioma": idioma,
                "pais": pais,
                "configurado_en": fecha_ahora,
            }
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def desactivar_modo_prueba() -> dict:
    """Desactiva el modo de prueba poniendo Active="NO" en "Demo Config".

    Returns:
        {"status": "desactivado"} o error claro.
    """
    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not credenciales_json or not sheet_id:
        return {"status": "error", "error": "Faltan credenciales de Sheets"}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)

        try:
            hoja = hoja_principal.worksheet("Demo Config")
        except gspread.exceptions.WorksheetNotFound:
            return {"status": "error", "error": "Demo Config no existe"}

        header = hoja.row_values(1)
        if "Active" not in header:
            return {"status": "error", "error": "Columna Active no existe"}

        idx_active = header.index("Active") + 1
        hoja.update_cell(2, idx_active, "NO")

        return {"status": "desactivado"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _apollo_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "x-api-key": os.environ.get("APOLLO_API_KEY", ""),
    }


def buscar_leads_apollo(sector: str, cantidad: int = 5, pais: str = None) -> dict:
    """Busca leads en Apollo.io que cumplan el ICP de Aptitude para un sector dado.

    Usa esta herramienta como PRIMER paso, cuando el usuario pida prospectar
    un sector (ej. "banca", "TI", "consumo masivo", "utilities"). Ya excluye
    internamente a los clientes actuales y solo trae contactos con email
    verificado.

    Args:
        sector: Uno de "TI", "Banca", "Consumo Masivo", "Utilities".
        cantidad: Cuántos leads devolver como máximo (por defecto 5).
        pais: País o mercado para búsqueda (default: consulta config de prueba o "Colombia").

    Returns:
        Una lista de leads con nombre, apellido, cargo, empresa, industria y email.
        Lista vacía si Apollo falla o no hay resultados.
    """
    # Determinar lista de países para buscar
    if pais is not None:
        # Si se especifica un país explícitamente
        if pais == "Latinoamérica (todos los países hispanohablantes)":
            person_locations = PAISES_LATAM_HISPANO
        else:
            person_locations = [pais]
    else:
        # Si no se especifica, consultar config de prueba
        config_prueba = _obtener_config_prueba()
        if config_prueba.get("activo") and config_prueba.get("pais"):
            # En modo prueba con país específico, usar lista completa o país único
            pais_config = config_prueba.get("pais")
            if pais_config == "Latinoamérica (todos los países hispanohablantes)":
                person_locations = PAISES_LATAM_HISPANO
            else:
                person_locations = [pais_config]
        else:
            # Por defecto, buscar en toda Latinoamérica hispanohablante
            person_locations = PAISES_LATAM_HISPANO

    tags = APOLLO_SECTOR_TAGS.get(sector, [sector])
    # Si cantidad >= 5 (prospección diaria), pedir el doble de resultados para tener margen
    # Si cantidad < 5 (pruebas manuales chicas), pedir el triple para asegurar suficientes candidatos
    per_page = cantidad * 2 if cantidad >= 5 else max(cantidad * 3, 25)
    body = {
        "person_locations": person_locations,
        "person_titles": [
            "recruiter", "talent acquisition", "reclutamiento y selección",
            "coordinador de selección", "analista de selección",
        ],
        "organization_num_employees_ranges": [
            "1001,5000", "5001,10000", "10001,50000", "50001,1000000",
        ],
        "q_organization_keyword_tags": tags,
        "not_organization_naics_codes": ["5613", "5614", "211"],
        "per_page": per_page,
    }

    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/mixed_people/api_search",
            headers=_apollo_headers(), json=body, timeout=20,
        )
        resp.raise_for_status()
        personas = resp.json().get("people", [])
    except Exception:
        return {"leads": [], "total": 0}

    candidatos = []
    empresas_vistas = set()
    for p in personas:
        org = p.get("organization") or {}
        if not p.get("has_email"):
            continue
        if _es_cliente_actual(org.get("name", "")):
            continue
        nombre_empresa_norm = (org.get("name", "") or "").lower()
        if nombre_empresa_norm in empresas_vistas:
            continue
        empresas_vistas.add(nombre_empresa_norm)
        candidatos.append(p)
        # Si cantidad >= 5 (prospección diaria), recopilar todos los candidatos (cantidad * 2)
        # Si cantidad < 5 (pruebas manuales), cortar a exactamente cantidad para no devolver demasiados
        max_candidatos = cantidad * 2 if cantidad >= 5 else cantidad
        if len(candidatos) >= max_candidatos:
            break

    leads = []
    for p in candidatos:
        try:
            enr = requests.post(
                "https://api.apollo.io/api/v1/people/bulk_match",
                headers=_apollo_headers(),
                json={"details": [{"id": p["id"]}], "reveal_personal_emails": True},
                timeout=20,
            )
            enr.raise_for_status()
            matches = enr.json().get("matches", [])
            email = matches[0].get("email") if matches else None
        except Exception:
            email = None

        if not email:
            continue

        org = p.get("organization") or {}
        leads.append({
            "nombre": p.get('first_name', ''),
            "apellido": p.get('last_name', ''),
            "cargo": p.get("title", ""),
            "empresa": org.get("name", ""),
            "industria": sector,
            "email": email,
        })

    return {"leads": leads, "total": len(leads)}


def buscar_persona_por_linkedin(url_linkedin: str) -> dict:
    """Busca en Apollo los datos de una persona puntual a partir de su URL de LinkedIn.

    Usa esta herramienta cuando el usuario te dé un perfil de LinkedIn
    específico para contactar, en vez de pedirte prospectar un sector
    completo. Es una búsqueda dirigida a una sola persona, no un listado.

    Args:
        url_linkedin: URL completa del perfil de LinkedIn de la persona.

    Returns:
        Los datos de la persona si Apollo la encuentra (nombre, apellido, cargo,
        empresa, industria, email), o encontrado=False si no hay match
        o no tiene email disponible.
    """
    try:
        resp = requests.post(
            "https://api.apollo.io/api/v1/people/match",
            headers=_apollo_headers(),
            json={"linkedin_url": url_linkedin, "reveal_personal_emails": True},
            timeout=20,
        )
        resp.raise_for_status()
        persona = resp.json().get("person")
    except Exception:
        return {"encontrado": False}

    if not persona or not persona.get("email"):
        return {"encontrado": False}

    org = persona.get("organization") or {}
    return {
        "encontrado": True,
        "nombre": persona.get('first_name', ''),
        "apellido": persona.get('last_name', ''),
        "cargo": persona.get("title", ""),
        "empresa": org.get("name", ""),
        "industria": org.get("industry", "") or "general",
        "email": persona["email"],
    }


# ---------------------------------------------------------------------------
# Gemini (redacción y verificación)
# ---------------------------------------------------------------------------

REDACTOR_SYSTEM_PROMPT = """Eres Juan Carlos Hernández, Co-fundador y COO de Aptitude, una plataforma
que evalúa soft skills y personalidad para procesos de selección
en ~5 minutos. Vas a escribir un correo de prospección en frío, corto
(máximo 120 palabras en el cuerpo), en español, tono cercano y profesional,
usando "tienes"/"tú" en vez de voseo, dirigido a un profesional de RRHH/
Talent Acquisition.

Usa la investigación dada para abrir el correo de forma natural, no forzada.
Según la industria de la empresa, menciona casos de éxito relevantes: TI →
Indra; banca → HSBC y Nequi; consumo masivo o alimentos y bebidas → Bavaria;
utilities → Veolia Colombia. Máximo dos casos de éxito por correo. Si la
industria no corresponde claramente a ninguna de esas categorías, menciona
brevemente los 5 clientes juntos (Indra, HSBC, Nequi, Bavaria, Veolia
Colombia) como prueba social general, sin forzar una comparación directa de
industria. No inventes cifras ni datos que no se te den.

Cierra invitando a conversar 30 minutos de forma fluida y natural, ofreciendo
dos opciones: responder a este correo para coordinar un horario, o agendar
directamente usando este enlace: https://meetings.hubspot.com/aptitude/demo
(mantén el tono conversacional, no como una lista de opciones fría). Firma
exactamente con:
"Juan Carlos Hernández\\nCo-fundador & COO, Aptitude\\ntheaptitude.co"

Responde ÚNICAMENTE con JSON puro, sin backticks ni texto adicional:
{"asunto": "...", "cuerpo": "..."}"""

VERIFICADOR_SYSTEM_PROMPT = """Eres el verificador de calidad de correos de prospección B2B para
Aptitude. Revisa un correo ya redactado y confirma que sea fiel a la
investigación real, sin inventar ni exagerar nada. Revisa: 1) que el gancho
de personalización corresponda a la investigación dada; 2) que el caso de
éxito mencionado sea el correcto según la industria (TI→Indra, banca→HSBC/
Nequi, consumo masivo→Bavaria, utilities→Veolia), o que mencione los 5
clientes juntos si la industria no encaja en ninguna; 3) tono profesional,
natural, no robótico; 4) que no exceda 120 palabras en el cuerpo; 5) que el
dominio del email tenga alguna relación con la empresa — SÉ PERMISIVO acá:
muchas empresas usan dominios corporativos abreviados que no contienen el
nombre completo (ejemplos reales y válidos: Schneider Electric usa se.com,
General Motors usa gm.com, Grupo Éxito usa grupo-exito.com). Solo rechazá
por este motivo si el dominio es claramente de un proveedor de email personal
(gmail.com, hotmail.com, outlook.com sin ser corporativo) o si no tiene
ninguna relación identificable en absoluto con la empresa o industria
mencionada. Ante la duda razonable, APROBÁ este criterio en particular —
es preferible aceptar un dominio corporativo legítimo que rechazar por exceso
de cautela.

Responde ÚNICAMENTE con JSON puro: {"aprobado": true o false, "razon":
"si rechazas, explica específica y accionablemente qué corregir; si
apruebas, string vacío"}"""


def _generar_json_con_gemini(system_prompt: str, user_content: str) -> tuple:
    """Helper interno: llama a Gemini y parsea la respuesta como JSON.

    Returns:
        (dict_parseado, None) en éxito, o (None, mensaje_de_error) en falla.
    """
    try:
        from google import genai
        client = genai.Client()
        modelo = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
        respuesta = client.models.generate_content(
            model=modelo,
            contents=f"{system_prompt}\n\n---\n\n{user_content}",
            config={"response_mime_type": "application/json"},
        )
        return json.loads(respuesta.text), None
    except Exception as e:
        return None, str(e)


def redactar_correo(nombre_destinatario: str, cargo: str, empresa: str,
                     industria: str, investigacion: str,
                     feedback_previo: str = "", idioma: str = "es",
                     nombre_empresa_remitente: str = "Aptitude",
                     url_reuniones_custom: str = None) -> dict:
    """Redacta un correo de prospección en frío personalizado, usando Gemini.

    Usa esta herramienta después de investigar a la empresa (google_search_agent).
    Si verificar_correo rechazó un intento anterior, pasá su feedback en
    feedback_previo para corregir el correo.

    Args:
        nombre_destinatario: Nombre de la persona a contactar.
        cargo: Cargo del destinatario.
        empresa: Nombre de la empresa.
        industria: Industria de la empresa.
        investigacion: Texto libre con el gancho de personalización, ya
            redactado por vos a partir de la búsqueda web.
        feedback_previo: Motivo de rechazo del intento anterior, si aplica.
        idioma: "es" para español, "en" para inglés (default: "es").
        nombre_empresa_remitente: Nombre de la empresa que envía (default: "Aptitude").
        url_reuniones_custom: URL de agenda personalizada (default: None, usa el default de Aptitude).

    Returns:
        Asunto y cuerpo del correo redactado por Gemini.
    """
    # Si nadie pasó overrides explícitos de idioma/empresa/url, aplicá config de prueba si está activa
    if idioma == "es" and nombre_empresa_remitente == "Aptitude" and url_reuniones_custom is None:
        config_prueba = _obtener_config_prueba()
        if config_prueba.get("activo"):
            idioma = config_prueba.get("idioma", "es")
            nombre_empresa_remitente = config_prueba.get("empresa", "Aptitude")
            url_reuniones_custom = config_prueba.get("url_reuniones")

    user_content = (
        f"Destinatario: {nombre_destinatario}, cargo: {cargo}, empresa: {empresa}, "
        f"industria: {industria}. Investigación: {investigacion}. "
        f"Feedback del intento anterior a corregir: "
        f"{feedback_previo if feedback_previo else 'ninguno, es el primer intento'}."
    )

    if idioma != "es":
        user_content += " IMPORTANT: Write the entire email in English, not Spanish."

    if nombre_empresa_remitente != "Aptitude":
        user_content += f" IMPORTANT: This email is on behalf of {nombre_empresa_remitente}, NOT Aptitude — do not mention Aptitude or its client case studies, invent a plausible generic value proposition instead."

    if url_reuniones_custom:
        user_content += f" Use this meeting link in the closing instead of the default one: {url_reuniones_custom}"

    resultado, error = _generar_json_con_gemini(REDACTOR_SYSTEM_PROMPT, user_content)
    if error:
        return {"asunto": "", "cuerpo": "", "error": error}
    return {"asunto": resultado.get("asunto", ""), "cuerpo": resultado.get("cuerpo", "")}


SEGUIMIENTO_SYSTEM_PROMPT = """Eres Juan Carlos Hernández, Co-fundador y COO de Aptitude, una plataforma
que evalúa soft skills y personalidad para procesos de selección
en ~5 minutos. Vas a escribir un correo de SEGUIMIENTO (follow-up) muy breve
(máximo 60 palabras en el cuerpo), en español, tono cercano, profesional y sin presionar,
usando "tú"/"tienes" en vez de voseo, dirigido a un profesional de RRHH / Talent Acquisition.

Instrucciones:
1. Reconoce implícitamente que es un mensaje de seguimiento (por ejemplo "quería retomar mi mensaje anterior" o similar, sin sonar insistente ni repetitivo).
2. Si paso_secuencia es 3 (el último intento), el tono debe ser de "dejo la puerta abierta" sin presionar más si no es el momento oportuno.
3. Ofrece con naturalidad dos opciones para coordinar: responder a este correo o agendar directamente usando este enlace: https://meetings.hubspot.com/aptitude/demo (mantén el tono fluido y conversacional, no como una lista de opciones fría).
4. Firma exactamente con:
"Juan Carlos Hernández\\nCo-fundador & COO, Aptitude\\ntheaptitude.co"

Responde ÚNICAMENTE con JSON puro, sin backticks ni texto adicional:
{"asunto": "...", "cuerpo": "..."}"""


def redactar_seguimiento(nombre_destinatario: str, cargo: str, empresa: str,
                         industria: str, paso_secuencia: int,
                         feedback_previo: str = "", idioma: str = "es",
                         nombre_empresa_remitente: str = "Aptitude",
                         url_reuniones_custom: str = None) -> dict:
    """Redacta un correo de seguimiento personalizado y breve (máximo 60 palabras).

    Args:
        nombre_destinatario: Nombre de la persona a contactar.
        cargo: Cargo del destinatario.
        empresa: Nombre de la empresa.
        industria: Industria de la empresa.
        paso_secuencia: Número de paso en la secuencia (2 para primer seguimiento, 3 para último).
        feedback_previo: Feedback del intento anterior a corregir si aplica.
        idioma: "es" para español, "en" para inglés (default: "es").
        nombre_empresa_remitente: Nombre de la empresa que envía (default: "Aptitude").
        url_reuniones_custom: URL de agenda personalizada (default: None, usa el default de Aptitude).

    Returns:
        Asunto y cuerpo del correo redactado por Gemini.
    """
    # Si nadie pasó overrides explícitos de idioma/empresa/url, aplicá config de prueba si está activa
    if idioma == "es" and nombre_empresa_remitente == "Aptitude" and url_reuniones_custom is None:
        config_prueba = _obtener_config_prueba()
        if config_prueba.get("activo"):
            idioma = config_prueba.get("idioma", "es")
            nombre_empresa_remitente = config_prueba.get("empresa", "Aptitude")
            url_reuniones_custom = config_prueba.get("url_reuniones")

    user_content = (
        f"Destinatario: {nombre_destinatario}, cargo: {cargo}, empresa: {empresa}, "
        f"industria: {industria}. Paso de secuencia actual: {paso_secuencia} de 3. "
        f"Feedback del intento anterior a corregir: "
        f"{feedback_previo if feedback_previo else 'ninguno, es el primer intento'}."
    )

    if idioma != "es":
        user_content += " IMPORTANT: Write the entire email in English, not Spanish."

    if nombre_empresa_remitente != "Aptitude":
        user_content += f" IMPORTANT: This email is on behalf of {nombre_empresa_remitente}, NOT Aptitude — do not mention Aptitude or its client case studies, invent a plausible generic value proposition instead."

    if url_reuniones_custom:
        user_content += f" Use this meeting link in the closing instead of the default one: {url_reuniones_custom}"

    resultado, error = _generar_json_con_gemini(SEGUIMIENTO_SYSTEM_PROMPT, user_content)
    if error:
        return {"asunto": "", "cuerpo": "", "error": error}
    return {"asunto": resultado.get("asunto", ""), "cuerpo": resultado.get("cuerpo", "")}



def verificar_correo(asunto: str, cuerpo: str, investigacion: str,
                      dominio_email: str, empresa: str, intento: int) -> dict:
    """Audita un correo redactado antes de aprobarlo para envío, usando Gemini.

    Usa esta herramienta como último paso antes de decidir enviar o
    reintentar. Si Gemini falla al auditar, esta función RECHAZA por
    seguridad en vez de aprobar a ciegas.

    Args:
        asunto: Asunto del correo a verificar.
        cuerpo: Cuerpo del correo a verificar.
        investigacion: Texto de investigación original usado para redactar.
        dominio_email: Dominio del email del destinatario.
        empresa: Nombre de la empresa mencionada en el correo.
        intento: Número de intento actual (máximo 3).

    Returns:
        Si fue aprobado, y si no, la razón específica del rechazo.
    """
    user_content = (
        f"Correo generado - Asunto: {asunto}. Cuerpo: {cuerpo}. "
        f"Investigación real: {investigacion}. Dominio del email del "
        f"destinatario: {dominio_email}. Empresa: {empresa}. "
        f"Este es el intento número {intento} de 3."
    )
    resultado, error = _generar_json_con_gemini(VERIFICADOR_SYSTEM_PROMPT, user_content)
    if error:
        return {"aprobado": False, "razon": f"No se pudo auditar el correo: {error}"}
    return {
        "aprobado": bool(resultado.get("aprobado", False)),
        "razon": resultado.get("razon", ""),
    }


# ---------------------------------------------------------------------------
# Microsoft Graph (Outlook)
# ---------------------------------------------------------------------------

def _obtener_token_graph():
    tenant_id = os.environ.get("MICROSOFT_TENANT_ID")
    client_id = os.environ.get("MICROSOFT_CLIENT_ID")
    client_secret = os.environ.get("MICROSOFT_CLIENT_SECRET")
    if not all([tenant_id, client_id, client_secret]):
        return None, "Faltan variables de entorno de Microsoft Graph"

    try:
        import msal
        app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        resultado = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
    except Exception as e:
        return None, str(e)

    token = resultado.get("access_token")
    if not token:
        return None, resultado.get("error_description", "Token no recibido")
    return token, None


def _enviar_correo_graph(destinatario_email: str, asunto: str, cuerpo_texto: str) -> dict:
    token, error = _obtener_token_graph()
    if error:
        return {"status": "error", "error": error}

    mailbox = os.environ.get("MICROSOFT_MAILBOX", "")
    cuerpo_html = html.escape(cuerpo_texto).replace("\n", "<br>")

    body = {
        "message": {
            "subject": asunto,
            "body": {"contentType": "HTML", "content": cuerpo_html},
            "toRecipients": [{"emailAddress": {"address": destinatario_email}}],
        }
    }

    try:
        resp = requests.post(
            f"https://graph.microsoft.com/v1.0/users/{mailbox}/sendMail",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body, timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"status": "error", "error": str(e)}

    return {"status": "enviado", "destinatario": destinatario_email}


def enviar_correo(destinatario_email: str, asunto: str, cuerpo: str) -> dict:
    """Envía el correo ya aprobado por verificar_correo, vía Outlook (Microsoft Graph).

    Usa esta herramienta SOLO después de que verificar_correo haya devuelto
    aprobado=True para ese correo.

    Prioridad de destinatario (en orden):
    1. TEST_OVERRIDE_EMAIL si está definida en el entorno
    2. Email de prueba dinámico si el modo de prueba está activo
    3. Destinatario real

    Args:
        destinatario_email: Email del destinatario.
        asunto: Asunto ya verificado.
        cuerpo: Cuerpo ya verificado.

    Returns:
        Confirmación de envío, o status de error si falla.
    """
    # Salvaguarda: si esto es una instancia de demo exclusiva, requiere modo de prueba activo
    if os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true":
        config_prueba = _obtener_config_prueba()
        if not config_prueba.get("activo"):
            return {"status": "error", "error": "No se puede enviar: esta es una instancia de demo, activá el modo de prueba primero con tu email"}

    # Prioridad 1: TEST_OVERRIDE_EMAIL del entorno
    test_override = os.environ.get("TEST_OVERRIDE_EMAIL")
    if test_override:
        return _enviar_correo_graph(test_override, asunto, cuerpo)

    # Prioridad 2: Modo de prueba dinámico
    config_prueba = _obtener_config_prueba()
    if config_prueba.get("activo"):
        return _enviar_correo_graph(config_prueba.get("email_prueba"), asunto, cuerpo)

    # Prioridad 3: Destinatario real
    return _enviar_correo_graph(destinatario_email, asunto, cuerpo)


def marcar_para_revision_humana(nombre_destinatario: str, apellido: str,
                                 cargo: str, empresa: str, industria: str,
                                 email: str, asunto: str, cuerpo: str,
                                 razon_rechazo: str, es_reintento: bool = False) -> dict:
    """Escala un lead para revisión humana y guarda registro persistente en Sheets.

    Escala un lead cuando hay rechazo de correo, exclusión, o contacto previo.
    Envía notificación por Outlook y guarda registro en pestaña "Pendientes de
    Aprobación" de Google Sheets.

    Args:
        nombre_destinatario: Nombre de la persona de contacto.
        apellido: Apellido de la persona.
        cargo: Cargo del destinatario.
        empresa: Nombre de la empresa.
        industria: Industria de la empresa.
        email: Email del destinatario.
        asunto: Asunto del correo (o "N/A" si no hay).
        cuerpo: Cuerpo del correo (o "N/A" si no hay).
        razon_rechazo: Motivo de la escalación.
        es_reintento: True si es un reintento de un lead rechazado previamente.
            Si True, marca la fila con Retried="SI" para evitar reintentos futuros.

    Returns:
        Confirmación de que quedó marcado para revisión, o status de error.
    """
    es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"

    # Enviar notificación por Outlook
    mailbox = os.environ.get("MICROSOFT_MAILBOX", "")

    # Textos condicionales según es_demo
    if es_demo:
        intro_text = "Lead pending manual review."
        empresa_label = "Company:"
        destinatario_label = "Recipient:"
        cargo_label = "Position:"
        industria_label = "Industry:"
        motivo_label = "Reason:"
        asunto_label = "Subject:"
        cuerpo_label = "Body:"
        correo_subject = f"Approve email for {empresa}"
    else:
        intro_text = "Lead pendiente de revisión manual."
        empresa_label = "Empresa:"
        destinatario_label = "Destinatario:"
        cargo_label = "Cargo:"
        industria_label = "Industria:"
        motivo_label = "Motivo:"
        asunto_label = "Asunto:"
        cuerpo_label = "Cuerpo:"
        correo_subject = f"Aprobar correo para {empresa}"

    cuerpo_notificacion = (
        f"{intro_text}\n\n"
        f"{empresa_label} {empresa}\n{destinatario_label} {nombre_destinatario} {apellido} <{email}>\n"
        f"{cargo_label} {cargo}\n{industria_label} {industria}\n"
        f"{motivo_label} {razon_rechazo}\n\n"
        f"{asunto_label} {asunto}\n{cuerpo_label}:\n{cuerpo}"
    )
    resultado_email = _enviar_correo_graph(
        mailbox, correo_subject, cuerpo_notificacion
    )

    # Guardar registro en Google Sheets
    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if credenciales_json and sheet_id:
        try:
            import gspread
            credenciales_dict = json.loads(credenciales_json)
            gc = gspread.service_account_from_dict(credenciales_dict)
            hoja_principal = gc.open_by_key(sheet_id)

            # Intentar abrir pestaña "Pending Approval" o "Pendientes de Aprobación", crear si no existe
            nombre_pestaña = "Pending Approval" if es_demo else "Pendientes de Aprobación"
            try:
                hoja = hoja_principal.worksheet(nombre_pestaña)
            except gspread.exceptions.WorksheetNotFound:
                hoja = hoja_principal.add_worksheet(
                    title=nombre_pestaña, rows=100, cols=13
                )
                hoja.append_row([
                    "Date", "Name", "Last Name", "Position", "Company", "Industry",
                    "Email", "Subject", "Body", "Reason", "Approved", "Sent", "Retried"
                ])

            # Agregar fila con datos del lead
            retried_value = "SI" if es_reintento else "NO"
            fila = [
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                nombre_destinatario, apellido, cargo, empresa, industria,
                email, asunto, cuerpo, razon_rechazo, "NO", "NO", retried_value,
            ]
            hoja.append_row(fila)
        except Exception as e:
            # Fail-open: loguear pero no romper
            logger_info = f"Error guardando en Sheets: {e}"
            pass

    if resultado_email.get("status") == "error":
        return resultado_email
    return {"status": "pendiente_revision", "contacto": email}


# ---------------------------------------------------------------------------
# Google Sheets (sustituto temporal de HubSpot)
# ---------------------------------------------------------------------------

def marcar_enviado_en_aprobaciones(email: str, empresa: str = None) -> dict:
    """Marca una fila como enviada (Approved/Sent) sin reenviar nada.

    Busca la fila en "Pending Approval" o "Pendientes de Aprobación" que coincida con
    el email (y opcionalmente empresa), y actualiza SOLO las columnas Approved y Sent
    a YES/SI según es_demo, sin llamar a revisar_aprobaciones_pendientes() ni enviar
    ningún correo. Útil para marcar coherente el registro de una exclusión que fue
    enviada manualmente.

    Args:
        email: Email del contacto a marcar como enviado.
        empresa: Nombre de la empresa (para confirmar coincidencia, opcional).

    Returns:
        {"status": "actualizado", "email": email} si se encontró y actualizó,
        {"status": "no_encontrado", "email": email} si no existe la fila.
    """
    es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"

    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not credenciales_json or not sheet_id:
        return {"status": "error", "error": "Faltan credenciales de Sheets"}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)

        nombre_pestaña = "Pending Approval" if es_demo else "Pendientes de Aprobación"
        hoja = hoja_principal.worksheet(nombre_pestaña)

        # Obtener header para encontrar índices
        header = hoja.row_values(1)
        idx_email = header.index("Email") + 1 if "Email" in header else None
        idx_company = header.index("Company") + 1 if "Company" in header else None
        idx_approved = header.index("Approved") + 1 if "Approved" in header else None
        idx_sent = header.index("Sent") + 1 if "Sent" in header else None

        if not idx_email or not idx_approved or not idx_sent:
            return {"status": "error", "error": "Columnas Email, Approved o Sent no encontradas"}

        # Buscar fila que coincida con email (y opcionalmente empresa)
        filas = hoja.get_all_values()
        fila_encontrada = None
        num_fila_encontrada = None

        for num_fila, fila in enumerate(filas[1:], start=2):
            email_fila = fila[idx_email - 1].strip() if idx_email <= len(fila) else ""
            if email_fila.lower() == email.lower():
                # Si se proporciona empresa, confirmar que coincida
                if empresa:
                    empresa_fila = fila[idx_company - 1].strip() if idx_company and idx_company <= len(fila) else ""
                    if empresa_fila.lower() == empresa.lower():
                        fila_encontrada = fila
                        num_fila_encontrada = num_fila
                        break
                else:
                    # Sin empresa, la primera coincidencia de email es suficiente
                    fila_encontrada = fila
                    num_fila_encontrada = num_fila
                    break

        if not fila_encontrada:
            return {"status": "no_encontrado", "email": email}

        # Actualizar SOLO Approved y Sent a YES/SI según es_demo
        approved_value = "YES" if es_demo else "SI"
        sent_value = "YES" if es_demo else "SI"
        hoja.update_cell(num_fila_encontrada, idx_approved, approved_value)
        hoja.update_cell(num_fila_encontrada, idx_sent, sent_value)

        return {"status": "actualizado", "email": email}

    except Exception as e:
        return {"status": "error", "error": str(e)}


def aprobar_y_enviar(empresa: str, email: str) -> dict:
    """Aprueba y envía inmediatamente un lead escalado encontrando su fila en Sheets.

    Busca la fila en "Pending Approval" o "Pendientes de Aprobación" que coincida con
    el email (y opcionalmente empresa), la marca como aprobada (Approved=YES/SI según
    es_demo), y luego ejecuta revisar_aprobaciones_pendientes() para enviarla de
    inmediato.

    Args:
        empresa: Nombre de la empresa (para confirmar coincidencia, opcional).
        email: Email del contacto a buscar y aprobar.

    Returns:
        Resultado de revisar_aprobaciones_pendientes() si se encontró y aprobó,
        {"status": "no_encontrado", "email": email} si no existe la fila.
    """
    es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"

    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not credenciales_json or not sheet_id:
        return {"status": "error", "error": "Faltan credenciales de Sheets"}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)

        nombre_pestaña = "Pending Approval" if es_demo else "Pendientes de Aprobación"
        hoja = hoja_principal.worksheet(nombre_pestaña)

        # Obtener header para encontrar índices
        header = hoja.row_values(1)
        idx_email = header.index("Email") + 1 if "Email" in header else None
        idx_company = header.index("Company") + 1 if "Company" in header else None
        idx_approved = header.index("Approved") + 1 if "Approved" in header else None

        if not idx_email or not idx_approved:
            return {"status": "error", "error": "Columnas Email o Approved no encontradas"}

        # Buscar fila que coincida con email (y opcionalmente empresa)
        filas = hoja.get_all_values()
        fila_encontrada = None
        num_fila_encontrada = None

        for num_fila, fila in enumerate(filas[1:], start=2):
            email_fila = fila[idx_email - 1].strip() if idx_email <= len(fila) else ""
            if email_fila.lower() == email.lower():
                # Si se proporciona empresa, confirmar que coincida
                if empresa:
                    empresa_fila = fila[idx_company - 1].strip() if idx_company and idx_company <= len(fila) else ""
                    if empresa_fila.lower() == empresa.lower():
                        fila_encontrada = fila
                        num_fila_encontrada = num_fila
                        break
                else:
                    # Sin empresa, la primera coincidencia de email es suficiente
                    fila_encontrada = fila
                    num_fila_encontrada = num_fila
                    break

        if not fila_encontrada:
            return {"status": "no_encontrado", "email": email}

        # Actualizar Approved a YES/SI según es_demo
        approved_value = "YES" if es_demo else "SI"
        hoja.update_cell(num_fila_encontrada, idx_approved, approved_value)

        # Llamar a revisar_aprobaciones_pendientes para procesar el envío
        resultado_revision = revisar_aprobaciones_pendientes()
        return resultado_revision

    except Exception as e:
        return {"status": "error", "error": str(e)}


def revisar_aprobaciones_pendientes() -> dict:
    """Procesa leads aprobados en la pestaña "Pendientes de Aprobación" / "Pending Approval".

    Lee la hoja de pendientes y para cada lead aprobado (Approved=SI/YES) que no
    ha sido enviado (Sent=NO), envía el correo, actualiza el estado, y registra
    en HubSpot.

    Returns:
        {"procesados": N, "enviados": [lista de empresas], "errores": [lista]}
    """
    es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"

    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not credenciales_json or not sheet_id:
        return {"procesados": 0, "enviados": [], "errores": ["Faltan credenciales"]}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)

        nombre_pestaña = "Pending Approval" if es_demo else "Pendientes de Aprobación"
        hoja = hoja_principal.worksheet(nombre_pestaña)

        # Obtener header para encontrar índices de columnas
        header = hoja.row_values(1)
        idx_approved = header.index("Approved") + 1 if "Approved" in header else None
        idx_sent = header.index("Sent") + 1 if "Sent" in header else None
        idx_name = header.index("Name") + 1 if "Name" in header else None
        idx_last_name = header.index("Last Name") + 1 if "Last Name" in header else None
        idx_company = header.index("Company") + 1 if "Company" in header else None
        idx_email = header.index("Email") + 1 if "Email" in header else None
        idx_subject = header.index("Subject") + 1 if "Subject" in header else None
        idx_body = header.index("Body") + 1 if "Body" in header else None
        idx_position = header.index("Position") + 1 if "Position" in header else None
        idx_industry = header.index("Industry") + 1 if "Industry" in header else None

        filas = hoja.get_all_values()
        procesados = 0
        enviados = []
        errores = []

        # Procesar desde fila 2 (saltar header)
        for num_fila, fila in enumerate(filas[1:], start=2):
            try:
                # Verificar si está aprobado y no enviado
                approved = fila[idx_approved - 1].strip().upper() if idx_approved <= len(fila) else ""
                sent = fila[idx_sent - 1].strip().upper() if idx_sent <= len(fila) else ""

                if approved in ("SI", "YES") and sent == "NO":
                    # Extraer datos de la fila
                    nombre = fila[idx_name - 1] if idx_name <= len(fila) else ""
                    apellido = fila[idx_last_name - 1] if idx_last_name <= len(fila) else ""
                    empresa = fila[idx_company - 1] if idx_company <= len(fila) else ""
                    email_dest = fila[idx_email - 1] if idx_email <= len(fila) else ""
                    asunto = fila[idx_subject - 1] if idx_subject <= len(fila) else ""
                    cuerpo = fila[idx_body - 1] if idx_body <= len(fila) else ""
                    cargo = fila[idx_position - 1] if idx_position <= len(fila) else ""
                    industria = fila[idx_industry - 1] if idx_industry <= len(fila) else ""

                    # Enviar correo
                    destinatario_real = os.environ.get("TEST_OVERRIDE_EMAIL") or email_dest
                    resultado_envio = _enviar_correo_graph(destinatario_real, asunto, cuerpo)

                    if resultado_envio.get("status") == "enviado":
                        procesados += 1
                        enviados.append(empresa)

                        # Actualizar Sent a "YES" (si es_demo) o "SI" (si no)
                        sent_value = "YES" if es_demo else "SI"
                        hoja.update_cell(num_fila, idx_sent, sent_value)

                        # Registrar en HubSpot (hoja principal)
                        try:
                            crear_negocio_hubspot(nombre, apellido, cargo, empresa,
                                                industria, email_dest)
                        except Exception as e:
                            errores.append(f"Fila {num_fila} ({empresa}): error al registrar en HubSpot - {e}")
                    else:
                        errores.append(f"Fila {num_fila} ({empresa}): error al enviar correo")

            except Exception as e:
                errores.append(f"Fila {num_fila}: error procesando - {e}")
                continue

        return {"procesados": procesados, "enviados": enviados, "errores": errores}

    except Exception as e:
        return {"procesados": 0, "enviados": [], "errores": [f"Error general: {e}"]}


def buscar_rechazados_para_reintentar() -> dict:
    """Busca correos rechazados hace más de 7 días para reintentar.

    Identifica leads que fueron rechazados por el verificador pero no por
    exclusión ni contacto previo. Si más de 7 días han pasado, pueden
    reintentarse (ej. si la empresa cambió de política o datos). Marca cada
    caso encontrado como "Retried" para evitar reintentos infinitos.

    Returns:
        {"leads": [{"nombre", "apellido", "cargo", "empresa", "industria",
                    "email"}, ...]} con leads listos para reintentar, o
        {"leads": []} si falla la conexión o no hay candidatos.
    """
    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not credenciales_json or not sheet_id:
        return {"leads": []}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)

        try:
            hoja = hoja_principal.worksheet("Pendientes de Aprobación")
        except gspread.exceptions.WorksheetNotFound:
            return {"leads": []}

        # Verificar/crear columna Retried (columna M, índice 13)
        header = hoja.row_values(1)
        if "Retried" not in header:
            hoja.resize(cols=13)
            hoja.update_cell(1, 13, "Retried")
            header.insert(12, "Retried")  # Actualizar header local

        # Encontrar índices de columnas
        idx_date = header.index("Date") + 1 if "Date" in header else None
        idx_reason = header.index("Reason") + 1 if "Reason" in header else None
        idx_approved = header.index("Approved") + 1 if "Approved" in header else None
        idx_retried = header.index("Retried") + 1 if "Retried" in header else None
        idx_name = header.index("Name") + 1 if "Name" in header else None
        idx_last_name = header.index("Last Name") + 1 if "Last Name" in header else None
        idx_position = header.index("Position") + 1 if "Position" in header else None
        idx_company = header.index("Company") + 1 if "Company" in header else None
        idx_industry = header.index("Industry") + 1 if "Industry" in header else None
        idx_email = header.index("Email") + 1 if "Email" in header else None

        if not all([idx_date, idx_reason, idx_approved, idx_retried]):
            return {"leads": []}

        filas = hoja.get_all_values()
        leads_para_reintentar = []
        ahora = datetime.now(timezone.utc)
        hace_7_dias = ahora - timedelta(days=7)

        # Procesar desde fila 2 (saltar header)
        for num_fila, fila in enumerate(filas[1:], start=2):
            try:
                # Extraer valores
                fecha_str = fila[idx_date - 1] if idx_date <= len(fila) else ""
                reason = fila[idx_reason - 1].lower() if idx_reason <= len(fila) else ""
                approved = fila[idx_approved - 1].strip().upper() if idx_approved <= len(fila) else ""
                retried = fila[idx_retried - 1].strip().upper() if idx_retried <= len(fila) else ""

                # Parsear fecha (formato: "%Y-%m-%d %H:%M UTC")
                try:
                    fecha_obj = datetime.strptime(fecha_str.replace(" UTC", ""), "%Y-%m-%d %H:%M")
                    fecha_obj = fecha_obj.replace(tzinfo=timezone.utc)
                except Exception:
                    continue

                # Verificar criterios
                if (reason and "rechazado" in reason and
                    "exclusión" not in reason and "contactada anteriormente" not in reason and
                    approved != "SI" and retried != "SI" and fecha_obj < hace_7_dias):

                    # Extraer datos del lead
                    nombre = fila[idx_name - 1] if idx_name <= len(fila) else ""
                    apellido = fila[idx_last_name - 1] if idx_last_name <= len(fila) else ""
                    cargo = fila[idx_position - 1] if idx_position <= len(fila) else ""
                    empresa = fila[idx_company - 1] if idx_company <= len(fila) else ""
                    industria = fila[idx_industry - 1] if idx_industry <= len(fila) else ""
                    email = fila[idx_email - 1] if idx_email <= len(fila) else ""

                    # Marcar inmediatamente como Retried (salvaguarda)
                    hoja.update_cell(num_fila, idx_retried, "SI")

                    # Agregar a lista de reintentos
                    leads_para_reintentar.append({
                        "nombre": nombre,
                        "apellido": apellido,
                        "cargo": cargo,
                        "empresa": empresa,
                        "industria": industria,
                        "email": email,
                    })

            except Exception:
                continue

        return {"leads": leads_para_reintentar}

    except Exception:
        return {"leads": []}


def generar_reporte_diario() -> dict:
    """Genera un reporte diario de actividad de prospección.

    Cuenta leads por estado desde "Leads Enviados" y pendientes por aprobar
    desde "Pendientes de Aprobación".

    Returns:
        {"total_leads": N, "respondieron": N, "no_interesados": N, "rebotaron": N,
         "cerrados_sin_respuesta": N, "sin_novedad": N, "pendientes_aprobacion": N}
        Con ceros en todo si falla la conexión (fail-open).
    """
    resultado = {
        "total_leads": 0,
        "respondieron": 0,
        "no_interesados": 0,
        "rebotaron": 0,
        "cerrados_sin_respuesta": 0,
        "sin_novedad": 0,
        "pendientes_aprobacion": 0,
    }

    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    if not credenciales_json or not sheet_id:
        return resultado

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)

        # Contar en "Leads Enviados"
        try:
            hoja_leads = hoja_principal.worksheet("Leads Enviados")
            header = hoja_leads.row_values(1)
            idx_estado = header.index("Estado") + 1 if "Estado" in header else None

            if idx_estado:
                filas = hoja_leads.get_all_values()
                resultado["total_leads"] = len(filas) - 1  # Restar header

                for fila in filas[1:]:
                    estado = fila[idx_estado - 1].strip() if idx_estado <= len(fila) else ""
                    if estado == "Respondió":
                        resultado["respondieron"] += 1
                    elif estado == "No interesado":
                        resultado["no_interesados"] += 1
                    elif estado == "Rebotó":
                        resultado["rebotaron"] += 1
                    elif estado == "Cerrado sin respuesta":
                        resultado["cerrados_sin_respuesta"] += 1
                    elif estado == "":
                        resultado["sin_novedad"] += 1
        except Exception:
            pass

        # Contar en "Pendientes de Aprobación"
        try:
            hoja_pendientes = hoja_principal.worksheet("Pendientes de Aprobación")
            header = hoja_pendientes.row_values(1)
            idx_approved = header.index("Approved") + 1 if "Approved" in header else None
            idx_sent = header.index("Sent") + 1 if "Sent" in header else None

            if idx_approved and idx_sent:
                filas = hoja_pendientes.get_all_values()
                for fila in filas[1:]:
                    approved = fila[idx_approved - 1].strip().upper() if idx_approved <= len(fila) else ""
                    sent = fila[idx_sent - 1].strip().upper() if idx_sent <= len(fila) else ""
                    if approved != "SI" and sent != "SI":
                        resultado["pendientes_aprobacion"] += 1
        except Exception:
            pass

        return resultado

    except Exception:
        return resultado


def enviar_reporte_por_correo(cuerpo_reporte: str, destinatario_email: str = None) -> dict:
    """Envía un reporte de prospección por correo.

    Args:
        cuerpo_reporte: Texto del reporte a enviar.
        destinatario_email: Email destinatario. Si es None, se envía a MICROSOFT_MAILBOX.

    Returns:
        Resultado de _enviar_correo_graph ({"status": "enviado"} o error).
    """
    if destinatario_email is None:
        destinatario_email = os.environ.get("MICROSOFT_MAILBOX", "")

    fecha_hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    asunto = f"Reporte de prospección — {fecha_hoy}"

    return _enviar_correo_graph(destinatario_email, asunto, cuerpo_reporte)


def verificar_lista_exclusion(email: str, empresa: str) -> dict:
    """Verifica si un contacto o empresa está en la lista manual de exclusión.

    Permite al usuario mantener una lista de contactos y empresas explícitamente
    excluidos que no deben ser contactados, sin importar otros criterios.

    Args:
        email: Email del contacto a verificar.
        empresa: Nombre de la empresa a verificar.

    Returns:
        {"excluido": True} si el email o la empresa están en la lista de exclusión,
        {"excluido": False} en caso contrario o si hay error de lectura.
    """
    es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"

    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not credenciales_json or not sheet_id:
        return {"excluido": False}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)

        # a) Verificar email en pestaña "Excluidos"
        try:
            hoja_emails = hoja_principal.worksheet("Excluidos")
            emails = hoja_emails.col_values(1)
            email_normalizado = (email or "").strip().lower()
            if email_normalizado:
                for emp in emails[1:]:  # Skip header
                    if emp.strip().lower() == email_normalizado:
                        return {"excluido": True}
        except Exception:
            pass

        # b) Verificar empresa en pestaña "Empresas Excluidas" / "Excluded Companies"
        try:
            nombre_pestaña = "Excluded Companies" if es_demo else "Empresas Excluidas"
            nombre_columna = "Company" if es_demo else "Empresa"
            try:
                hoja_empresas = hoja_principal.worksheet(nombre_pestaña)
            except gspread.exceptions.WorksheetNotFound:
                hoja_empresas = gc.open_by_key(sheet_id).add_worksheet(
                    title=nombre_pestaña, rows=100, cols=20
                )
                hoja_empresas.append_row([nombre_columna])

            header = hoja_empresas.row_values(1)
            col_idx = header.index(nombre_columna) + 1 if nombre_columna in header else 1
            empresas_excluidas = hoja_empresas.col_values(col_idx)

            empresa_normalizada = (empresa or "").strip().lower()
            if empresa_normalizada:
                for emp_val in empresas_excluidas[1:]:  # Skip header
                    val = emp_val.strip().lower()
                    if val and (val in empresa_normalizada or empresa_normalizada in val):
                        return {"excluido": True}
        except Exception:
            pass

        return {"excluido": False}
    except Exception:
        return {"excluido": False}


def verificar_contactado_previamente(empresa: str) -> dict:
    """Verifica si una empresa fue contactada hace menos de 3 días hábiles.

    Busca TODAS las filas con esa empresa, obtiene la más reciente, y devuelve
    ya_contactado=True solo si pasaron MENOS de 3 días hábiles desde ese contacto.
    Si pasaron 3+ días hábiles, permite un nuevo contacto.

    Args:
        empresa: Nombre de la empresa a verificar.

    Returns:
        {"ya_contactado": True} si la empresa fue contactada hace <3 días hábiles,
        {"ya_contactado": False} si no hay registros o ya pasaron 3+ días hábiles.
    """
    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not credenciales_json or not sheet_id:
        return {"ya_contactado": False}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja = gc.open_by_key(sheet_id).sheet1

        # Obtener header para encontrar columnas de "Company" y "Date"
        header = hoja.row_values(1)
        if "Company" not in header or "Date" not in header:
            return {"ya_contactado": False}

        col_company = header.index("Company") + 1
        col_date = header.index("Date") + 1

        # Traer todos los valores
        filas = hoja.get_all_values()

        # Buscar TODAS las filas que coincidan con la empresa
        empresa_normalizada = empresa.strip().lower()
        fecha_mas_reciente = None
        for fila in filas[1:]:  # Skip header
            if col_company <= len(fila):
                emp = fila[col_company - 1].strip().lower()
                if emp == empresa_normalizada:
                    if col_date <= len(fila):
                        fecha_str = fila[col_date - 1]
                        if not fecha_mas_reciente or fecha_str > fecha_mas_reciente:
                            fecha_mas_reciente = fecha_str

        # Si no hay registros, permitir contacto
        if fecha_mas_reciente is None:
            return {"ya_contactado": False}

        # Verificar si pasaron >= 3 días hábiles
        if _hace_n_dias_habiles(fecha_mas_reciente, 3):
            return {"ya_contactado": False}
        else:
            return {"ya_contactado": True}

    except Exception:
        return {"ya_contactado": False}


def crear_negocio_hubspot(nombre_destinatario: str, apellido: str, cargo: str, empresa: str,
                           industria: str, email: str) -> dict:
    """Registra el lead con correo aprobado en una hoja de Google Sheets.

    NOTA: pese al nombre, esto NO escribe en HubSpot real — es un registro
    temporal en Google Sheets para no mezclar datos de prueba del hackathon
    con el pipeline de producción de Aptitude en HubSpot.

    Usa esta herramienta como ÚLTIMO paso, solo después de que
    verificar_correo haya aprobado el correo de ese lead.

    Args:
        nombre_destinatario: Nombre de la persona de contacto.
        apellido: Apellido de la persona.
        cargo: Cargo del destinatario.
        empresa: Nombre de la empresa.
        industria: Industria de la empresa.
        email: Email del destinatario.

    Returns:
        Confirmación de registro con el número de fila, o status de error.
    """
    # Determinar si es instancia demo exclusiva
    es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"

    # Determinar nombre de pestaña según modo de prueba y tipo de instancia
    config_prueba = _obtener_config_prueba()
    if es_demo:
        nombre_pestaña = "Sent Leads"
    else:
        nombre_pestaña = "Leads Enviados (Test)" if config_prueba.get("activo") else "Leads Enviados"

    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not credenciales_json or not sheet_id:
        return {"status": "error", "error": "Faltan variables de Google Sheets"}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)
        try:
            hoja = hoja_principal.worksheet(nombre_pestaña)
        except gspread.exceptions.WorksheetNotFound:
            hoja = hoja_principal.add_worksheet(title=nombre_pestaña, rows=100, cols=20)
            if es_demo:
                header = ["Date", "Name", "Last Name", "Position", "Company", "Industry", "Email", "First Contact", "Status"]
            else:
                header = [
                    "Fecha", "Nombre", "Apellido", "Cargo", "Empresa", "Industria",
                    "Email", "Primer Contacto", "Estado", "Paso Secuencia", "Próximo Contacto"
                ]
            hoja.append_row(header)
        except Exception:
            hoja = hoja_principal.sheet1

        header = hoja.row_values(1)
        if not header:
            if es_demo:
                header = ["Date", "Name", "Last Name", "Position", "Company", "Industry", "Email", "First Contact", "Status"]
            else:
                header = [
                    "Fecha", "Nombre", "Apellido", "Cargo", "Empresa", "Industria",
                    "Email", "Primer Contacto", "Estado", "Paso Secuencia", "Próximo Contacto"
                ]
            hoja.append_row(header)
        else:
            if not es_demo:
                columnas_requeridas = ["Paso Secuencia", "Próximo Contacto"]
                if any(col not in header for col in columnas_requeridas):
                    hoja.resize(cols=max(len(header) + 5, 20))
                    for col in columnas_requeridas:
                        if col not in header:
                            hoja.update_cell(1, len(header) + 1, col)
                            header.append(col)

        # Construir fila completa mapeada dinámicamente según encabezados
        fila_completa = [""] * len(header)

        ahora = datetime.now(timezone.utc)
        fecha_str = ahora.strftime("%Y-%m-%d %H:%M UTC")
        proximo_contacto_str = (ahora + timedelta(days=5)).strftime("%Y-%m-%d %H:%M UTC")

        def _obtener_indice(nombres_posibles):
            for n in nombres_posibles:
                if n in header:
                    return header.index(n) + 1
            return None

        valor_primer_contacto = "Email sent" if es_demo else "Correo enviado"
        campos = [
            (["Fecha", "Date"], fecha_str),
            (["Nombre", "Name"], nombre_destinatario),
            (["Apellido", "Last Name"], apellido),
            (["Cargo", "Position"], cargo),
            (["Empresa", "Company"], empresa),
            (["Industria", "Industry"], industria),
            (["Email"], email),
            (["Primer Contacto", "First Contact"], valor_primer_contacto),
        ]
        if not es_demo:
            campos.extend([
                (["Paso Secuencia", "Sequence Step"], 1),
                (["Próximo Contacto", "Next Contact"], proximo_contacto_str),
            ])

        for nombres, valor in campos:
            idx = _obtener_indice(nombres)
            if idx:
                fila_completa[idx - 1] = valor

        # Agregar la fila completa en una sola llamada
        hoja.append_row(fila_completa)
        num_fila = len(hoja.get_all_values())

    except Exception as e:
        return {"status": "error", "error": str(e)}

    return {"status": "creado", "fila": num_fila, "contacto": email}


def revisar_respuestas_bandeja() -> dict:
    """Revisa la bandeja de entrada para detectar rebotes y respuestas de prospectos.

    Consulta los correos no leídos vía Microsoft Graph, identifica rebotes o
    respuestas de leads existentes en la hoja principal "Leads Enviados", clasifica
    el interés de la respuesta usando Gemini, actualiza el estado en Google Sheets
    y marca los correos procesados como leídos.

    Returns:
        {"revisados": N, "rebotes": [...], "respuestas": [...], "no_interesados": [...]}
    """
    es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"

    token, error = _obtener_token_graph()
    if error or not token:
        return {"revisados": 0, "rebotes": [], "respuestas": [], "no_interesados": []}

    mailbox = os.environ.get("MICROSOFT_MAILBOX", "")
    if not mailbox:
        return {"revisados": 0, "rebotes": [], "respuestas": [], "no_interesados": []}

    # Obtener correos no leídos de la bandeja de entrada
    try:
        url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/mailFolders/inbox/messages"
        params = {
            "$filter": "isRead eq false",
            "$select": "id,subject,from,body,receivedDateTime",
            "$orderby": "receivedDateTime asc",
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        mensajes = resp.json().get("value", [])
    except Exception:
        return {"revisados": 0, "rebotes": [], "respuestas": [], "no_interesados": []}

    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")

    hoja = None
    idx_estado = None
    emails_en_hoja = []

    if credenciales_json and sheet_id:
        try:
            import gspread
            credenciales_dict = json.loads(credenciales_json)
            gc = gspread.service_account_from_dict(credenciales_dict)
            hoja_principal = gc.open_by_key(sheet_id)
            nombre_pestaña = "Sent Leads" if es_demo else "Leads Enviados"
            try:
                hoja = hoja_principal.worksheet(nombre_pestaña)
            except Exception:
                hoja = hoja_principal.sheet1

            header = hoja.row_values(1)
            col_nombre_estado = "Status" if es_demo else "Estado"
            if col_nombre_estado not in header:
                hoja.resize(cols=max(len(header) + 5, 15))
                idx_estado = len(header) + 1
                hoja.update_cell(1, idx_estado, col_nombre_estado)
                header.append(col_nombre_estado)
            else:
                idx_estado = header.index(col_nombre_estado) + 1

            idx_email = (header.index("Email") + 1) if "Email" in header else 7
            emails_en_hoja = [e.strip().lower() for e in hoja.col_values(idx_email)]
        except Exception:
            hoja = None

    palabras_rebote = [
        "mailer-daemon", "postmaster", "undeliverable",
        "no pudo entregarse", "delivery status notification", "returned mail"
    ]

    revisados = 0
    rebotes = []
    respuestas = []
    no_interesados = []

    for msg in mensajes:
        try:
            msg_id = msg.get("id")
            asunto = msg.get("subject", "") or ""
            from_obj = msg.get("from", {}).get("emailAddress", {})
            remitente_email = (from_obj.get("address", "") or "").strip().lower()
            remitente_nombre = (from_obj.get("name", "") or "").strip().lower()
            cuerpo_obj = msg.get("body", {})
            cuerpo_raw = cuerpo_obj.get("content", "") or ""
            cuerpo_texto = re.sub(r"<[^>]+>", " ", cuerpo_raw)
            cuerpo_texto = html.unescape(cuerpo_texto).strip()

            texto_evaluar = f"{remitente_email} {remitente_nombre} {asunto}".lower()
            es_rebote = any(p in texto_evaluar for p in palabras_rebote)

            if es_rebote:
                # Extraer email original del cuerpo
                emails_en_cuerpo = re.findall(
                    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", cuerpo_texto
                )
                email_objetivo = None
                fila_match = None

                if hoja and emails_en_hoja:
                    for email_cand in emails_en_cuerpo:
                        cand_norm = email_cand.strip().lower()
                        if cand_norm == mailbox.lower():
                            continue
                        for row_idx, e_sheet in enumerate(emails_en_hoja[1:], start=2):
                            if e_sheet and e_sheet == cand_norm:
                                email_objetivo = cand_norm
                                fila_match = row_idx
                                break
                        if fila_match:
                            break

                    if fila_match and idx_estado:
                        estado_rebote = "Bounced" if es_demo else "Rebotó"
                        hoja.update_cell(fila_match, idx_estado, estado_rebote)

                rebote_identificado = email_objetivo or (emails_en_cuerpo[0] if emails_en_cuerpo else remitente_email)
                rebotes.append(rebote_identificado)

            else:
                # Verificar si el remitente coincide con algún lead enviado
                fila_match = None
                if hoja and emails_en_hoja and remitente_email:
                    for row_idx, e_sheet in enumerate(emails_en_hoja[1:], start=2):
                        if e_sheet and e_sheet == remitente_email:
                            fila_match = row_idx
                            break

                if fila_match:
                    # Clasificar respuesta con Gemini
                    prompt_clasificacion = (
                        "Analiza el cuerpo del siguiente correo de respuesta a un mensaje de prospección B2B. "
                        "Determina si el remitente NO está interesado. Esto incluye: rechazos explícitos (dice que no le interesa, "
                        "pide que no le escriban más), Y TAMBIÉN respuestas mínimas o vacías que sugieren desinterés o descarte "
                        "(por ejemplo: solo un punto, solo 'no', respuestas de una sola palabra sin contexto, el cuerpo está "
                        "prácticamente vacío). Si el correo expresa curiosidad, hace una pregunta, pide más información, o muestra "
                        "cualquier apertura a seguir la conversación (aunque sea breve como 'ok' o 'cuéntame más'), NO lo marques como "
                        "no interesado. Ante la duda entre una respuesta breve pero con apertura vs. una respuesta de descarte, "
                        "priorizá NO marcar como no interesado — es preferible seguir la conversación por error a cerrar una oportunidad "
                        "real por error.\n\n"
                        "Responde ÚNICAMENTE con JSON puro: {\"no_interesado\": true} o {\"no_interesado\": false}"
                    )
                    resultado_gemini, _ = _generar_json_con_gemini(prompt_clasificacion, cuerpo_texto)
                    no_interesado = False
                    if resultado_gemini and isinstance(resultado_gemini, dict):
                        no_interesado = bool(resultado_gemini.get("no_interesado", False))

                    if no_interesado:
                        nuevo_estado = "Not interested" if es_demo else "No interesado"
                        no_interesados.append(remitente_email)
                    else:
                        nuevo_estado = "Replied" if es_demo else "Respondió"
                        respuestas.append(remitente_email)

                    if idx_estado:
                        hoja.update_cell(fila_match, idx_estado, nuevo_estado)

            # Marcar el correo como leído
            if msg_id:
                try:
                    patch_url = f"https://graph.microsoft.com/v1.0/users/{mailbox}/messages/{msg_id}"
                    requests.patch(
                        patch_url,
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json={"isRead": True},
                        timeout=15,
                    )
                except Exception:
                    pass

            revisados += 1

        except Exception:
            continue

    return {
        "revisados": revisados,
        "rebotes": rebotes,
        "respuestas": respuestas,
        "no_interesados": no_interesados,
    }


def buscar_leads_para_seguimiento() -> dict:
    """Busca leads en 'Leads Enviados' listos para su siguiente correo de seguimiento.

    Verifica que la columna Estado no tenga respuesta/rebote/cierre, que Paso Secuencia
    sea menor a 3, y que la fecha de Próximo Contacto ya haya vencido.

    Returns:
        {"leads": [{"nombre": str, "apellido": str, "cargo": str, "empresa": str,
                    "industria": str, "email": str, "paso_secuencia": int}, ...]}
    """
    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not credenciales_json or not sheet_id:
        return {"leads": []}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)
        try:
            hoja = hoja_principal.worksheet("Leads Enviados")
        except Exception:
            hoja = hoja_principal.sheet1

        header = hoja.row_values(1)
        if not header:
            return {"leads": []}

        idx_name = header.index("Nombre") + 1 if "Nombre" in header else (header.index("Name") + 1 if "Name" in header else 2)
        idx_last_name = header.index("Apellido") + 1 if "Apellido" in header else (header.index("Last Name") + 1 if "Last Name" in header else 3)
        idx_position = header.index("Cargo") + 1 if "Cargo" in header else (header.index("Position") + 1 if "Position" in header else 4)
        idx_company = header.index("Empresa") + 1 if "Empresa" in header else (header.index("Company") + 1 if "Company" in header else 5)
        idx_industry = header.index("Industria") + 1 if "Industria" in header else (header.index("Industry") + 1 if "Industry" in header else 6)
        idx_email = header.index("Email") + 1 if "Email" in header else 7
        idx_estado = header.index("Estado") + 1 if "Estado" in header else 8
        idx_paso = header.index("Paso Secuencia") + 1 if "Paso Secuencia" in header else None
        idx_proximo = header.index("Próximo Contacto") + 1 if "Próximo Contacto" in header else None

        if not idx_paso or not idx_proximo:
            return {"leads": []}

        filas = hoja.get_all_values()
        leads_seguimiento = []
        ahora = datetime.now(timezone.utc)

        for num_fila, fila in enumerate(filas[1:], start=2):
            try:
                estado = fila[idx_estado - 1].strip().lower() if idx_estado <= len(fila) else ""
                # Si el estado indica que ya hubo interacción o cierre, no hacer seguimiento
                if estado in ["rebotó", "reboto", "respondió", "respondio", "no interesado", "cerrado sin respuesta"]:
                    continue

                paso_str = fila[idx_paso - 1].strip() if idx_paso <= len(fila) else "1"
                try:
                    paso_val = int(paso_str)
                except Exception:
                    paso_val = 1

                if paso_val >= 3:
                    continue

                proximo_str = fila[idx_proximo - 1].strip() if idx_proximo <= len(fila) else ""
                if not proximo_str:
                    continue

                try:
                    fecha_clean = proximo_str.replace(" UTC", "").strip()
                    fecha_obj = datetime.strptime(fecha_clean, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                except Exception:
                    continue

                if fecha_obj <= ahora:
                    nombre = fila[idx_name - 1] if idx_name <= len(fila) else ""
                    apellido = fila[idx_last_name - 1] if idx_last_name <= len(fila) else ""
                    cargo = fila[idx_position - 1] if idx_position <= len(fila) else ""
                    empresa = fila[idx_company - 1] if idx_company <= len(fila) else ""
                    industria = fila[idx_industry - 1] if idx_industry <= len(fila) else ""
                    email = fila[idx_email - 1] if idx_email <= len(fila) else ""

                    leads_seguimiento.append({
                        "nombre": nombre,
                        "apellido": apellido,
                        "cargo": cargo,
                        "empresa": empresa,
                        "industria": industria,
                        "email": email,
                        "paso_secuencia": paso_val,
                    })
            except Exception:
                continue

        return {"leads": leads_seguimiento}

    except Exception:
        return {"leads": []}


def marcar_seguimiento_enviado(empresa: str, email: str, paso_nuevo: int, exitoso: bool) -> dict:
    """Actualiza en 'Leads Enviados' el paso de secuencia y próxima fecha tras un seguimiento.

    Si exitoso=True:
    - Si paso_nuevo <= 3: actualiza Paso Secuencia y suma +5 días a Próximo Contacto.
    - Si paso_nuevo > 3: marca Estado='Cerrado sin respuesta' y deja Próximo Contacto vacío.

    Args:
        empresa: Nombre de la empresa.
        email: Email del destinatario.
        paso_nuevo: Número de paso alcanzado (ej. 2, 3 o 4).
        exitoso: Si el correo fue enviado exitosamente.

    Returns:
        {"status": "actualizado", "email": email, "paso": paso_nuevo} o {"status": "error" / "no_encontrado"}
    """
    credenciales_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEETS_ID")
    if not credenciales_json or not sheet_id:
        return {"status": "error", "error": "Faltan credenciales de Google Sheets"}

    try:
        import gspread
        credenciales_dict = json.loads(credenciales_json)
        gc = gspread.service_account_from_dict(credenciales_dict)
        hoja_principal = gc.open_by_key(sheet_id)
        try:
            hoja = hoja_principal.worksheet("Leads Enviados")
        except Exception:
            hoja = hoja_principal.sheet1

        header = hoja.row_values(1)
        if "Paso Secuencia" not in header or "Próximo Contacto" not in header:
            hoja.resize(cols=max(len(header) + 5, 20))
            if "Paso Secuencia" not in header:
                hoja.update_cell(1, len(header) + 1, "Paso Secuencia")
                header.append("Paso Secuencia")
            if "Próximo Contacto" not in header:
                hoja.update_cell(1, len(header) + 1, "Próximo Contacto")
                header.append("Próximo Contacto")

        idx_email = (header.index("Email") + 1) if "Email" in header else 7
        idx_paso = header.index("Paso Secuencia") + 1
        idx_proximo = header.index("Próximo Contacto") + 1
        idx_estado = (header.index("Estado") + 1) if "Estado" in header else None

        emails_en_hoja = [e.strip().lower() for e in hoja.col_values(idx_email)]
        email_norm = email.strip().lower()

        fila_match = None
        for row_idx, e_val in enumerate(emails_en_hoja[1:], start=2):
            if e_val and e_val == email_norm:
                fila_match = row_idx
                break

        if not fila_match:
            return {"status": "no_encontrado", "email": email}

        if exitoso:
            if paso_nuevo > 3:
                if idx_estado:
                    hoja.update_cell(fila_match, idx_estado, "Cerrado sin respuesta")
                hoja.update_cell(fila_match, idx_paso, paso_nuevo)
                hoja.update_cell(fila_match, idx_proximo, "")
            else:
                ahora = datetime.now(timezone.utc)
                proxima_fecha = (ahora + timedelta(days=5)).strftime("%Y-%m-%d %H:%M UTC")
                hoja.update_cell(fila_match, idx_paso, paso_nuevo)
                hoja.update_cell(fila_match, idx_proximo, proxima_fecha)

        return {"status": "actualizado", "email": email, "paso": paso_nuevo}

    except Exception as e:
        return {"status": "error", "error": str(e)}