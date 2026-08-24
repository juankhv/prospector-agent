# Contexto del proyecto — Agente de Prospección (Hackathon)

## Qué es esto

Agente autónomo de prospección B2B para Aptitude (HRtech, mercado LATAM
hispanohablante), construido con Google ADK + Gemini para el **All Things
Agentic Hackathon** (deadline: 31 de agosto de 2026, track **Taskmaster**).
Inscrito como **organización** (Aptitude), no individuo — para calificar al
Startup Prize ($20,000 USD). Correo corporativo usado para el registro:
juan.hernandez@theaptitude.co.

Construido desde cero durante el período de submission. NO mencionar en
ningún documento (README, CLAUDE.md, respuestas de Devpost, ni en las
instrucciones del agente) ningún sistema previo de automatización — esto
es una decisión explícita del usuario, respetarla siempre.

## A quién ayuda esto

Juan Carlos (el usuario) es Co-Founder/COO de Aptitude, **no tiene perfil
técnico**. Cada cambio de código debe explicarse en términos simples. Usa
"tú/tienes", NO "vos/tenés". Ha usado Claude Code (VS Code y Desktop) y
Antigravity IDE con Gemini como asistentes de código en distintos momentos.

## REGLA DE ORO: verificar con evidencia real, nunca confiar en la descripción

**La lección más importante de todo el proyecto.** El asistente de código
(especialmente con DeepSeek vía OpenRouter, pero también con otros modelos)
describió más de una vez cambios que nunca se aplicaron al archivo real, o
solo parcialmente, mientras afirmaba que estaban completos. La única forma
confiable de confirmar un cambio: pedir que se corra `Select-String -Path
<archivo> -Pattern <texto>` DIRECTAMENTE en PowerShell y pegar el resultado
real. Nunca aceptar un resumen en prosa como prueba. Cuando un fragmento se
corta antes de mostrar la parte relevante (por ejemplo, la condición antes
de una línea de código), pedir más contexto (`-Context 0,N` con N mayor)
antes de dar el visto bueno.

## Arquitectura general

Un solo agente orquestador (`agente_prospeccion` en `agent.py`), NO
múltiples agentes separados. Gemini decide en tiempo real qué herramienta
llamar y en qué orden, según las instrucciones en lenguaje natural del
`instruction=` del Agent. **Existen DOS despliegues del mismo código**, ver
sección "Dos instancias" más abajo — es fundamental entender esta
arquitectura dual antes de tocar nada.

### Herramientas en `tools.py` (20 en total)

**Búsqueda de leads:**
1. `buscar_leads_apollo` — Apollo real (mixed_people/api_search), por
   sector. Un solo contacto por empresa por corrida (set `empresas_vistas`
   dentro de la función, evita duplicados en la misma llamada). Mercado
   default: `PAISES_LATAM_HISPANO` (17 países, constante al inicio del
   archivo) — NO Brasil (portugués), NO mercados de habla inglesa.
2. `buscar_persona_por_linkedin` — Apollo real (people/match), por LinkedIn
3. Camino C en agent.py: email directo dado por el usuario

**Investigación y redacción:**
4. `google_search_agent` — tool nativa de ADK (GoogleSearchTool con
   bypass_multi_tools_limit=True), vive en agent.py, no en tools.py
5. `redactar_correo` — Gemini real. SIEMPRE habla de Aptitude con el link
   real de HubSpot Meetings (https://meetings.hubspot.com/aptitude/demo) —
   esto es fijo, no configurable, ni siquiera en modo demo (decisión
   explícita: mostrarle al juez el agente real vendiendo Aptitude, no una
   empresa ficticia).
6. `verificar_correo` — Gemini real, fail-safe, permisivo con dominios
   corporativos abreviados (se.com, gm.com, etc.)
7. `redactar_seguimiento` — Gemini real, correos breves (máx 60 palabras)

**Filtros previos al envío (SIEMPRE en este orden en agent.py):**
8. `verificar_lista_exclusion(email, empresa)` — pestaña "Excluidos"/
   "Excluded Companies" (por email) Y "Empresas Excluidas"/"Excluded
   Companies" (por nombre). SIEMPRE el primer paso, antes de investigar o
   redactar nada.
9. `verificar_contactado_previamente` — ventana de **3 días hábiles**, NO
   bloqueo permanente. Usa `_hace_n_dias_habiles(fecha_str, n)`. Pasados 3
   días hábiles, se puede contactar a otra persona de la misma empresa.

**Envío y registro:**
10. `enviar_correo` — Microsoft Graph real (Outlook). Prioridad de
    destinatario: TEST_OVERRIDE_EMAIL (env var) > modo de prueba dinámico
    (Sheets) > destinatario real. Salvaguarda DEMO_ONLY_INSTANCE: si esa
    env var es "true" Y el modo de prueba no está activo, RECHAZA enviar
    (devuelve error, no manda nada) — evita que la instancia de demo
    dispare correos reales por accidente.
11. `crear_negocio_hubspot` — registra en Sheets (NO HubSpot real, nombre
    heredado). Escribe TODA la fila de una sola vez con
    `hoja.append_row(fila_completa)`, mapeando cada valor a su columna por
    NOMBRE — ver "Bug histórico" abajo, no volver al patrón viejo.
12. `marcar_para_revision_humana` — notificación real por Outlook a
    MICROSOFT_MAILBOX + registro persistente en "Pendientes de
    Aprobación"/"Pending Approval". Parámetro `es_reintento: bool` marca
    Retried="SI"/"YES".

**Automatización (chat o Cloud Scheduler):**
13. `revisar_aprobaciones_pendientes` — envía casos con Approved=SI/YES y
    Sent=NO/NO pendientes, reusando el texto ya guardado. Acepta "SI" o
    "YES" (case-insensitive) como aprobación válida.
14. `buscar_rechazados_para_reintentar` — rechazos >7 días, marca
    Retried=SI/YES ANTES de reintentar (salvaguarda anti-loop)
15. `revisar_respuestas_bandeja` — Microsoft Graph, rebotes (keywords) y
    respuestas reales (match de email contra "Leads Enviados"/"Sent
    Leads"), clasifica "no interesado" con Gemini (incluye respuestas
    mínimas tipo "." o "no")
16. `buscar_leads_para_seguimiento` / `marcar_seguimiento_enviado` —
    seguimiento 2do/3er intento, +5 días entre intentos, máx 3, luego
    "Cerrado sin respuesta"
17. `generar_reporte_diario` — cuenta leads por estado, NO envía nada
18. `enviar_reporte_por_correo(cuerpo_reporte, destinatario_email=None)` —
    envía solo si se pide explícitamente

**Modo de prueba / instancia de demo (agregadas en sesión del 22 de agosto):**
19. `activar_modo_prueba(email_prueba, idioma="en", pais=None)` /
    `desactivar_modo_prueba` — guarda config en pestaña "Demo Config"
    (Active, TestEmail, Language, Country, ConfiguredAt, ExpiresAt).
    Auto-expira a los 30 minutos (columna ExpiresAt, chequeada en
    `_obtener_config_prueba`). YA NO tiene parámetros `empresa` ni
    `url_reuniones` — se quitaron a propósito (ver "Simplificación" abajo).
    `pais` default: "Latinoamérica (todos los países hispanohablantes)" —
    `buscar_leads_apollo` traduce ese string especial a la lista completa
    `PAISES_LATAM_HISPANO`.
20. `aprobar_y_enviar(empresa, email)` / `marcar_enviado_en_aprobaciones(email, empresa=None)`
    — permiten aprobar y enviar directamente desde la conversación (sin ir
    a Sheets). `aprobar_y_enviar` asume que YA existe un correo guardado
    (funciona para contacto-previo y rechazo-verificador). Para el caso de
    EXCLUSIÓN nunca hay correo guardado (Subject/Body quedan "N/A") — en
    ese caso el agente debe primero investigar/redactar/verificar/enviar
    de cero con `enviar_correo`, y DESPUÉS llamar a
    `marcar_enviado_en_aprobaciones` (no `aprobar_y_enviar`, que
    reenviaría un correo vacío / duplicaría el intento).

### Regla de negocio: autonomía con excepciones puntuales

El agente es **AUTÓNOMO de punta a punta**. Interviene un humano SOLO
cuando: correo rechazado 3 veces por el Verificador, contacto/empresa en
lista de exclusión manual, o empresa contactada hace menos de 3 días
hábiles. En cualquier otro caso, envía y registra SIN pedir confirmación.

## Dos instancias de Cloud Run — MUY IMPORTANTE

Mismo código, mismo repo, **dos despliegues separados** con distinto
archivo de variables de entorno:

| | Producción real | Demo (jueces) |
|---|---|---|
| Service name | `prospector-agent` | `prospector-agent-demo` |
| Env file | `env-vars.yaml` | `env-vars-demo.yaml` |
| URL | https://prospector-agent-405290540774.us-central1.run.app | https://prospector-agent-demo-405290540774.us-central1.run.app |
| GOOGLE_SHEETS_ID | hoja real de Aptitude | `1Abr0X62ngMsx30N0UWmkdBl4G2kUYvyx2Q2ZwdP0B7s` (separada, compartida read-only con cualquiera que tenga el link) |
| DEMO_ONLY_INSTANCE | no existe | `'true'` |
| Idioma de Sheets | español | inglés (pestañas y encabezados) |
| Cloud Scheduler | 5 jobs activos | ninguno — todo manual vía chat |

**CUALQUIER cambio en `tools.py` o `agent.py` que no sea 100% específico
de un solo lado (por ejemplo, un ajuste solo al mensaje de bienvenida
DEMO_ONLY_INSTANCE) requiere REDESPLEGAR AMBAS instancias** — es un error
común quedarse a mitad de camino desplegando solo una. Siempre correr los
dos comandos de `adk deploy cloud_run` (ver sección Despliegue).

`env-vars-demo.yaml` se generó copiando `env-vars.yaml` y reemplazando
`GOOGLE_SHEETS_ID` + agregando `DEMO_ONLY_INSTANCE: 'true'` — NUNCA pegar
el contenido de estos archivos en el chat (tienen credenciales completas),
solo confirmar con `Select-String -Pattern` sobre líneas específicas o
conteos.

### Simplificación del modo de prueba (importante para no revertir)

La primera versión del modo de prueba permitía cambiar también empresa
("empresa ficticia" en vez de Aptitude) y `url_reuniones` custom
(Calendly genérico). **Se descartó explícitamente**: el objetivo pasó a
ser mostrarle al juez el agente REAL vendiendo Aptitude, con el link REAL
de HubSpot Meetings — solo `email_prueba`, `idioma`, y `pais` quedan
configurables. Si en el futuro aparece código o instrucciones mencionando
"empresa ficticia", "url_reuniones custom" o "calendly.com" en el contexto
del modo de prueba, es código residual viejo — limpiarlo, no reactivarlo
(ya se hizo una vez, ver el patrón de limpieza usado ese día:
`Select-String -Pattern "calendly.com"` debe devolver vacío).

También se quitó "colombiana" de TODAS las descripciones de Aptitude (en
agent.py línea ~49, y en los dos SYSTEM_PROMPT de tools.py) — el mercado ya
es LATAM completa, no solo Colombia.

### Textos bilingües en Sheets — patrón `es_demo`

Todas las funciones que escriben en Sheets siguen el mismo patrón:
```python
es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"
nombre_pestaña = "Nombre En Inglés" if es_demo else "Nombre En Español"
```
Aplicado en: `crear_negocio_hubspot` ("Sent Leads" / "Leads Enviados"),
`verificar_lista_exclusion` ("Excluded Companies" / "Empresas Excluidas"),
`marcar_para_revision_humana` y `revisar_aprobaciones_pendientes`
("Pending Approval" / "Pendientes de Aprobación"), `revisar_respuestas_bandeja`
(valores de estado: Bounced/Rebotó, Replied/Respondió, Not interested/No
interesado). Los valores de aprobación aceptan ambas grafías
(`if approved in ("SI", "YES")`) por seguridad, aunque cada instancia solo
escribe con su propio idioma. **Si se agrega una función nueva que escriba
en Sheets, aplicar este mismo patrón siempre — es fácil olvidarlo y crear
una pestaña en el idioma equivocado en la instancia de demo** (pasó varias
veces esta sesión: "Sent Leads" tuvo que corregirse, "Pending Approval"
también).

### El agente en modo demo puede explicar el proyecto

Sección completa en `agent.py` (dentro del bloque `DEMO_ONLY_INSTANCE`) con
toda la info de Devpost (elevator pitch, inspiración, qué hace, cómo se
construyó, stack, SDK usado, desafíos técnicos, aprendizajes, qué sigue) —
el juez puede preguntarle directamente al agente en vez de ir a Devpost.
El contenido de referencia está en español pero la instrucción es explícita:
SIEMPRE traducir al idioma en que hable el juez. También explica el
propósito de cada pestaña de Sheets si se le pregunta (Excluded Companies,
Pending Approval) y menciona que puede aprobar/enviar directamente desde
el chat sin ir a Sheets.

## Google Sheets: estructura de pestañas (PRODUCCIÓN real, español)

- **"Leads Enviados"**: `Date, Name, Last Name, Position, Company,
  Industry, Email, Primer Contacto, Estado, Paso Secuencia, Próximo
  Contacto`. "Primer Contacto" (antes "Status") solo dice "Correo enviado"
  una vez. "Estado" es para respuestas/rebotes/cierre.
- **"Excluidos"**: columna "Email"
- **"Empresas Excluidas"**: columna "Empresa", creada con `cols=20`
- **"Pendientes de Aprobación"**: `Date, Name, Last Name, Position,
  Company, Industry, Email, Subject, Body, Reason, Approved, Sent, Retried`

Equivalentes en INGLÉS en la hoja de demo (`1Abr0X62ngMsx30N0UWmkdBl4G2kUYvyx2Q2ZwdP0B7s`):
"Sent Leads", "Excluded Companies", "Pending Approval" — mismos campos,
encabezados en inglés, valores de estado en inglés.

**Patrón de búsqueda de columnas**: SIEMPRE por NOMBRE (con fallback
bilingüe ES/EN donde aplica), nunca por posición fija. Columna nueva que no
existe todavía: `hoja.resize(cols=N)` ANTES de `update_cell` — Sheets
tiene un límite estricto que rompe sin este paso (bug real, ya corregido
varias veces).

## Bug histórico importante: desalineamiento/sobrescritura de filas

`crear_negocio_hubspot` tuvo tres versiones:
1. **v1**: lista de valores por posición fija — se desalineó cuando se
   agregaron columnas nuevas sin actualizar la lista.
2. **v2 (bug grave)**: reservar fila vacía + contar filas para el índice —
   condición de carrera que SOBRESCRIBIÓ una fila existente en vez de
   crear una nueva. Pérdida de datos real (una fila de prueba).
3. **v3 (actual, correcta)**: construir la fila completa en memoria,
   mapear por nombre de columna, UNA SOLA llamada `append_row(fila_completa)`
   al final. Este es el patrón a seguir siempre — nunca volver a v1 o v2.

## Cloud Scheduler: 5 jobs, SOLO en producción, ACTIVOS desde 21 de agosto

| Job | Horario (Bogotá) | Mensaje al agente |
|---|---|---|
| revision-respuestas-diaria | 7:00am, todos los días | "Revisá la bandeja de respuestas y rebotes" |
| reintento-rechazados-diario | 8:30am, todos los días | "Reintentá los rechazados" |
| prospeccion-diaria | 12:00pm, solo días hábiles | "Prospectá 10 empresas del sector {rotativo}" |
| seguimiento-diario | 2:00pm, todos los días | "Hacé seguimiento" |
| revision-aprobaciones-diaria | 4:00pm, todos los días | "Revisá las aprobaciones pendientes" |

Volumen: 10 correos/día de primer contacto (subido desde 5 el 22-ago).
Todos `--attempt-deadline=600s --max-retry-attempts=0`. La instancia de
demo NO tiene ningún job — todo es manual vía chat.

## Variables de entorno

`.env` (local, sintaxis `CLAVE=valor`) y `env-vars.yaml`/`env-vars-demo.yaml`
(Cloud Run, sintaxis YAML `CLAVE: 'valor'`) — MISMO contenido salvo
`GOOGLE_SHEETS_ID` y `DEMO_ONLY_INSTANCE`. Confundir formatos rompe el
parseo (ya pasó una vez).

Core: GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT,
GOOGLE_CLOUD_LOCATION=us (NO us-central1), APOLLO_API_KEY,
MICROSOFT_TENANT_ID/CLIENT_ID/CLIENT_SECRET/MAILBOX, GOOGLE_SHEETS_CREDENTIALS_JSON,
GOOGLE_SHEETS_ID. TEST_OVERRIDE_EMAIL fue ELIMINADA de producción el 21 de
agosto — sistema en MODO REAL. `DEMO_ONLY_INSTANCE='true'` solo en
env-vars-demo.yaml.

**Seguridad de credenciales**: la clave de servicio de Sheets fue rotada
DOS VECES por pegarse en el chat. Nunca pedir/mostrar contenido de
credenciales — solo conteos o nombres de archivo.

## Despliegue

**Producción:**
```
adk deploy cloud_run --project=prospector-agent-505122 --region=us-central1 --service_name=prospector-agent --app_name=prospector_agent --with_ui prospector_agent -- --env-vars-file=env-vars.yaml --allow-unauthenticated --clear-base-image
```

**Demo:**
```
adk deploy cloud_run --project=prospector-agent-505122 --region=us-central1 --service_name=prospector-agent-demo --app_name=prospector_agent --with_ui prospector_agent -- --env-vars-file=env-vars-demo.yaml --allow-unauthenticated --clear-base-image
```

Siempre termina con falso "Deploy failed" (permisos de Windows en carpeta
temporal) — ignorar, lo que importa es "serving 100 percent of traffic"
antes de esa línea. `requirements.txt` debe existir en la raíz Y en
`prospector_agent/`.

**Cloud Functions** (solo producción, triggers de Scheduler):
```
gcloud functions deploy <nombre> --gen2 --runtime=python312 --region=us-central1 --source=cloud_function --entry-point=<func_python> --trigger-http --allow-unauthenticated --timeout=540 --set-env-vars=AGENT_SERVICE_URL=<url-produccion>
```

## Devpost — estado del registro

- Inscrito como organización (Aptitude), no individuo
- Elevator pitch: "An autonomous B2B prospecting agent that finds leads,
  writes personalized outreach, and manages follow-ups — running in
  production, not just a demo."
- About the project: completo (Inspiration/What it does/How we built
  it/Why Sheets/Challenges/What we learned/What's next) — en "we", no "I"
- Fecha de inicio: 10 de agosto de 2026
- Google SDK: ADK + GenAI SDK
- Modelo de IA: Gemini 3.5 Flash únicamente (no se forzaron Veo/Lyria/Gemma)
- Tags: Python, Google ADK, Gemini, Google Cloud, Cloud Run, Cloud
  Functions, Cloud Scheduler, Google Sheets, Google Sheets API, Apollo.io,
  Microsoft Graph API, Outlook, Claude, Claude Code, Antigravity IDE,
  Vertex AI, gspread, REST API, OAuth
- Diagrama de arquitectura: generado y subido (PNG, matplotlib)
- Hosted project URL: la de producción real (se decidió compartir porque
  el modo de prueba dinámico protege contra envíos accidentales — pero
  luego se optó por promover la URL de DEMO en su lugar en README/testing
  instructions, más segura)
- Testing instructions (privadas, ≤255 caracteres): mencionan la URL demo
  y el sheet de solo lectura
- Video demo: PENDIENTE de grabar
- Repo de GitHub: PENDIENTE de subir (se dejará para el final, cuando el
  código esté más asentado)
- Teammates: confirmar si se agrega a alguien más (deben aceptar invite)

## Pendientes reales para el submission

1. **Grabar el video demo** (~4 min)
2. **Subir el repo a GitHub** (verificar .gitignore antes: .env,
   env-vars.yaml, env-vars-demo.yaml, cualquier .json de credenciales)
3. Completar el resto del formulario de Devpost (teammates, disclosures)
4. Monitorear producción real: bandeja jh@go.theaptitude.co, Sheets real,
   confirmar que el volumen de 10/día y el mercado LATAM funcionan bien
   en la práctica durante la primera semana

## Fuera de alcance a propósito

- Detección de reuniones agendadas vía HubSpot Meetings real — no
  implementable sin HubSpot real
- Vigilancia de bandeja en tiempo real (cada minuto) — batch diario a las
  7am, decisión consciente de arquitectura

## Convenciones de estilo al hablar con el usuario

- Español, "tú/tienes" (NO "vos/tenés")
- Explicaciones honestas, sin inflar el alcance de lo logrado
- No regenerar/reempaquetar el proyecto completo cuando cambian 1-2
  archivos — mostrar o editar solo lo que cambió
- SIEMPRE pedir verificación con comando real antes de aceptar que un
  cambio de código se aplicó correctamente
- NUNCA mencionar sistemas de automatización previos a este proyecto, en
  ningún documento ni conversación con jueces
