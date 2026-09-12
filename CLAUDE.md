# Contexto del proyecto — Agente de Prospección (Aptitude)

## Qué es esto

Agente autónomo de prospección B2B para Aptitude (HRtech, mercado LATAM
hispanohablante), construido con Google ADK + Gemini. Originalmente para
el All Things Agentic Hackathon — **el equipo NO llegó a presentar el
submission a tiempo** (deadline 31 de agosto de 2026). El proyecto sigue
vivo como herramienta de negocio real de Aptitude, ya sin ningún propósito
de jueces/demo externa.

Repositorio de GitHub: https://github.com/juankhv/prospector-agent (público).

## A quién ayuda esto

Juan Carlos Hernández (Juank), Co-Founder/COO de Aptitude, **no tiene
perfil técnico**. Explicar cambios en términos simples. Usar "tú/tienes",
NO "vos/tenés". Ha usado Claude Code y Antigravity IDE con Gemini como
asistentes de código.

## REGLA DE ORO: verificar con evidencia real, nunca confiar en la descripción

El asistente de código ha descrito más de una vez cambios que nunca se
aplicaron realmente. Única forma confiable: pedir `Select-String -Path
<archivo> -Pattern <texto>` en PowerShell y pegar el resultado real.
Nunca aceptar un resumen en prosa como prueba.

## Arquitectura general

Un solo agente orquestador (`agente_prospeccion`, Gemini 3.5 Flash) con
~20 herramientas en `tools.py`, instrucciones en lenguaje natural en
`agent.py`. Gemini decide en tiempo real qué herramienta llamar — no hay
workflow programado a mano. **Dos despliegues del mismo código en Cloud
Run**: `prospector-agent` (producción real) y `prospector-agent-demo`
(instancia de demo para el hackathon, ya SIN USO real — se puede
considerar apagarla en el futuro, no urgente).

### Flujo normal para un lead nuevo (agent.py, actualizado)

1. `verificar_lista_exclusion(email, empresa)` — SIEMPRE primero
2. `google_search_agent` — investiga la empresa. **IMPORTANTE (7-sep)**:
   la consulta ahora ancla la búsqueda con el DOMINIO del email del
   contacto (ej. "empresa con sitio web liverpool.com.mx"), no solo el
   nombre — corrige ambigüedad cuando el nombre de empresa coincide con
   una ciudad/lugar/entidad no relacionada (bug real: un correo habló del
   "Puerto de Liverpool" en vez de la tienda departamental mexicana).
3. `redactar_correo` — Gemini redacta. SIEMPRE habla de Aptitude, con el
   link real de HubSpot Meetings (https://meetings.hubspot.com/aptitude/demo)
   — fijo, no configurable. La "prueba social" (4-sep) ya NO hace matching
   rígido por industria — puede mencionar libremente cualquier combinación
   de los 5 clientes (Indra, HSBC, Nequi, Bavaria, Veolia Colombia).
4. `verificar_correo` — Gemini audita. **Desde el 4-sep: UN SOLO INTENTO,
   SIN REINTENTO** — cualquier rechazo escala DIRECTO a "Pendientes de
   Aprobación" (antes permitía 2 reintentos de redacción; se quitó para
   bajar latencia por lead — trade-off aceptado: más casos en revisión
   manual, menos tiempo por corrida).
5. Si aprobado: `verificar_contactado_previamente(email)` — **desde el
   1-sep: chequeo POR EMAIL DEL CONTACTO, PERMANENTE, sin ventana de
   días** (antes era por empresa + 3 días hábiles, lo que permitía
   reescribirle a la MISMA persona pasados 3 días — bug real, corregido).
   Una empresa sí puede recontactarse con otra persona distinta; un
   contacto específico que ya recibió correo NUNCA vuelve a recibir un
   "primer contacto" — le corresponde flujo de seguimiento.
6. Si ya_contactado=True: escalar con `marcar_para_revision_humana`
7. Si no: `enviar_correo` + `crear_negocio_hubspot`

### Prospección diaria bajo demanda (agregada 28-ago, ajustada 4-sep)

El usuario puede pedir "hacé una prospección diaria" (reparte 10 leads
entre 4 sectores rotativos) o especificar un sector. Si un lead ya fue
contactado, se SALTA sin escalar (aprovecha el margen extra de Apollo),
pasando al siguiente. **Esta funcionalidad vive SOLO en el bloque de
producción real** (no en el bloque de demo) — movida ahí explícitamente
para que un juez no dispare sin querer una corrida de 10 leads reales
mientras prueba la demo.

### Estructura de bienvenida en 3 bloques (corregido 28-ago, bug crítico)

`agent.py` tiene 3 bloques SEPARADOS sin texto compartido: (1) reglas que
aplican siempre (idioma auto-detectado, escalamiento, aprobar_y_enviar/
marcar_enviado_en_aprobaciones — disponibles en ambas instancias),
(2) bienvenida/funcionalidad de demo SOLO si `DEMO_ONLY_INSTANCE='true'`,
(3) comportamiento de producción real — NUNCA ofrece modo de prueba, NUNCA
pide email para redirigir correos. **Bug corregido**: antes, producción
real podía ofrecer "modo de prueba" si alguien saludaba o decía "test" —
un fallback legado de antes de existir la instancia de demo separada,
nunca se había quitado. **NUNCA volver a mezclar texto entre estos 3
bloques.**

## Bugs y cambios importantes — cronología resumida

- **v1→v3 de `crear_negocio_hubspot`**: v2 tuvo condición de carrera que
  sobrescribió una fila real. v3 (actual): construir fila completa en
  memoria, mapear por nombre de columna, UNA sola `append_row`. Nunca
  volver a v1/v2.
- **Timeout de Cloud Run** (21/24-ago): 504 Gateway Timeout por límite
  default de 300s nunca configurado. Fix: `--timeout=1800` explícito en
  ambos despliegues, y luego `--min-instances=1` (confirmado activo:
  `minScale=1` en la config real) para eliminar arranques en frío.
- **Timeout de creación de sesión** (27-ago): 60s insuficiente para
  arranque en frío lento → subido a 180s en las 5 Cloud Functions.
- **Margen de leads de Apollo insuficiente para cantidades chicas**
  (1-sep): el margen `cantidad*2` solo aplicaba si `cantidad>=5`, pero
  prospección diaria pide ~2-3 por sector → sin margen. Corregido para
  aplicar siempre, luego (4-sep) REDUCIDO a `cantidad+3` /
  `max(cantidad+5,15)` para bajar latencia (56 min una corrida llegó a
  tomar).
- **Filtro de cargos de Apollo**: ampliado de 5→18 (1-sep), luego
  SIMPLIFICADO a solo 2 ("jefe de reclutamiento y selección", "talent
  acquisition manager") el 4-sep para bajar latencia. **10-sep: esto
  causó 0 leads algunos días** — no por falta de candidatos, sino porque
  la API key de Apollo dejó de funcionar (ver abajo). Si el filtro de 2
  cargos resulta insuficiente en el futuro (pool de candidatos agotado
  por el chequeo permanente por email), considerar ampliar un poco (5-6
  cargos) como punto intermedio.
- **Error 429 RESOURCE_EXHAUSTED de Gemini** (7-sep): cuota de API
  agotada a mitad de corrida. El reintento agresivo de Cloud Scheduler
  (`--max-retry-attempts=2`, agregado 4-sep tras un error 400 distinto)
  resultó CONTRAPRODUCENTE — cada reintento reinicia la prospección desde
  cero, sumando 16 correos en vez de 10. Revertido a
  `--max-retry-attempts=0` para `prospeccion-diaria`. Corrección de raíz:
  `_generar_json_con_gemini` en `tools.py` ahora reintenta automáticamente
  hasta 3 veces SOLO si el error es de cuota (429/RESOURCE_EXHAUSTED), con
  esperas 10s/20s; cualquier otro error falla inmediato sin reintento.
- **API key de Apollo inválida (10-sep, resuelto)**: `buscar_leads_apollo`
  empezó a devolver `{'leads': [], 'total': 0}` sin error visible (fail-open
  silencioso) desde el 9 de septiembre — cero correos 2 días seguidos.
  Diagnóstico: probar la API directamente con `requests.post` reveló
  `401 Invalid API key`. La clave en uso se llamaba "n8n" / "master key"
  en el panel de Apollo — compartida con otro sistema/proceso ajeno a
  este proyecto, probablemente rotada o revocada desde ahí sin avisar.
  **Corrección**: se creó una clave NUEVA y DEDICADA solo a este proyecto
  en Apollo.io (Settings → API Keys → Create new key), y se actualizó en
  los 3 archivos (`prospector_agent/.env`, `env-vars.yaml`,
  `env-vars-demo.yaml`). Confirmado funcionando con una llamada de prueba
  antes de redesplegar. **Lección**: si `buscar_leads_apollo` vuelve a
  devolver `{'leads': [], 'total': 0}` de forma persistente (no solo un
  día), sospechar primero de la API key antes que de filtros de
  búsqueda — probar la API directamente con `requests` para ver el
  código de estado real, ya que la función envuelve errores en fail-open
  silencioso.

## Textos bilingües en Sheets — patrón `es_demo`

```python
es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"
nombre_pestaña = "Nombre En Inglés" if es_demo else "Nombre En Español"
```
Aplicado en `crear_negocio_hubspot`, `verificar_lista_exclusion`,
`marcar_para_revision_humana`, `revisar_aprobaciones_pendientes`,
`revisar_respuestas_bandeja`. Cualquier función nueva que escriba en
Sheets debe seguir este patrón.

## Detección de rebotes ampliada (3-sep)

`palabras_rebote` en `revisar_respuestas_bandeja` pasó de 6 a 18 términos
(agregado: "mail delivery system", "message blocked", "delivery has
failed", "wasn't found at", "recipient address rejected", "user unknown",
"access denied", "550 5", "no-reply@tmes.trendmicro.com", "action
required", etc.) — varios formatos reales de rebote (Office 365 nativo,
trendmicro, bloqueos por política) no se detectaban antes. **Cuidado**:
"action required" es genérico, podría dar falsos positivos con
respuestas reales legítimas — monitorear.

## Google Sheets: estructura de pestañas (producción, español)

- **"Leads Enviados"**: Date, Name, Last Name, Position, Company,
  Industry, Email, Primer Contacto, Estado, Paso Secuencia, Próximo Contacto
- **"Excluidos"**: columna Email — incluye 5 emails agregados el 31-ago
  como parche manual (Banregio, Banco Ganadero, Caja Arequipa, Applus+,
  Heineken México), decisión del usuario de dejarlos ahí permanentemente
- **"Empresas Excluidas"**: columna Empresa
- **"Pendientes de Aprobación"**: Date, Name, Last Name, Position,
  Company, Industry, Email, Subject, Body, Reason, Approved, Sent, Retried

Búsqueda de columnas SIEMPRE por nombre, nunca posición fija. Columna
nueva: `hoja.resize(cols=N)` ANTES de `update_cell`.

## Cloud Scheduler: 5 jobs (producción)

| Job | Horario (Bogotá) |
|---|---|
| revision-respuestas-diaria | 7:00am diario |
| reintento-rechazados-diario | 8:30am diario |
| prospeccion-diaria | 12:00pm, solo días hábiles |
| seguimiento-diario | 2:00pm diario |
| revision-aprobaciones-diaria | 4:00pm diario |

Volumen: 10 correos/día. `prospeccion-diaria` tiene `--max-retry-attempts=0`
(revertido el 7-sep, ver arriba). Demo no tiene jobs.

## Variables de entorno

`.env` local y `env-vars.yaml`/`env-vars-demo.yaml` (Cloud Run) — mismo
contenido salvo `GOOGLE_SHEETS_ID` y `DEMO_ONLY_INSTANCE`.
GOOGLE_CLOUD_LOCATION=us (NO us-central1). APOLLO_API_KEY: clave dedicada
nueva desde el 10-sep (ver arriba). TEST_OVERRIDE_EMAIL no existe en
producción.

**Seguridad**: la clave de servicio de Google Sheets fue rotada dos veces
por pegarse en el chat en su momento — nunca mostrar contenido de
credenciales, solo conteos/primeros caracteres.

## Despliegue

**Producción:**
```
adk deploy cloud_run --project=prospector-agent-505122 --region=us-central1 --service_name=prospector-agent --app_name=prospector_agent --with_ui prospector_agent -- --env-vars-file=env-vars.yaml --allow-unauthenticated --clear-base-image --timeout=1800 --min-instances=1
```

**Demo:**
```
adk deploy cloud_run --project=prospector-agent-505122 --region=us-central1 --service_name=prospector-agent-demo --app_name=prospector_agent --with_ui prospector_agent -- --env-vars-file=env-vars-demo.yaml --allow-unauthenticated --clear-base-image --timeout=1800
```

Termina con falso "Deploy failed" (permisos Windows) — ignorar si
"serving 100 percent of traffic" apareció antes. `requirements.txt` en
raíz Y en `prospector_agent/`.

**Cloud Functions** (5, solo producción):
```
gcloud functions deploy <nombre> --gen2 --runtime=python312 --region=us-central1 --source=cloud_function --entry-point=<func> --trigger-http --allow-unauthenticated --timeout=540 --set-env-vars=AGENT_SERVICE_URL=<url-produccion>
```

## Diagnóstico de "cero respuestas" (en curso desde 3-sep)

~46+ correos enviados sin ninguna respuesta real confirmada (usuario
revisa la bandeja a diario). Hallazgos hasta ahora: tasa de rebote real
más alta de lo que Sheets mostraba (corregido con la detección ampliada),
un caso de reenvío duplicado a email ya inválido (ya no puede repetirse),
y una señal de posible bloqueo por política/spam en un rebote de
Banregio ("policy that prohibited the mail"). No se ha investigado a
fondo la reputación del dominio de envío (`go.theaptitude.co` vía
Microsoft Graph) — pendiente si la tasa de rebote sigue alta.

## Pendientes reales abiertos

1. Confirmar que la prospección vuelve a funcionar con normalidad ahora
   que la API key de Apollo está corregida (revisar corrida de mañana)
2. Confirmar el efecto combinado de los cambios de latencia del 4-sep
   (margen reducido, cargos simplificados, verificación de un intento) —
   no se ha vuelto a medir la duración total de una corrida completa
3. Evaluar si el filtro de solo 2 cargos de Apollo da suficiente volumen
   de candidatos nuevos día a día, ahora que la key funciona de nuevo
4. Considerar apagar/eliminar la instancia de demo (`prospector-agent-demo`)
   ya que no tiene uso real desde que no se presentó al hackathon
5. Seguir monitoreando tasa de respuesta real; si sigue en cero con
   volumen sostenido, investigar reputación de dominio de envío

## Error 400 INVALID_ARGUMENT recurrente del propio agente orquestador (4 y 11-sep)

**Patrón que se repitió dos veces** (4-sep y 11-sep, mismo tipo de error
exacto): a mitad de una corrida de prospección, el razonamiento del
propio agente (`agente_prospeccion`, NO una de las herramientas custom)
falla con `google.genai.errors.ClientError: 400 INVALID_ARGUMENT. Request
contains an invalid argument.` — sin más detalle específico. Como viene
del framework ADK (no de `_generar_json_con_gemini`, que sí tiene
reintento desde el 7-sep), NO se puede interceptar ni reintentar desde
nuestro código — el fix de reintento por cuota (429) no cubre este caso.

**Efecto**: toda la corrida se detiene en ese punto, perdiendo los leads
que quedaban en la cola. El 4-sep interrumpió tras ~10 leads procesados;
el 11-sep interrumpió más temprano, resultando en cero correos ese día.

**Corrección aplicada (11-sep)**: en lugar de resolver la causa raíz (no
identificada — probablemente contenido específico de una empresa que
activa un filtro de seguridad de Gemini, pero no se pudo aislar cuál),
se configuró 1 reintento en Cloud Scheduler para `prospeccion-diaria`,
con backoff largo para evitar el problema de cascada que causó el
incidente del 429 el 7-sep:
```
gcloud scheduler jobs update http prospeccion-diaria --location=us-central1 --max-retry-attempts=1 --min-backoff=300s
```
Un reintento único, esperando 5 minutos — suficiente margen para que un
segundo intento probablemente no repita el mismo problema puntual (orden
distinto de leads de Apollo), sin arriesgar el consumo excesivo de cuota
que un reintento agresivo causó antes.

**Si este error 400 se sigue repitiendo con frecuencia** (más de 1-2
veces por semana), valdría la pena investigar más a fondo qué contenido
específico lo dispara — por ejemplo, capturando qué empresa se estaba
procesando justo antes de cada ocurrencia, algo que no se ha logrado
hacer todavía por falta de detalle en los logs disponibles.

## Convenciones de estilo al hablar con el usuario

- Español, "tú/tienes" (NO "vos/tenés")
- Explicaciones honestas, sin inflar el alcance de lo logrado
- Mostrar/editar solo lo que cambió, no regenerar todo el proyecto
- SIEMPRE pedir verificación con comando real antes de aceptar un cambio
- NUNCA mencionar sistemas de automatización previos a este proyecto
