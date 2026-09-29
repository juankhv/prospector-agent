# Contexto del proyecto — Agente de Prospección (Aptitude)

## ESTADO ACTUAL (29 de septiembre de 2026): AUTOMATIZACIÓN PAUSADA

**Los 5 jobs de Cloud Scheduler están PAUSADOS** (no eliminados —
`gcloud scheduler jobs pause <nombre> --location=us-central1` en cada
uno). Causa: Apollo.io agotó por completo los créditos del plan gratuito
(100/mes) — confirmado con un 422 real de la API:
`"BILLING.LIMIT.CREDITS_EXHAUSTED"`, `credit_balance: 0`,
`next_billing_date: "2026-10-10"`. Con el volumen real del proyecto
(10 leads/día ≈ 200+/mes), el plan gratuito es estructuralmente
insuficiente — se va a agotar de nuevo en pocos días cada vez que se
renueve, hasta que se actualice a un plan pago.

**Decisión del usuario (29-sep)**: en vez de actualizar el plan de Apollo
por ahora, pausar toda la automatización y usar el agente MANUALMENTE por
chat (`adk web` o la URL de producción `/dev-ui/`), dándole contactos
específicos (perfil de LinkedIn o email directo) que no requieren
`buscar_leads_apollo` — así se evita seguir generando búsquedas fallidas
mientras se decide sobre el plan.

**Para reanudar la automatización en el futuro**: `gcloud scheduler jobs
resume <nombre> --location=us-central1` para cada uno de los 5 jobs
(`prospeccion-diaria`, `revision-respuestas-diaria`,
`reintento-rechazados-diario`, `seguimiento-diario`,
`revision-aprobaciones-diaria`) — pero SOLO después de resolver el tema
de créditos de Apollo, o va a volver a fallar de inmediato.

**Uso manual mientras tanto**: pedirle directamente al agente, por chat,
"Contactá a esta persona: [URL de LinkedIn]" o "Contactá a [nombre] en
[email], cargo [cargo] en [empresa]" — esto NO pasa por
`buscar_leads_apollo`, solo usa `buscar_persona_por_linkedin` (que sí
consume créditos de Apollo también, cuidado) o el camino directo por
email (Camino C, que no toca Apollo en absoluto — el más seguro de usar
mientras los créditos estén en 0).

## Qué es esto

Agente autónomo de prospección B2B para Aptitude (HRtech, mercado LATAM
hispanohablante), construido con Google ADK + Gemini. Originalmente para
el All Things Agentic Hackathon — **el equipo NO llegó a presentar el
submission a tiempo** (deadline 31 de agosto de 2026). El proyecto sigue
vivo como herramienta de negocio real de Aptitude.

Repositorio de GitHub: https://github.com/juankhv/prospector-agent (público).

## A quién ayuda esto

Juan Carlos Hernández (Juank), Co-Founder/COO de Aptitude, **no tiene
perfil técnico**. Explicar cambios en términos simples. Usa "tú/tienes",
NO "vos/tenés".

## REGLA DE ORO: verificar con evidencia real, nunca confiar en la descripción

Pedir `Select-String -Path <archivo> -Pattern <texto>` en PowerShell y
pegar el resultado real. Nunca aceptar un resumen en prosa como prueba.

## Arquitectura general

Un solo agente orquestador (`agente_prospeccion`, Gemini 3.5 Flash) con
~20 herramientas en `tools.py`, instrucciones en lenguaje natural en
`agent.py`. Dos despliegues en Cloud Run: `prospector-agent` (producción
real) y `prospector-agent-demo` (SIN USO real, era para el hackathon —
considerar apagarla).

### Flujo normal para un lead nuevo

1. `verificar_lista_exclusion(email, empresa)` — SIEMPRE primero
2. `google_search_agent` — investiga, ancla la búsqueda con el DOMINIO
   del email del contacto (no solo el nombre — corrige ambigüedad,
   ej. "Liverpool" tienda vs. ciudad/puerto)
3. `redactar_correo` — siempre habla de Aptitude, link real de HubSpot
   Meetings, prueba social flexible (5 clientes, sin matching por industria)
4. `verificar_correo` — UN SOLO INTENTO, sin reintento — rechazo escala
   directo a "Pendientes de Aprobación"
5. `verificar_contactado_previamente(email)` — chequeo POR EMAIL
   ESPECÍFICO, PERMANENTE, sin ventana de días (una empresa sí puede
   recontactarse con otra persona; un contacto específico nunca vuelve a
   recibir "primer contacto")
6. Si ya_contactado=True: escalar. Si no: `enviar_correo` +
   `crear_negocio_hubspot`

### Prospección diaria bajo demanda

"Hacé una prospección diaria" reparte 10 leads entre 4 sectores. Vive
SOLO en el bloque de producción real (no en demo). Salta duplicados sin
escalar.

### 3 bloques separados en agent.py (bug crítico corregido 28-ago)

(1) reglas siempre-aplican, (2) bienvenida/demo SOLO si
`DEMO_ONLY_INSTANCE='true'`, (3) producción real — NUNCA ofrece modo de
prueba. Nunca volver a mezclar texto entre bloques.

## Bugs y cambios — cronología resumida

- **v3 de `crear_negocio_hubspot`**: fila completa en memoria, mapeo por
  nombre de columna, UNA `append_row`. Nunca volver a versiones previas.
- **Cloud Run**: `--timeout=1800`, `--min-instances=1` (confirmado activo).
- **Cloud Functions**: timeout de sesión subido a 180s.
- **Margen de leads Apollo**: `cantidad+3` / `max(cantidad+5,15)` (4-sep,
  bajado de duplicar para reducir latencia).
- **Cargos de Apollo**: reducidos a solo 2 ("jefe de reclutamiento y
  selección", "talent acquisition manager") el 4-sep para bajar latencia.
- **Error 429 (cuota Gemini)**: `_generar_json_con_gemini` reintenta
  automático hasta 3 veces SOLO si es 429, con esperas 10s/20s. Cloud
  Scheduler NO debe reintentar agresivo para este tipo de error (ya se
  revirtió una vez tras causar envíos duplicados en cascada).
- **Error 400 INVALID_ARGUMENT recurrente** (4 y 11-sep): viene del
  framework ADK (razonamiento del agente orquestador), NO interceptable
  desde nuestro código. Mitigado con 1 reintento en Cloud Scheduler
  (`--max-retry-attempts=1 --min-backoff=300s`) para `prospeccion-diaria`
  — pero este job ahora está PAUSADO (ver Estado Actual arriba).
- **API key de Apollo inválida (10-sep, resuelto)**: la clave vieja
  ("n8n"/"master key", compartida con otro sistema) dejó de funcionar.
  Se creó una clave NUEVA dedicada y se actualizó en `.env`,
  `env-vars.yaml`, `env-vars-demo.yaml`.
- **Créditos de Apollo agotados (29-sep, causa del estado actual)**:
  plan gratuito de 100 créditos/mes insuficiente para el volumen real.
  Confirmado con 422 `CREDITS_EXHAUSTED`. Automatización pausada hasta
  resolver el plan (ver Estado Actual arriba).
- **Ambigüedad de nombres en investigación** (7-sep): corregido usando
  dominio del email como ancla en `google_search_agent`.
- **Detección de rebotes**: ampliada de 6 a 18 palabras clave (3-sep).
- **Contacto previo**: cambiado de "por empresa + 3 días" a "por email,
  permanente" (1-sep) — bug real que permitía reescribirle a la misma
  persona pasados 3 días.

## Patrón bilingüe `es_demo` en Sheets

```python
es_demo = os.environ.get("DEMO_ONLY_INSTANCE", "").lower() == "true"
nombre_pestaña = "Nombre En Inglés" if es_demo else "Nombre En Español"
```
Aplicar a cualquier función nueva que escriba en Sheets.

## Google Sheets: pestañas (producción, español)

- **"Leads Enviados"**: Date, Name, Last Name, Position, Company,
  Industry, Email, Primer Contacto, Estado, Paso Secuencia, Próximo Contacto
- **"Excluidos"**: columna Email (incluye 5 emails agregados 31-ago como
  parche permanente: Banregio, Banco Ganadero, Caja Arequipa, Applus+,
  Heineken México)
- **"Empresas Excluidas"**: columna Empresa
- **"Pendientes de Aprobación"**: Date, Name, Last Name, Position,
  Company, Industry, Email, Subject, Body, Reason, Approved, Sent, Retried

Búsqueda de columnas SIEMPRE por nombre. Columna nueva:
`hoja.resize(cols=N)` antes de `update_cell`.

## Cloud Scheduler: 5 jobs (TODOS PAUSADOS desde 29-sep)

| Job | Horario (Bogotá) | Estado |
|---|---|---|
| revision-respuestas-diaria | 7:00am | PAUSADO |
| reintento-rechazados-diario | 8:30am | PAUSADO |
| prospeccion-diaria | 12:00pm, días hábiles | PAUSADO |
| seguimiento-diario | 2:00pm | PAUSADO |
| revision-aprobaciones-diaria | 4:00pm | PAUSADO |

Reanudar con `gcloud scheduler jobs resume <nombre> --location=us-central1`
cuando se resuelva el tema de créditos de Apollo.

## Variables de entorno

`.env` local y `env-vars.yaml`/`env-vars-demo.yaml` — mismo contenido
salvo `GOOGLE_SHEETS_ID` y `DEMO_ONLY_INSTANCE`.
GOOGLE_CLOUD_LOCATION=us. APOLLO_API_KEY: clave dedicada desde 10-sep,
pero SIN CRÉDITOS desde 29-sep hasta que se actualice el plan o se
renueve el 10-oct (y se agote de nuevo rápido con el volumen actual).

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
"serving 100 percent of traffic" apareció antes.

**Uso manual del agente (mientras está pausada la automatización):**
`https://prospector-agent-405290540774.us-central1.run.app/dev-ui/?app=prospector_agent`

## Diagnóstico de "cero respuestas" (en curso desde antes del 29-sep)

~46+ correos enviados sin respuesta real confirmada. Tasa de rebote real
corregida (detección ampliada). Un caso de reenvío duplicado (ya no puede
repetirse). Señal de posible bloqueo por política/spam en un rebote de
Banregio — no investigado a fondo (reputación de dominio de envío
`go.theaptitude.co` vía Microsoft Graph).

## Pendientes reales abiertos

1. **Decidir sobre el plan de Apollo** — actualizar a plan pago (~200+
   créditos/mes necesarios para el volumen real) o seguir operando
   manualmente con contactos puntuales
2. Reanudar los 5 jobs de Cloud Scheduler cuando se resuelva lo anterior
3. Confirmar efecto de los cambios de latencia (margen reducido, cargos
   simplificados, verificación de un intento) una vez que vuelva a correr
   la automatización
4. Considerar apagar/eliminar `prospector-agent-demo` (sin uso real)
5. Seguir monitoreando tasa de respuesta; investigar reputación de
   dominio si sigue en cero con volumen sostenido
6. Si el error 400 INVALID_ARGUMENT recurrente se repite con frecuencia
   una vez reanudada la automatización, investigar qué contenido
   específico lo dispara (no identificado con certeza)

## Convenciones de estilo al hablar con el usuario

- Español, "tú/tienes" (NO "vos/tenés")
- Explicaciones honestas, sin inflar el alcance de lo logrado
- Mostrar/editar solo lo que cambió, no regenerar todo el proyecto
- SIEMPRE pedir verificación con comando real antes de aceptar un cambio
- NUNCA mencionar sistemas de automatización previos a este proyecto
