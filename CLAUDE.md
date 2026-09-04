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

## Cambio de diseño importante: contacto previo ahora es por email, permanente (31 de agosto)

**Problema detectado por el usuario**: la regla original (ventana de 3 días
hábiles, chequeada por EMPRESA) permitía que la prospección diaria volviera
a escribirle un "primer contacto" a la MISMA PERSONA que ya había recibido
uno, simplemente porque pasaron 3+ días — mezclando indebidamente lo que
debería ser flujo de seguimiento con lo que debería ser prospección nueva.
Confirmado en vivo el 31 de agosto: la prospección diaria bajo demanda
reescribió a contactos que ya habían recibido correo, sin escalar.

**Corrección de diseño (decisión explícita del usuario, no revertir)**:
- Una EMPRESA sí puede volver a contactarse — pero solo con una PERSONA
  DISTINTA dentro de esa empresa.
- Un CONTACTO específico (por email exacto), una vez que recibió un primer
  correo, NUNCA vuelve a recibir otro "primer contacto" automático — le
  corresponde el flujo de seguimiento (`buscar_leads_para_seguimiento` /
  `redactar_seguimiento`), no la prospección nueva.
- Ya NO hay ventana de tiempo (se eliminó la lógica de 3 días hábiles y
  `_hace_n_dias_habiles` de esta función específica — esa función sigue
  existiendo para otros usos, solo se dejó de usar aquí).

**Cambios aplicados**:
1. `verificar_contactado_previamente` en `tools.py`: firma cambiada de
   `(empresa: str)` a `(email: str)`. Ahora busca la columna "Email" (no
   "Company"/"Date"), y devuelve `ya_contactado=True` si ese email aparece
   EN CUALQUIER FILA de "Leads Enviados"/"Sent Leads", sin importar la
   fecha. `False` solo si el email nunca apareció.
2. `agent.py`: la llamada ahora es `verificar_contactado_previamente(email)`
   en todos los flujos (normal de leads nuevos, prospección diaria bajo
   demanda). Los mensajes de escalamiento (`razon_rechazo`) ya no dicen
   "esta empresa ya fue contactada" — dicen "este contacto ya fue
   contactado anteriormente — requiere revisión antes de enviarle
   seguimiento" (ES) / "this contact has already been reached out to
   before" (EN).

**Si se toca esta función en el futuro, NUNCA volver a comparar por
empresa ni reintroducir una ventana de días — el chequeo por email,
permanente, es la decisión de negocio correcta y ya confirmada.**

## Pendientes de investigación abiertos al cierre del 31 de agosto (deadline)

1. **Correo real enviado sin protección aparente** — el 31 de agosto, un
   correo salió a `juanita@activatetalent.com` (prospecto real) mientras
   el usuario reportaba estar usando la instancia de DEMO. No quedó
   registrado en ninguna de las tres hojas de seguimiento (Leads Enviados
   de producción, Pendientes de Aprobación de producción, Sent Leads de
   demo) — se descartó que viniera del camino de "exclusión + enviar de
   todas formas" (que sí deja rastro parcial en Pending Approval). Causa
   raíz NO confirmada — quedó sin resolver por falta de tiempo (día límite
   del hackathon). Hipótesis sin confirmar: el modo de prueba pudo haber
   expirado a mitad de sesión (ver punto 2) y el sistema cayó
   silenciosamente a destinatario real sin avisar. **Investigar con
   prioridad después del deadline** — si se repite, hay que decidir si el
   sistema debe RECHAZAR enviar cuando el modo de prueba expira a mitad de
   sesión, en vez de caer silenciosamente a destinatario real.
2. **Pestaña "Demo Config" con estructura vieja**: en la hoja de demo,
   sigue teniendo los encabezados viejos (`Active, TestEmail, Language,
   CompanyName, MeetingURL, ConfiguredAt`) en vez de la estructura actual
   del código (`Active, TestEmail, Language, Country, ConfiguredAt,
   ExpiresAt`) — nunca se recreó porque el código solo escribe encabezados
   nuevos al CREAR la pestaña, no la actualiza si ya existía de antes.
   Esto probablemente rompe la lógica de auto-expiración de 30 minutos
   (`ExpiresAt` no existe en esa fila real). Posiblemente relacionado con
   el punto 1. **Arreglar**: borrar y dejar que el código recree la
   pestaña con la estructura nueva, o migrar manualmente los datos.
3. **5 emails agregados a "Excluidos" en PRODUCCIÓN real como parche
   rápido el 31 de agosto** (Banregio, Banco Ganadero S.A., Caja Arequipa,
   Applus+, Heineken México) — se agregaron para evitar reenvíos
   duplicados el mismo día, ANTES de que existiera el fix de
   `verificar_contactado_previamente` por email. Como "Excluidos" es
   permanente y bloquea también el seguimiento normal (no solo el primer
   contacto), **considerar sacarlos de esa lista** ahora que el fix real
   ya está desplegado, para que puedan recibir seguimiento normal si no
   responden al primer correo.

## Bug real encontrado y corregido: margen de leads no aplicaba a "prospección diaria" (1-3 de septiembre)

**Síntoma**: la nueva funcionalidad de "prospección diaria bajo demanda"
(que reparte 10 leads entre los 4 sectores, ~2-3 por sector) empezó a
devolver muy pocos candidatos nuevos genuinos — algunos días solo
encontraba 1-3 prospectos, todos ya excluidos o contactados, sin buscar
más para completar la cuota de 10.

**Causa raíz**: el margen extra de `buscar_leads_apollo` (agregado el 28
de agosto para el problema similar del job de las 12pm) solo se activaba
cuando `cantidad >= 5`. Como la prospección diaria por sector pide ~2-3
por sector (menor a 5), el margen NUNCA se activaba para esas llamadas —
`max_candidatos` quedaba igual a `cantidad`, sin ningún respaldo para
descartar duplicados/excluidos.

**Corrección aplicada (1 de septiembre)**: se quitó el condicional
`if cantidad >= 5` por completo — ahora el margen aplica SIEMPRE, sin
importar cuán chica sea la cantidad pedida:
- `per_page = max(cantidad * 3, 15)` (antes: condicional con default 25)
- `max_candidatos = cantidad * 2` (antes: `cantidad` sin margen si <5)

**Si se vuelve a tocar esta lógica, NUNCA reintroducir un condicional que
excluya cantidades chicas del margen — ese fue exactamente el origen de
este bug.**

## Otros dos cambios del 1 de septiembre

**Filtro de cargos en Apollo ampliado**: `person_titles` en
`buscar_leads_apollo` pasó de 5 a 18 valores — se agregaron variantes de
gerentes de RRHH, HRBP, head of talent/people, recruiting/talent
acquisition manager, jefe de selección/reclutamiento, en inglés y
español, para ampliar el universo de contactos válidos por sector.

**"Prueba social" simplificada en redacción**: se quitó el matching
rígido de caso de éxito por industria (TI→Indra, banca→HSBC/Nequi,
consumo masivo→Bavaria, utilities→Veolia) tanto en `REDACTOR_SYSTEM_PROMPT`
como en `VERIFICADOR_SYSTEM_PROMPT` — ahora el redactor puede mencionar
libremente cualquier combinación de los 5 clientes (Indra, HSBC, Nequi,
Bavaria, Veolia Colombia) como prueba social general, sin necesidad de que
coincidan con la industria exacta del prospecto. El verificador ya no
rechaza por "caso de éxito incorrecto para la industria".

## Hackathon: NO se pudo presentar (tiempo)

El equipo no llegó a completar el submission de Devpost a tiempo — el
proyecto sigue vivo y en desarrollo activo como herramienta de negocio
real de Aptitude, pero ya NO hay ningún propósito de "jueces" o demo
externa. La instancia `prospector-agent-demo` sigue desplegada pero SIN
USO real — considerar en el futuro si conviene apagarla/eliminarla junto
con el código de `DEMO_ONLY_INSTANCE` para simplificar, aunque no es
urgente (no genera costo relevante estando inactiva). El correo real
enviado sin protección a `juanita@activatetalent.com` (31 de agosto,
causa nunca confirmada) y la estructura vieja de la pestaña "Demo Config"
quedaron **descartados como prioridad** — decisión explícita del usuario,
ya que la instancia de demo no se sigue usando.

## Diagnóstico de "cero respuestas" — hallazgos del 3 de septiembre

**Contexto**: después de ~46 correos enviados en varios días, el usuario
reporta CERO respuestas reales (confirmado revisando la bandeja
`jh@go.theaptitude.co` a diario — no es un problema de detección, no hay
respuestas que detectar).

**Hallazgo 1 — la tasa de rebote real es más alta de lo que Sheets
mostraba**: la columna "Estado" solo tenía 5 filas marcadas "Rebotó" de
46, pero al revisar la bandeja manualmente aparecieron varios rebotes
reales adicionales que el sistema nunca detectó (Corporativo Kosmos, ADN
Tigo/Tigo Paraguay, entre otros) — confirmando un segundo bug real, ver
"Bug: detección de rebotes incompleta" abajo.

**Hallazgo 2 — un contacto recibió el mismo correo DOS VECES** porque
rebotó una vez (26-ago, sí se detectó) y el sistema, con la regla vieja
de "3 días hábiles por empresa", lo volvió a intentar el 31-ago al MISMO
email ya inválido (Kassandra, Caja Arequipa, `kcardenas@cajaarequipa.pe`).
Esto ya no puede repetirse gracias al fix de `verificar_contactado_previamente`
por email permanente (ver sección de arriba) — cualquier email que ya
esté en "Leads Enviados" queda bloqueado para siempre, rebotado o no.

**Hallazgo 3 — al menos un caso de bloqueo por política de spam, no solo
emails inválidos**: el rebote a `julio.trevino@banregio.com` decía
explícitamente "the user or domain... has a policy that prohibited the
mail that you sent" — señal de que el servidor destino puede estar
tratando los correos como spam por contenido o reputación de dominio, no
solo por direcciones inválidas. **No investigado a fondo todavía** — si
la tasa de rebote real (una vez corregida la detección) resulta alta,
esto merece revisión de reputación del dominio de envío
(`go.theaptitude.co` vía Microsoft Graph).

## Bug: detección de rebotes incompleta, corregido el 3 de septiembre

**Causa raíz**: `revisar_respuestas_bandeja` en `tools.py` clasifica un
correo como rebote buscando palabras clave en
`texto_evaluar = f"{remitente_email} {remitente_nombre} {asunto}"`. La
lista `palabras_rebote` original (6 términos: mailer-daemon, postmaster,
undeliverable, no pudo entregarse, delivery status notification, returned
mail) no cubría varios formatos reales vistos en producción: "Mail
Delivery System" (con espacio, Tigo Guatemala/trendmicro.com), "Message
blocked" (Banregio/Tigo — señal de bloqueo por política, ver Hallazgo 3),
notificaciones nativas de Office 365 tipo "wasn't found at" / "Action
Required", y variantes en español como "no fue posible entregar".

**Corrección aplicada**: ampliada a 18 términos, agregando: "mail delivery
system", "message blocked", "delivery has failed", "delivery failed",
"wasn't found at", "no fue posible entregar", "recipient address
rejected", "user unknown", "access denied", "550 5",
"no-reply@tmes.trendmicro.com", "action required".

**Cuidado a futuro**: "action required" es genérico y PODRÍA coincidir
con una respuesta real legítima de un prospecto (ej. si escribe "acción
requerida de mi parte"). Monitorear — si se detectan falsos positivos
(respuestas reales clasificadas como rebote), ese es el término más
probable a ajustar o quitar.

**Corrección manual puntual**: la fila de Tigo Paraguay
(`earmoa@tigo.com.gt`, fila 45 de "Leads Enviados") se actualizó a mano
a Estado="Rebotó", ya que el rebote real ya había pasado antes del fix y
el correo ya estaba leído (fuera del alcance de la próxima revisión
automática, que solo mira no leídos).

## Nuevo tipo de error: 400 INVALID_ARGUMENT de Gemini, corridas interrumpidas (4 de septiembre)

**Síntoma**: `prospeccion-diaria` del 4 de septiembre solo envió 2 correos
(en vez de ~10) y quedó marcada "Con errores" en Cloud Scheduler.

**Causa raíz (distinta a los timeouts anteriores)**: revisando
`gcloud run services logs read prospector-agent`, la corrida procesó
varios leads exitosamente (~17:01 a 17:05 UTC, varias llamadas 200 OK a
Gemini) y luego una llamada del propio agente orquestador falló con:
`google.genai.errors.ClientError: 400 INVALID_ARGUMENT. Request contains
an invalid argument.` Sin más detalle específico de qué campo o contenido
lo causó — el traceback muestra que viene del nivel de razonamiento del
agente (`agente_prospeccion`), no de una de las funciones custom (que ya
tienen su propio manejo de errores). Hipótesis no confirmada: contenido
de la investigación web de un lead específico activó un filtro de
seguridad de Gemini o tenía algún carácter/formato que rompió la
solicitud. No se pudo identificar la empresa exacta — los logs técnicos
no incluyen el contenido de la conversación, y el registro en Sheets se
corta antes del lead que falló.

**Efecto grave**: cuando esto pasa, TODA la corrida se detiene — no solo
se pierde el lead problemático, se pierden todos los que venían después
en la cola ese día, sin ningún reintento (Cloud Scheduler estaba
configurado con `--max-retry-attempts=0`).

**Corrección aplicada**: se actualizó el job `prospeccion-diaria` (no se
recreó, se usó `gcloud scheduler jobs update`) para agregar reintento
automático:
```
gcloud scheduler jobs update http prospeccion-diaria --location=us-central1 --max-retry-attempts=2 --min-backoff=60s
```
Ahora, si el job falla por cualquier motivo (este error de Gemini,
timeout, o cualquier otro), Cloud Scheduler lo reintenta automáticamente
hasta 2 veces más, esperando al menos 60s entre intentos — sin que el
usuario tenga que darse cuenta y dispararlo manualmente. **Aplicar la
misma configuración a los otros 4 jobs si se repite este tipo de fallo en
ellos** (por ahora solo se aplicó a `prospeccion-diaria`, el único que
había fallado así).

**PENDIENTE DE CONFIRMAR**: si este error 400 se repite, valdría la pena
capturar más contexto (por ejemplo, loggear qué lead/empresa se estaba
procesando justo antes de cada llamada a Gemini) para poder diagnosticar
la causa real en vez de solo mitigar con reintentos.

## Latencia alta y ajuste del margen de leads (4 de septiembre)

**Síntoma**: la corrida manual de `prospeccion-diaria` del 4 de septiembre
completó su cuota de 10 leads con éxito, pero tardó **56 minutos** en
total (18:06 a 19:02 UTC) — muy por encima de los 5-10 minutos típicos de
antes, y superando el `--timeout=1800` (30 min) configurado en Cloud Run
(el proceso siguió corriendo en background y terminó bien, pero es un
riesgo real si algún día se corta a mitad de un envío).

**Hipótesis (no confirmada con certeza total, pero coherente en tiempo)**:
el margen de leads siempre activo (`cantidad * 2`, agregado el 1 de
septiembre) combinado con la base creciente de contactos ya alcanzados
(58+ leads acumulados) significa que Apollo devuelve cada vez más
candidatos que YA están en "Leads Enviados" — el agente tiene que ir
descartando uno por uno (cada descarte implica una ida y vuelta con
Gemini), acumulando latencia.

**Correcciones aplicadas (4 de septiembre, sin confirmar todavía si
resuelven la latencia — monitorear próximas corridas)**:
1. Margen de `buscar_leads_apollo` reducido de duplicar (`cantidad * 2`)
   a un margen fijo más chico: `max_candidatos = cantidad + 3`,
   `per_page = max(cantidad + 5, 15)` (antes `cantidad * 3`).
2. `person_titles` simplificado drásticamente: de 18 cargos a solo 2
   ("jefe de reclutamiento y selección", "talent acquisition manager") —
   decisión explícita del usuario para reducir el volumen de candidatos
   que Apollo devuelve y así acotar el trabajo de filtrado por corrida.

**Si la latencia sigue siendo alta después de este cambio**, el siguiente
paso sería subir el `--timeout` de Cloud Run (a 3600s o más) como red de
seguridad, independientemente de si se resuelve la causa raíz — no
aplicado todavía, se prefirió atacar la causa primero.

## Bug crítico corregido: producción ofrecía modo de prueba (28 de agosto)

**Síntoma**: al abrir la URL de PRODUCCIÓN real (sin "-demo") y saludar al
agente, este respondió presentándose como si fuera la instancia de demo —
"Como este es un entorno de demo... facilítame tu dirección de correo para
activar el Modo de Prueba". Si el usuario hubiera dado su email en esa
sesión, todos los correos de esa sesión se habrían redirigido ahí en vez
de a prospectos reales, silenciosamente.

**Causa raíz**: cuando el modo de prueba se diseñó originalmente (antes de
existir la instancia de demo separada), las instrucciones de `agent.py`
incluían un fallback "Si NO existe DEMO_ONLY_INSTANCE, seguí el
comportamiento normal: si el usuario saluda o menciona
'test'/'demo'/'probar', igual ofrecé modo de prueba" — ese fallback nunca
se quitó al construir la instancia de demo dedicada, así que producción
real seguía pudiendo activar modo de prueba con solo un saludo.

**Corrección aplicada**: se reestructuró por completo la sección de
bienvenida en `agent.py` en 3 bloques SIN texto compartido entre ellos:
- **Bloque 1** ("Reglas que aplican SIEMPRE"): idioma de respuesta
  auto-detectado, reglas de escalamiento (aprobar_y_enviar /
  marcar_enviado_en_aprobaciones — disponibles en AMBAS instancias, es
  funcionalidad de negocio real, no solo para jueces), y la nueva sección
  de prospección diaria bajo demanda (ver abajo).
- **Bloque 2** ("Bienvenida y funcionalidad de demo — SOLO si
  DEMO_ONLY_INSTANCE='true'"): todo el contenido específico de jueces
  (presentación, activar_modo_prueba, país, Sheets de solo lectura,
  preguntas sobre el proyecto, explicación de pestañas).
- **Bloque 3** ("Comportamiento de producción real — si
  DEMO_ONLY_INSTANCE NO existe"): explícito y sin ambigüedad — "NUNCA
  ofrezcas activar un modo de prueba, nunca pidas el email de quien te
  escribe para redirigir correos, y nunca menciones 'modo de prueba' de
  ninguna forma".

**Si en el futuro se edita esta sección de bienvenida, mantener los 3
bloques completamente separados — NUNCA volver a un condicional que
comparta texto entre demo y producción, ese fue exactamente el origen de
este bug.**

## Prospección diaria bajo demanda (28 de agosto)

Nueva capacidad conversacional en `agent.py` (Bloque 1, aplica a ambas
instancias): el usuario puede pedirle al agente directamente "hacé una
prospección diaria" (sin especificar sector → reparte 10 leads entre los
4 sectores rotativos, ~2-3 por sector) o "hacé una prospección diaria de
banca/TI/etc." (sector específico → 10 leads de ese sector). Ejecuta el
mismo flujo completo que la corrida automática de las 12pm (exclusión,
investigación, redacción, verificación, contacto previo, envío/escalado),
aprovechando el margen extra de `buscar_leads_apollo` y saltando
duplicados sin escalarlos, igual que la corrida programada.

## Bug de seguridad crítico: producción ofrecía modo de prueba (28 de agosto de 2026)

**Síntoma**: al saludar al agente en la URL de PRODUCCIÓN real (sin
"-demo"), respondió presentándose como si fuera la instancia de demo,
pidiendo el email del usuario para "activar el modo de prueba" — un
comportamiento que solo debería existir en `prospector-agent-demo`.

**Causa raíz**: cuando se construyó el modo de prueba dinámico (antes de
crear la instancia de demo dedicada), las instrucciones de `agent.py`
tenían una rama de fallback: "Si NO existe DEMO_ONLY_INSTANCE, seguí el
comportamiento normal: si el usuario saluda sin instrucción específica o
menciona 'test'/'demo'/'judge'/etc., ofrecé modo de prueba igual". Esa
rama nunca se quitó al construir la instancia de demo separada, así que
CUALQUIERA que abriera la URL de producción y saludara (o usara esas
palabras clave) podía activar el modo de prueba en producción real — y
si daba su email, todos los correos de esa sesión se habrían redirigido
ahí en vez de ir a prospectos reales, silenciosamente.

**Impacto real**: se confirmó con el usuario que, en el incidente que
destapó el bug, nunca llegó a darse un email — ningún correo real se vio
afectado. Pero el bug estuvo latente desde que se creó la instancia de
demo (22 de agosto) hasta esta corrección (28 de agosto).

**Corrección aplicada**: `agent.py` se reestructuró en 3 bloques
completamente separados, sin texto compartido entre ellos:
- **Bloque 1** ("Reglas que aplican SIEMPRE"): idioma de respuesta
  auto-detectado, y — importante — `aprobar_y_enviar`/
  `marcar_enviado_en_aprobaciones` para casos de exclusión/contacto-
  previo/rechazo (decisión explícita: esta funcionalidad de aprobación
  conversacional SÍ debe estar disponible también en producción real,
  no solo en demo).
- **Bloque 2** ("Bienvenida y funcionalidad de demo — SOLO si
  DEMO_ONLY_INSTANCE='true'"): todo el contenido específico de jueces
  (presentación, activar_modo_prueba, país, Sheets de solo lectura,
  preguntas sobre el proyecto, explicación de pestañas). Sin cambios de
  contenido, solo reubicado.
- **Bloque 3** ("Comportamiento de producción real — si
  DEMO_ONLY_INSTANCE NO existe"): explícito y sin ambigüedad — "NUNCA
  ofrezcas activar un modo de prueba, nunca pidas el email de quien te
  escribe para redirigir correos, y nunca menciones 'modo de prueba' de
  ninguna forma".

Ambas instancias redesplegadas. **Lección para el futuro**: cuando se
divide una funcionalidad entre dos instancias (producción/demo), revisar
TODAS las ramas condicionales del código/instrucciones para confirmar que
ninguna quedó con comportamiento compartido no intencional — este bug
existió por 6 días sin que nadie lo notara, porque nadie había abierto la
URL de producción y saludado sin dar una instrucción de tarea específica.

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
