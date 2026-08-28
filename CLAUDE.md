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

**Repositorio de GitHub**: https://github.com/juankhv/prospector-agent
(público, subido el 24-25 de agosto de 2026, verificado sin credenciales
expuestas).

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
corta antes de mostrar la parte relevante, pedir más contexto (`-Context
0,N` con N mayor) antes de dar el visto bueno.

## Arquitectura general

Un solo agente orquestador (`agente_prospeccion` en `agent.py`), NO
múltiples agentes separados. Gemini decide en tiempo real qué herramienta
llamar y en qué orden. **Existen DOS despliegues del mismo código** — ver
sección "Dos instancias" más abajo, fundamental antes de tocar nada.

### Herramientas en `tools.py` (20 en total)

**Búsqueda de leads:**
1. `buscar_leads_apollo` — Apollo real, por sector. Un solo contacto por
   empresa por corrida (set `empresas_vistas`). Mercado default:
   `PAISES_LATAM_HISPANO` (17 países, constante al inicio del archivo) — NO
   Brasil, NO mercados de habla inglesa.
2. `buscar_persona_por_linkedin` — Apollo real, por LinkedIn
3. Camino C en agent.py: email directo dado por el usuario

**Investigación y redacción:**
4. `google_search_agent` — tool nativa de ADK, vive en agent.py
5. `redactar_correo` — Gemini real. SIEMPRE habla de Aptitude con el link
   real de HubSpot Meetings (https://meetings.hubspot.com/aptitude/demo) —
   fijo, no configurable ni en modo demo.
6. `verificar_correo` — Gemini real, fail-safe, permisivo con dominios
   corporativos abreviados
7. `redactar_seguimiento` — Gemini real, correos breves (máx 60 palabras)

**Filtros previos al envío (SIEMPRE en este orden en agent.py):**
8. `verificar_lista_exclusion(email, empresa)` — SIEMPRE el primer paso
9. `verificar_contactado_previamente` — ventana de **3 días hábiles**, NO
   bloqueo permanente

**Envío y registro:**
10. `enviar_correo` — Microsoft Graph real. Prioridad: TEST_OVERRIDE_EMAIL >
    modo de prueba dinámico > destinatario real. Salvaguarda
    DEMO_ONLY_INSTANCE: rechaza enviar si esa env var es "true" Y el modo de
    prueba no está activo.
11. `crear_negocio_hubspot` — registra en Sheets (NO HubSpot real). UNA SOLA
    llamada `hoja.append_row(fila_completa)`, mapeo por NOMBRE de columna —
    ver "Bug histórico" abajo.
12. `marcar_para_revision_humana` — notificación real por Outlook +
    registro persistente. Parámetro `es_reintento: bool`.

**Automatización (chat o Cloud Scheduler):**
13. `revisar_aprobaciones_pendientes` — acepta "SI" o "YES"
14. `buscar_rechazados_para_reintentar` — >7 días, marca Retried ANTES de
    reintentar
15. `revisar_respuestas_bandeja` — rebotes + respuestas + clasificación
    "no interesado" con Gemini
16. `buscar_leads_para_seguimiento` / `marcar_seguimiento_enviado` — +5 días
    entre intentos, máx 3
17. `generar_reporte_diario` — NO envía nada
18. `enviar_reporte_por_correo(cuerpo_reporte, destinatario_email=None)`

**Modo de prueba / instancia de demo:**
19. `activar_modo_prueba(email_prueba, idioma="en", pais=None)` /
    `desactivar_modo_prueba` — pestaña "Demo Config", auto-expira a los 30
    min. SIN parámetros `empresa` ni `url_reuniones` (se quitaron a
    propósito). `pais` default: string especial "Latinoamérica (todos los
    países hispanohablantes)" → `buscar_leads_apollo` lo traduce a
    `PAISES_LATAM_HISPANO`.
20. `aprobar_y_enviar(empresa, email)` / `marcar_enviado_en_aprobaciones(email, empresa=None)`
    — para exclusión (sin correo guardado) usar investigar→redactar→
    verificar→enviar_correo→marcar_enviado_en_aprobaciones (NUNCA
    aprobar_y_enviar solo, duplicaría/enviaría "N/A").

### Regla de negocio: autonomía con excepciones puntuales

Autónomo de punta a punta. Interviene un humano SOLO cuando: correo
rechazado **2 veces** por el Verificador (bajado de 3 a 2 el 25-ago-2026,
para reducir latencia — ver sección de performance abajo), contacto/empresa
en exclusión manual, o empresa contactada hace menos de 3 días hábiles.

## Dos instancias de Cloud Run — MUY IMPORTANTE

| | Producción real | Demo (jueces) |
|---|---|---|
| Service name | `prospector-agent` | `prospector-agent-demo` |
| Env file | `env-vars.yaml` | `env-vars-demo.yaml` |
| URL | https://prospector-agent-405290540774.us-central1.run.app | https://prospector-agent-demo-405290540774.us-central1.run.app |
| GOOGLE_SHEETS_ID | hoja real de Aptitude | `1Abr0X62ngMsx30N0UWmkdBl4G2kUYvyx2Q2ZwdP0B7s` (separada, read-only pública) |
| DEMO_ONLY_INSTANCE | no existe | `'true'` |
| Idioma de Sheets | español | inglés |
| Cloud Scheduler | 5 jobs activos | ninguno — manual vía chat |
| Timeout Cloud Run | **1800s (30 min)**, corregido 25-ago | 1800s |

**CUALQUIER cambio que no sea 100% específico de un lado requiere
REDESPLEGAR AMBAS instancias.** Ambos comandos de despliegue AHORA deben
incluir `--timeout=1800` (ver "Bug de performance" abajo) — no volver al
timeout por defecto de Cloud Run (300s) al redesplegar.

### Simplificación del modo de prueba (no revertir)

Se descartaron `empresa` ficticia y `url_reuniones` custom — el agente
SIEMPRE habla de Aptitude real, con el link real de HubSpot Meetings. Si
aparece código o instrucciones mencionando "empresa ficticia",
"url_reuniones custom" o "calendly.com" en el modo de prueba, es residuo
viejo — limpiarlo (`Select-String -Pattern "calendly.com"` debe devolver
vacío). También se quitó "colombiana" de TODAS las descripciones de
Aptitude — el mercado es LATAM completa.

### Textos bilingües en Sheets — patrón `es_demo`

```python
es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"
nombre_pestaña = "Nombre En Inglés" if es_demo else "Nombre En Español"
```
Aplicado en: `crear_negocio_hubspot` ("Sent Leads"/"Leads Enviados"),
`verificar_lista_exclusion` ("Excluded Companies"/"Empresas Excluidas"),
`marcar_para_revision_humana` y `revisar_aprobaciones_pendientes`
("Pending Approval"/"Pendientes de Aprobación"), `revisar_respuestas_bandeja`
(estados: Bounced/Rebotó, Replied/Respondió, Not interested/No interesado).
**Cualquier función nueva que escriba en Sheets debe aplicar este patrón —
se olvidó varias veces y hubo que corregir después del hecho.**

### El agente en modo demo puede explicar el proyecto

Sección completa en `agent.py` (bloque `DEMO_ONLY_INSTANCE`) con toda la
info de Devpost (pitch, inspiración, qué hace, cómo se construyó, stack,
SDK, desafíos, aprendizajes, qué sigue). Contenido de referencia en
español, pero SIEMPRE traducido al idioma del juez. También explica el
propósito de cada pestaña de Sheets, y que puede aprobar/enviar desde el
chat sin ir a Sheets manualmente (recordarle al juez que en la instancia
demo no hay Cloud Scheduler — si aprueba algo, tiene que volver a pedirle
al agente que revise las aprobaciones pendientes, no pasa solo).

## Bug de performance encontrado y corregido el 25 de agosto de 2026

**Síntoma**: la prospección diaria real (12pm) dejó de completar envíos
desde el 21 de agosto, cuando el volumen subió de 5 a 10 leads/día.

**Causa raíz**: Cloud Run tiene un límite de request de 300s (5 min) por
defecto, nunca configurado explícitamente al desplegar `prospector-agent`.
Procesar 10 leads secuenciales (cada uno: investigar+redactar+verificar
con hasta 3 reintentos+enviar+registrar) supera fácilmente ese límite —
Cloud Run cortaba la conexión con `504 Gateway Timeout` antes de que el
agente terminara. Confirmado en logs de Cloud Functions
(`gcloud functions logs read trigger-prospector`) para el 21 y 24 de
agosto, mismo patrón exacto.

**Corrección aplicada:**
1. Ambos despliegues de Cloud Run ahora incluyen `--timeout=1800` (30 min)
   explícito en el comando `adk deploy cloud_run ... -- ... --timeout=1800`
2. Límite de reintentos del Verificador bajado de 3 a 2 (9 menciones en
   `agent.py`, todas actualizadas) — reduce el peor caso de latencia,
   sobre todo relevante para la instancia de demo con jueces esperando en
   vivo
3. **PENDIENTE DE CONFIRMAR**: la corrida del 26 de agosto (próximo día
   hábil) es la primera prueba real de que el fix funciona — revisar
   logs de `trigger-prospector` y la hoja "Leads Enviados" real después
   de las 12pm para confirmar que los 10 correos se completan sin 504.
   Si sigue fallando, el siguiente sospechoso sería el timeout interno de
   la Cloud Function (540s en el `requests.post` del código Python Y en
   el `--timeout` de `gcloud functions deploy`) — aunque un timeout ahí
   ya está diseñado para no tratarse como error fatal (el código captura
   `requests.exceptions.Timeout` y asume que sigue en background), así
   que no debería ser la causa si Cloud Run ya no corta la conexión antes.

**Nota para la demo con jueces**: para latencia baja en vivo, se sugiere
"prospect 1 company" en vez de "3 companies" como ejemplo — pendiente de
confirmar si este ajuste al texto de ejemplo llegó a aplicarse (revisar
`Select-String -Pattern "Prospect 1"` en agent.py; si no aparece, seguía
sugiriendo 3 al momento de este corte de sesión).

## Margen de leads y salto automático de duplicados (28 de agosto de 2026)

**Problema real encontrado**: el 28 de agosto, `prospeccion-diaria` corrió
sin ningún error de timeout (confirmando que los dos fixes anteriores
funcionan), pero Apollo devolvió las mismas dos empresas que ya se habían
contactado el día anterior (durante pruebas manuales de diagnóstico del
bug de timeout). El chequeo de contacto-previo las bloqueó correctamente
—comportamiento esperado— pero el agente simplemente las escaló a
"Pendientes de Aprobación" y se detuvo ahí, sin buscar otros candidatos.
Resultado: cero correos nuevos ese día, aunque el sistema funcionó
"correctamente" según su diseño original.

**Corrección aplicada**:
1. `buscar_leads_apollo` ahora pide margen extra a Apollo cuando
   `cantidad >= 5` (el caso real de prospección diaria, no las pruebas
   manuales chicas): `per_page = cantidad * 2` (con mínimo `cantidad * 3`
   o 25 para cantidades chicas), y devuelve hasta `cantidad * 2`
   candidatos filtrados (ya no corta la lista a `cantidad`) — el agente
   recibe más opciones de las que necesita.
2. En las instrucciones de `agent.py`, durante la prospección diaria por
   sector: si un lead resulta ya contactado, el agente ya NO lo escala a
   revisión — lo salta silenciosamente, sin ningún registro, y pasa al
   siguiente candidato de la lista extra, hasta completar la cuota
   original o agotar los candidatos disponibles. Esta regla es específica
   del chequeo de contacto-previo durante prospección diaria — la
   exclusión manual (`verificar_lista_exclusion`) sigue escalando
   normalmente, sin cambios.

**Efecto esperado**: los días en que Apollo repite resultados ya
contactados, el agente ahora debería seguir intentando con el resto de
la lista extra en vez de terminar el día con cero correos nuevos.
**PENDIENTE DE CONFIRMAR** en la próxima corrida real de `prospeccion-diaria`.

## Segundo bug de timeout, corregido el 27 de agosto de 2026

**Síntoma**: aunque el fix del 25 de agosto funcionó (confirmado: la
corrida del 26 de agosto completó envíos con éxito), la corrida automática
del 27 de agosto a las 12pm falló de nuevo, esta vez con un error distinto:
`Error creando sesión: ... Read timed out. (read timeout=60)` — NO era un
504 de Cloud Run, era el timeout de la PRIMERA llamada HTTP (crear sesión),
que seguía en 60 segundos.

**Causa raíz**: 60 segundos era insuficiente para cubrir un arranque en
frío lento de Cloud Run en algunos días — el servicio, si no tuvo tráfico
reciente, puede tardar más de 60s en levantar el contenedor y responder al
primer POST de creación de sesión. Confirmado con una llamada directa
aislada (`requests.post` a mano) que, una vez la instancia ya estaba
"caliente", respondía en ~15s — pero un arranque frío real puede superar
holgadamente los 60s.

**Corrección aplicada**: subido el timeout de la llamada de creación de
sesión de 60 a 180 segundos, en las 5 funciones de `cloud_function/main.py`
(trigger_prospector, trigger_seguimiento, trigger_reintento_rechazados,
trigger_revision_respuestas, trigger_revision_aprobaciones). Las 5 Cloud
Functions fueron redesplegadas individualmente (mismo comando
`gcloud functions deploy` de siempre, solo cambia `--entry-point`).

**Efecto colateral del diagnóstico**: al disparar manualmente
`gcloud scheduler jobs run prospeccion-diaria` para probar, se generó una
corrida real ADICIONAL ese mismo día (10 correos reales a prospectos
reales, confirmados en "Leads Enviados" entre las 22:34–22:45 UTC del
27-ago) — fuera del horario normal de las 12pm. Esto es esperado: correr
ese comando siempre dispara el proceso real completo, no hay modo
"simulación" para ese comando específico. Tenerlo en cuenta antes de
volver a disparar manualmente un job de producción solo para diagnosticar
— considerar si hace falta de verdad o si alcanza con revisar logs.

**PENDIENTE DE CONFIRMAR (actualizado)**: la corrida del 28 de agosto
(viernes, día hábil) es la primera prueba real de este segundo fix —
revisar logs de todas las Cloud Functions y la hoja "Leads Enviados" real
después de cada horario programado (7am, 8:30am, 12pm, 2pm, 4pm) para
confirmar que ninguna vuelve a fallar por timeout de ningún tipo.

## Google Sheets: estructura de pestañas (PRODUCCIÓN real, español)

- **"Leads Enviados"**: `Date, Name, Last Name, Position, Company,
  Industry, Email, Primer Contacto, Estado, Paso Secuencia, Próximo
  Contacto`
- **"Excluidos"**: columna "Email"
- **"Empresas Excluidas"**: columna "Empresa", `cols=20`
- **"Pendientes de Aprobación"**: `Date, Name, Last Name, Position,
  Company, Industry, Email, Subject, Body, Reason, Approved, Sent, Retried`

Equivalentes en inglés en la hoja de demo
(`1Abr0X62ngMsx30N0UWmkdBl4G2kUYvyx2Q2ZwdP0B7s`): "Sent Leads", "Excluded
Companies", "Pending Approval".

**Patrón de búsqueda de columnas**: SIEMPRE por NOMBRE, nunca posición
fija. Columna nueva: `hoja.resize(cols=N)` ANTES de `update_cell`.

## Bug histórico: desalineamiento/sobrescritura de filas

`crear_negocio_hubspot` tuvo 3 versiones — v1 (lista por posición fija,
se desalineaba), v2 (reservar fila + contar filas, causó una condición de
carrera que SOBRESCRIBIÓ una fila real), v3 actual (correcta: construir la
fila completa en memoria, mapear por nombre, UNA sola llamada `append_row`
al final). Nunca volver a v1 o v2.

## Cloud Scheduler: 5 jobs, SOLO en producción, ACTIVOS desde 21 de agosto

| Job | Horario (Bogotá) | Mensaje al agente |
|---|---|---|
| revision-respuestas-diaria | 7:00am, todos los días | "Revisá la bandeja de respuestas y rebotes" |
| reintento-rechazados-diario | 8:30am, todos los días | "Reintentá los rechazados" |
| prospeccion-diaria | 12:00pm, solo días hábiles | "Prospectá 10 empresas del sector {rotativo}" |
| seguimiento-diario | 2:00pm, todos los días | "Hacé seguimiento" |
| revision-aprobaciones-diaria | 4:00pm, todos los días | "Revisá las aprobaciones pendientes" |

Volumen: 10 correos/día (subido desde 5 el 22-ago). Todos
`--attempt-deadline=600s --max-retry-attempts=0`. Demo NO tiene jobs.

**Nota post-fix de timeout**: `--attempt-deadline=600s` de Cloud Scheduler
es el tiempo que Scheduler espera la respuesta de la Cloud Function (no de
Cloud Run) — no necesitó cambiarse, porque la Cloud Function responde
rápido gracias al manejo de timeout ya diseñado (ver Bug de performance).

## Variables de entorno

`.env` (local) y `env-vars.yaml`/`env-vars-demo.yaml` (Cloud Run) — mismo
contenido salvo `GOOGLE_SHEETS_ID` y `DEMO_ONLY_INSTANCE`. Core:
GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION=us
(NO us-central1), APOLLO_API_KEY, MICROSOFT_TENANT_ID/CLIENT_ID/
CLIENT_SECRET/MAILBOX, GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEETS_ID.
TEST_OVERRIDE_EMAIL eliminada de producción — modo real activo.

**Seguridad de credenciales**: la clave de servicio de Sheets fue rotada
DOS VECES por pegarse en el chat. Nunca pedir/mostrar contenido de
credenciales — solo conteos o nombres de archivo.

## Despliegue (comandos actualizados con --timeout)

**Producción:**
```
adk deploy cloud_run --project=prospector-agent-505122 --region=us-central1 --service_name=prospector-agent --app_name=prospector_agent --with_ui prospector_agent -- --env-vars-file=env-vars.yaml --allow-unauthenticated --clear-base-image --timeout=1800
```

**Demo:**
```
adk deploy cloud_run --project=prospector-agent-505122 --region=us-central1 --service_name=prospector-agent-demo --app_name=prospector_agent --with_ui prospector_agent -- --env-vars-file=env-vars-demo.yaml --allow-unauthenticated --clear-base-image --timeout=1800
```

Termina con falso "Deploy failed" (permisos Windows, carpeta temporal) —
ignorar, lo que importa es "serving 100 percent of traffic" antes de esa
línea. `requirements.txt` en la raíz Y en `prospector_agent/`.

**Cloud Functions:**
```
gcloud functions deploy <nombre> --gen2 --runtime=python312 --region=us-central1 --source=cloud_function --entry-point=<func_python> --trigger-http --allow-unauthenticated --timeout=540 --set-env-vars=AGENT_SERVICE_URL=<url-produccion>
```

## GitHub

Repo público: https://github.com/juankhv/prospector-agent. `.gitignore`
robusto con patrones (no solo nombres exactos): `.env`, `*.env`,
`env-vars*.yaml`, `*service-account*.json`, `*credentials*.json`,
`prospector-agent-*.json`, `sheets_credentials_oneline.txt`, `.claude/`,
`*.adk/`, `*.db` (este último para excluir `prospector_agent/.adk/session.db`,
la base de datos local de sesiones de `adk web`, que no debe subirse).
Verificado visualmente en GitHub que no hay ningún archivo sensible
expuesto — 13 archivos en el commit inicial.

## Devpost — estado del registro

- Organización (Aptitude), no individuo. Elevator pitch, About the
  project (Inspiration/What it does/How we built it/Why Sheets/
  Challenges/What we learned/What's next) completos, en "we".
- Fecha de inicio: 10 de agosto de 2026. SDK: ADK + GenAI SDK. Modelo:
  Gemini 3.5 Flash únicamente.
- Tags (19): Python, Google ADK, Gemini, Google Cloud, Cloud Run, Cloud
  Functions, Cloud Scheduler, Google Sheets, Google Sheets API, Apollo.io,
  Microsoft Graph API, Outlook, Claude, Claude Code, Antigravity IDE,
  Vertex AI, gspread, REST API, OAuth
- Diagrama de arquitectura: generado (PNG, matplotlib), refleja solo
  producción real (decisión consciente de no agregar la instancia de
  demo al diagrama)
- URL del repo de GitHub: ya agregada al formulario
- Hosted project URL / testing instructions: apuntan a la instancia de
  demo, no a producción real
- Video demo: PENDIENTE — guion de 4 minutos ya definido (ver abajo),
  planificación detallada se está haciendo en un chat separado
- Teammates: pendiente de decidir si se agrega a alguien más

### Guion del video demo (definido, pendiente de grabar en detalle en otro chat)

0:00–0:30 problema+solución, 0:30–1:30 demo prospección exitosa, 1:30–2:15
demo caso de escalamiento, 2:15–3:00 arquitectura (usar el diagrama),
3:00–3:40 prueba de producción real (cifras concretas), 3:40–4:00 cierre
(stack, qué sigue). La planificación palabra por palabra se está haciendo
en una conversación aparte, con todo este contexto ya pasado ahí.

## Pendientes reales para el submission

1. **Confirmar que el segundo fix de timeout funcionó** — revisar la
   corrida del 28 de agosto (viernes) en TODOS los horarios (7am, 8:30am,
   12pm, 2pm, 4pm), no solo el de las 12pm
2. **Grabar el video demo** (guion ya definido)
3. Terminar el resto del formulario de Devpost (teammates, disclosures)
4. Monitorear producción real durante la primera semana completa con
   ambos fixes de timeout aplicados

## Fuera de alcance a propósito

- Detección de reuniones agendadas vía HubSpot Meetings real
- Vigilancia de bandeja en tiempo real (cada minuto) — batch diario a las
  7am, decisión consciente de arquitectura

## Convenciones de estilo al hablar con el usuario

- Español, "tú/tienes" (NO "vos/tenés")
- Explicaciones honestas, sin inflar el alcance de lo logrado
- No regenerar/reempaquetar el proyecto completo cuando cambian 1-2
  archivos — mostrar o editar solo lo que cambió
- SIEMPRE pedir verificación con comando real antes de aceptar que un
  cambio de código se aplicó correctamente
- NUNCA mencionar sistemas de automatización previos a este proyecto
