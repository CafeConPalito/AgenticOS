# Agentic OS · Pantallas

Ventana de escritorio de 1280–1920px de ancho (mínimo 1200px). Las capturas están en `screenshots/` (1440×900).
Esqueleto común: `AppSidebar` (232/60px) | columna principal = `AppHeader` (52px) + `ErrorBanner` opcional + cuerpo. El cuerpo es una fila (dock a la derecha) o una columna (dock abajo) con el **contenido** (scroll propio) y el `TerminalDock` opcional.

Datos de ejemplo: agentes Ana · Analista (Claude Code), Dev · Desarrollador (Claude Code), Quique · QA (Antigravity) y Rita · Redactora (Antigravity); proyectos Tienda online, App reservas y Blog corporativo; usuaria «Marta».

---

## 1. Dashboard
Capturas: `01a-dashboard-oscuro.png`, `01b-dashboard-claro.png`

**Layout** (padding 22/24/32, max-width 1640, gap 20):
1. Saludo: H1 «Buenos días, Marta» + resumen «2 agentes trabajando · 1 esperándote · 5 peticiones en el Inbox»; a la derecha, la fecha en mono («jueves 8 oct · 10:43»).
2. Rejilla de `AgentCard`: `repeat(auto-fill, minmax(270px,1fr))`, gap 12.
3. Dos columnas `minmax(0,1.55fr) minmax(0,1fr)`, gap 16, alineadas arriba:
   - Izquierda: **Aprobaciones pendientes** (sección con acento ámbar, contador, «Ver Inbox →»), con hasta 3 filas: avatar 26 · meta (tipo, agente, proyecto, «hace 4 min») · título · comando opcional · acciones (`Rechazar` + `Aprobar` en las aprobaciones; `Responder` en el resto, que lleva al Inbox). Vacío: «Nada pendiente. Tus agentes no necesitan nada de ti ahora mismo.»
     Debajo, **Actividad reciente**: timeline de rejilla `44px 14px 1fr` con la hora en mono, un punto coloreado según el tipo de evento y una línea vertical; texto «▪ **Quique** pidió aprobación para ejecutar npm install -D @playwright/test · Tienda online».
   - Derecha: **Consumo de hoy**: 2 KPIs (Tokens «3,82 M», «2,61 M en caché»; Coste «6,51 €», «Límite diario 25 €»), barras por agente (nombre, barra con su color, coste en mono), barra del límite diario («26 % del límite diario») y «Ver detalle →».

**Comportamiento:** clic en una tarjeta de agente → Detalle de su tarea actual (o editor del agente si está inactivo); «Asignar tarea» → dialog Nueva tarea; Aprobar/Rechazar resuelven la petición con un toast. Los cronómetros avanzan en vivo.
**Estados:** vacío (sin agentes; ver EmptyState), cargando (4 skeletons de tarjeta), desconectado (ErrorBanner).

## 2. Agentes — lista
Captura: `02-agentes-lista.png`

**Layout:** cabecera (H1 «Agentes», «Tu equipo. Cada agente es un CLI de IA con su propio rol, instrucciones y permisos.»; botón outline «Crear con el Arquitecto» con `Sparkles` violeta). `Table` dentro de `Card` con las columnas `minmax(220px,1.6fr) 150px minmax(140px,1fr) 150px 80px 120px 28px`: **Agente** (avatar 32, nombre, rol; chip discontinuo violeta «Propuesto por el Arquitecto» si es borrador) · **CLI** (logo + nombre) · **Modelo** (mono muted: `claude-opus-4-1`, `claude-sonnet-4-5`, `gemini-2.5-pro`, `gemini-2.5-flash`) · **Estado** (StatusBadge) · **En cola** (derecha, mono) · **Consumo del mes** (derecha, mono, «131,75 €») · chevron.
**Comportamiento:** clic en la fila → editor. Las filas son focusables y Enter las abre.
**Estados:** vacío («Aún no tienes agentes – Crea tu primer agente o usa una plantilla: Analista, Desarrollador, QA, Redactor, Comercial»), skeleton de 5 filas.

## 3. Agente — detalle / editor
Capturas: `03a-agente-general.png`, `03b-agente-ejecucion.png`, `03c-agente-instrucciones.png`, `03d-agente-borrador-arquitecto.png`

**Layout:**
- (Si es borrador) **banner violeta** a todo el ancho: `Sparkles` · «Borrador propuesto por el Agente Arquitecto» / «Revisa rol, instrucciones y permisos. El agente no podrá recibir tareas hasta que lo apruebes.» · `Rechazar` · `Aprobar agente`.
- Cabecera (padding 20/24/14): avatar 48 · «Dev · Desarrollador» · StatusBadge · CLI · modelo en mono · «Guardar cambios» (primario).
- Tabs subrayadas: **General · Instrucciones · Ejecución · Conocimiento · Skills · Historial**. Contenido con max-width 1100 y padding 20/24.

**Pestañas:**
- **General:** rejilla de 2 columnas: Nombre, Rol · *Avatar y color* (avatar 56, 8 swatches de 28px como `RadioGroup`, «Subir imagen», ayuda «El color identifica al agente en el tablero, las colas y las pestañas de terminal.») · Descripción (textarea).
- **Instrucciones:** `minmax(0,1fr) 260px`. Editor markdown con toolbar (H, B, I, `</>`, • Lista y la etiqueta «Markdown · system prompt»), textarea mono 13/1.65 de 22 filas y pie «N caracteres · ~N tokens». Lateral: «Variables disponibles» (`$PROYECTO $ETAPA $TAREA $MEMORIA $WORKSPACE`) y la nota «Se añaden automáticamente: herramientas MCP de Agentic OS, memoria del proyecto y documentos de conocimiento activos.»
- **Ejecución:**
  - Fila de 2 columnas: CLI como 2 radio cards (Claude Code «Anthropic · claude.cmd» / Antigravity «Google · gemini.exe») y Modelo (`Select`; las opciones dependen del CLI).
  - **Modo de permisos:** 3 radio cards: *Autónomo* (`Zap`) «Ejecuta comandos y edita sin preguntar, siempre dentro de su workspace.» · *Restringido* (`Lock`) «Lee y edita archivos. Sin red ni comandos de sistema.» · *Preguntar* (`Hand`) «Pide aprobación en el Inbox antes de cada comando.»
  - **Herramientas permitidas:** chips de toggle: Leer archivos, Editar archivos, Terminal, Git, Web fetch, MCP agentic-os, Navegador (Playwright).
  - 3 tarjetas: «Concurrencia máxima / Tareas a la vez» (stepper 1–8) · «Puede lanzar subagentes / Ejecuciones hijas en paralelo» (Switch) · «Puede crear tareas / En el backlog de sus proyectos» (Switch).
- **Conocimiento:** `KnowledgePanel level="agente" section="docs"`.
- **Skills:** `KnowledgePanel level="agente" section="skills"`.
- **Historial:** tabla con las columnas Inicio, Tarea (+ ID de sesión), Proyecto, Estado, Tokens, Coste y Duración. Vacío: «Este agente todavía no ha ejecutado ninguna tarea.»

**Comportamiento:** «Guardar cambios» → toast «Cambios guardados · Dev · Desarrollador usará la nueva configuración en la próxima ejecución». Aprobar borrador → estado Inactivo + toast. Rechazar → vuelve a la lista, el borrador desaparece y se lanza un toast.

## 4. Proyectos — lista
Captura: `05-proyectos-lista.png`

Tabla con las columnas `minmax(180px,1.2fr) minmax(220px,1.4fr) minmax(150px,1fr) minmax(200px,1.2fr) 100px 120px`: **Proyecto** (cuadrado de color de 12px, nombre y los avatares solapados de los agentes que trabajan ahora) · **Carpeta** (mono, `D:\proyectos\tienda-online`) · **Git** (`GitBranch` + rama mono; «—» si no hay git) · **Pipeline** (nombre «Desarrollo web» + etapas «Requisitos → Desarrollo → QA») · **Abiertas** · **Último movimiento** («hace 40 s»). Clic → detalle.

## 5. Proyecto — detalle
Capturas: `06a-proyecto-resumen.png`, `06b-proyecto-pipeline.png`, `06c-proyecto-memoria.png`, `08-conocimiento-y-skills.png`

Cabecera: cuadrado de color de 40px · nombre · línea mono con la ruta, «⎇ rama» y el modo de workspace · «Abrir carpeta». Tabs: **Resumen · Tareas · Pipeline · Memoria del proyecto · Conocimiento · Ajustes**. Max-width 1400.

- **Resumen:** 4 KPIs (Tareas abiertas, En ejecución, Esperando humano, Coste del mes) · «Ahora mismo» (tareas en ejecución o esperando; clic → detalle; vacío: «Ningún agente trabaja en este proyecto ahora mismo.») · mini-lista del pipeline.
- **Tareas:** tabla con ID, Tarea, Etapa, Estado, Agente, Prioridad y Coste. Clic → detalle.
- **Pipeline (editor visual):**
  - Cabecera: «Editor de pipeline» / «Cada etapa la ejecuta un agente. Pulsa el avatar para cambiarlo y usa las flechas para reordenar.» · «Añadir etapa» (botón discontinuo).
  - Lienzo con borde, radio 12, fondo `--subtle` con una trama de puntos (`radial-gradient(var(--border) 1px, transparent 1px)` de 16px) y padding 28.
  - Rejilla `repeat(n, minmax(0,1fr))` con column-gap de 44px. **Tarjeta de etapa**: «ETAPA n» (mono 11) · ← → × · nombre 15/500 · selector de agente (avatar 24 + nombre + rol + `ChevronsUpDown`) · «● Puede rechazar» (failed) en la etapa de QA.
  - Conector → entre etapas: línea de 2px `--ring` de 32px con una punta de flecha.
  - **Flecha de rechazo:** fila 2 de la rejilla, que abarca de la etapa origen a la destino, con un borde discontinuo de 2px `--status-failed` (sin borde superior), radio inferior de 12, 34px de alto y márgenes laterales de media columna para que salga y entre por el centro de cada tarjeta; punta ↑ en el destino; etiqueta centrada «↩ Si QA rechaza → vuelve a Desarrollo».
  - **Comportamiento:** ← → reordenan (la flecha de rechazo se recalcula), × elimina (mínimo 1 etapa), el avatar recorre los agentes y «Añadir etapa» añade «Nueva etapa» al final. Recomendado en la implementación: drag & drop con `@dnd-kit/sortable` además de las flechas.
- **Memoria del proyecto:** «Notas que los agentes escriben con `add_memory` y que leen al empezar cada tarea. Puedes editarlas.» · «Añadir nota». Cada nota: avatar del autor (o «Tú») · fecha · `Editar` ↔ `Guardar` · × · texto (en edición: textarea con borde `--ring`).
- **Conocimiento:** `KnowledgePanel level="proyecto" section="all"`.
- **Ajustes:** «Modo de workspace» con 2 radio cards: *Carpeta directa* («Los agentes trabajan sobre la carpeta del proyecto. Simple, pero solo una tarea a la vez.») / *Git worktree por tarea* («Cada tarea tiene su propio worktree y rama. Permite varias tareas en paralelo sin conflictos.») · Carpeta del proyecto (input mono + «Cambiar…») · «Rama base para worktrees» (`develop`).

## 6. Tablero (Kanban)
Capturas: `07a-tablero-por-estado.png`, `07b-tablero-por-etapa.png`, `07c-tablero-colas-por-agente.png`

**Layout:** a pantalla completa (sin padding de página).
- Toolbar (padding 14/20, borde inferior): segmented **Por estado · Por etapa · Colas por agente** · separador · chips de proyecto (**Todos los proyectos**, Tienda online, App reservas, Blog corporativo; el activo con borde `--ring` y fondo `--accent`) · a la derecha, «Agente» + 5 avatares de filtro (∗ = todos; el activo con borde `--ring`; los no seleccionados con opacidad .45).
- **Por estado:** columnas Backlog, En cola, En ejecución, Esperando humano, En revisión y Hecho, de 276px de ancho (scroll horizontal), fondo `--subtle`, borde y radio 12. Cabecera: punto del estado, título y contador en mono. Tarjetas TaskCard con gap 8. Columna vacía: «Sin tareas».
- **Por etapa:** columnas Requisitos, Briefing, Desarrollo, Redacción, QA, Revisión y Hecho; las tarjetas muestran además su StatusBadge.
- **Colas por agente:** nota «Arrastra las tareas para cambiar el orden en que cada agente las ejecutará. La primera tarjeta es la actual.» Una fila por agente (Card, rejilla `190px 1fr`): a la izquierda avatar, nombre, «rol · CLI», «1 en curso · 2 en cola · concurrencia 2/2»; a la derecha una fila horizontal de QueueCards («Ahora», «#1», «#2»…), mezclando proyectos.

**Comportamiento:** los filtros se combinan (proyecto × agente) y se aplican a las 3 vistas. Clic en una tarjeta → Detalle de tarea. **Drag & drop** en Colas: reordena dentro de la misma fila de agente (`@dnd-kit/sortable`, eje horizontal) y lanza el toast «Cola de Dev reordenada · «Pasarela de pago con Stripe» pasa a la posición #1». Opcional: arrastrar entre columnas por estado = cambiar el estado manualmente.

## 7. Detalle de tarea / ejecución ★ (pantalla principal)
Capturas: `09a-detalle-tarea-observando.png`, `09b-detalle-tarea-interviniendo.png`, `09c-detalle-tarea-claro.png`

**Cabecera** (padding 12/20, borde inferior): ID mono «T-142» · título 17/500 «Login con Google» · StatusBadge (pulsante) · ProjectChip · avatar + «Dev · Desarrollador» · a la derecha las acciones: `Pausar`/`Reanudar` · `Reintentar` · `Abrir worktree` · `Cancelar` (outline destructivo).

**Cuerpo:** rejilla `300px minmax(0,1fr) 316px` con `grid-template-rows: minmax(0,1fr)` que ocupa todo el alto disponible (mínimo 560px).
- **Izquierda** (scroll propio, padding 16, gap 18):
  - *Descripción* (texto).
  - *Etapa del pipeline*: stepper horizontal de píldoras con mini-avatar; la etapa actual va con borde y fondo running y las anteriores en muted.
  - *Subtareas · 3/5*: checklist (`Checkbox`); las hechas van tachadas y en muted, con «@dev» o «@quique» a la derecha.
  - *Historial de transiciones*: puntos coloreados + texto + fecha («QA → Desarrollo · rechazado por Quique: «el redirect tras el callback vuelve a /»» · «hoy 10:31»).
  - *Resumen del agente*: caja `--subtle`.
- **Centro** (padding 14): `TerminalPanel` a todo el alto + línea de info. Por defecto muestra «Solo lectura (observando)».
- **Derecha** (scroll propio, padding 16):
  - *Árbol de ejecución*: Dev · ejecución principal → explorar-auth (hecho), tests-auth (ejecutando) → fixtures-oauth (hecho).
  - *Eventos MCP*: rejilla `40px 1fr` con la hora mono, el nombre de la función en mono violeta y el argumento («update_status: implementando el login con Google: corrigiendo redirect», «spawn_subagent», «add_memory», «request_approval»).
  - *Consumo de la sesión*: rejilla 2×3 con separadores de 1px (Tokens entrada 1,24 M · Tokens salida 86,4 k · Caché (lectura) 3,10 M · Caché (escritura) 212 k · Coste · Duración, en vivo) y «ID de sesión `cc-7f3a91e2-04b8`».

**Comportamiento:**
- **Tomar control** → modo intervención (borde ámbar, píldora, input de stdin con autofocus). Enter envía la línea al PTY. **Devolver al agente** → reanuda la ejecución + toast «Control devuelto a Dev».
- Clic en un nodo del árbol → la terminal central cambia a ese subagente (sale del modo intervención).
- **Pausar** cambia el badge a «En pausa», congela los cronómetros y cambia el botón a «Reanudar». **Cancelar** muestra un toast de confirmación («Se detendrá Dev y sus 2 subagentes»). **Reintentar** crea una nueva sesión en el mismo worktree. **Abrir worktree** abre el Explorador de Windows en `D:\proyectos\app-reservas.wt\T-142`.
- Breadcrumb: «Tablero / App reservas / T-142 · Login con Google» (App reservas lleva a la pestaña Tareas del proyecto).

## 8. Inbox
Captura: `10-inbox.png`

**Layout:** max-width 1080. Cabecera con H1 «Inbox», «Peticiones de tus agentes: aprobaciones, preguntas, bloqueos y entregas.» y a la derecha el segmented **Pendientes (n) · Resueltas (n)**. Lista de `InboxItem` con gap 16.
**Ejemplos:**
- Aprobación · Quique · Tienda online: «¿Puedo ejecutar este comando?» `npm install -D @playwright/test`.
- Pregunta · Dev · App reservas: «¿Usamos Postgres o SQLite para las reservas?» (opciones Postgres / SQLite).
- Bloqueo · Ana: «Me falta la clave de test de Stripe».
- Aprobación · Dev: «¿Puedo hacer push de la rama?» `git push origin feature/login-google`.
- Tarea completada · Rita: «Guía de estilo editorial».

**Comportamiento:** acciones rápidas (ver InboxItem). Al resolver, el elemento pasa a «Resueltas» con el resultado. El contador de la sidebar se actualiza. Vacío: «Bandeja al día».

## 9. Consumo
Captura: `11-consumo.png`

**Layout** (max-width 1640, gap 16):
1. Cabecera + segmented de periodo **7 días · 30 días · 90 días**.
2. 4 KPIs (Coste «160,38 €» «+12 % vs. periodo anterior» · Tokens «66,08 M» «68 % servidos desde caché» · Horas de agente «83,4 h» «equivale a 10 jornadas» · Sesiones de CLI «305» «94 % terminadas sin error»).
3. Rejilla `minmax(0,2.2fr) minmax(260px,1fr)`:
   - **Gráfica de barras apiladas** diaria (recharts `BarChart` con `stackId`; un color por agente o por proyecto). Título «Coste diario por agente/proyecto», segmented **Por agente · Por proyecto**, 200px de alto, guías horizontales cada 42px, etiqueta cada 5 días y tooltip «8 oct · 6,51 €».
   - **Reparto del periodo:** por grupo, punto, nombre, coste, % y barra.
4. **Sesiones de CLI:** tabla ordenable (`TanStack Table`) con las columnas Inicio, Agente, Proyecto, Tarea, Modelo, Tokens, Coste y Duración. La cabecera activa va en foreground con ↑/↓ y `aria-sort`. Hacer clic de nuevo invierte el orden.

## 10. Conocimiento y Skills (componente reutilizable `KnowledgePanel`)
Captura: `08-conocimiento-y-skills.png`. Se usa en Ajustes (General), en Proyecto > Conocimiento y en Agente > Conocimiento/Skills.

Props: `level: 'general'|'proyecto'|'agente'`, `scopeName`, `section: 'all'|'docs'|'skills'`.
- Cabecera: título («Conocimiento y skills» / «Conocimiento» / «Skills») + «Disponible para {ámbito}» · segmented **General · Proyecto · Agente**.
- **Zona de subida** (`react-dropzone`): borde discontinuo de 1.5px (`--ring` y fondo ring al 10% mientras se arrastra encima) · icono `Upload` · «Arrastra archivos aquí o **examina**» / «Markdown, código, PDF, Word, Excel e imágenes · hasta 50 MB por archivo» · input de URL «o pega una URL» + «Añadir».
- **Documentos:** tabla con Documento (tag de extensión coloreado: PDF `#FF6B6F`, MD `#8FB4FF`, DOCX `#4CC9F0`, XLSX `#43D392`, PNG `#F5B547`, TS `#B39CFF`, URL `#9DB0D0`, y «Añadido por …»), Tamaño, Añadido, **Indexado** (Indexado / Indexando · 62 % con barra de progreso y punto pulsante / En cola / «Error: imagen sin texto legible») y eliminar.
- **Biblioteca de skills:** rejilla `auto-fill minmax(300px,1fr)`. Cada tarjeta: icono, ID en mono (`revision-codigo`), descripción, Switch, chip «Autoseleccionada» (`WandSparkles`, running) y metadatos («Usada 41 veces»). **Propuesta**: borde discontinuo violeta, sin Switch, con el aviso «Propuesta por Dev – pendiente de aprobar» y los botones Rechazar / Aprobar. Contador «4 activas de 6».

## 11. Crear agente con el Arquitecto
Captura: `04-crear-agente-arquitecto.png`

**Layout:** rejilla `minmax(0,1fr) minmax(380px,.9fr)` que ocupa todo el alto.
- **Izquierda (chat):** cabecera (avatar violeta con `Sparkles`, «Agente Arquitecto» / «Diseña nuevos agentes a partir de una conversación», «Reiniciar») · mensajes (los del arquitecto a la izquierda con avatar «A», en card con borde; los del usuario a la derecha con fondo `--primary-action` y texto blanco; max-width del 78%) · composer (textarea + botón ↑ primario; «Enter para enviar · Mayús+Enter para nueva línea»).
- **Derecha (ficha en vivo, fondo `--subtle`):** «Ficha del agente» + «Ficha completada al N %» + barra de progreso violeta · card con los campos Nombre y rol (avatar + «Carla · Comercial»), CLI y modelo, Permisos, Skills (chips), Conocimiento (archivos en mono) e Instrucciones (bloque `pre` mono). Los campos pendientes se muestran como skeleton · «Crear borrador» (primario; deshabilitado y con opacidad .45 hasta que la ficha está completa) · la nota «El borrador quedará pendiente de tu aprobación antes de poder recibir tareas.»

**Comportamiento:** cada respuesta del Arquitecto rellena campos (con streaming en la implementación real). «Crear borrador» → Editor del agente con el banner de borrador.

## 12. Ajustes
Captura: `12-ajustes.png`

Max-width 1080, gap 22.
1. **CLIs detectados:** card-tabla con logo, nombre y ruta (mono), «v2.0.14», estado («Sesión iniciada» done / «Sin sesión» waiting / «No detectado» failed) + «Comprobado hace 3 h», y botón «Comprobar» (spinner durante la comprobación; después, un toast con el resultado). Ejemplos: Claude Code, Antigravity (Gemini CLI) y Codex CLI (no detectado).
2. Dos columnas:
   - **General:** Carpeta de datos (`C:\Users\marta\AppData\Local\AgenticOS` + «Cambiar…», «Base de datos, logs de sesión y documentos indexados · 1,8 GB») · Idioma (`Select`: Español / English / Català) · Tema (segmented Oscuro / Claro).
   - **Notificaciones de Windows** (Switch): Aprobaciones pendientes · Preguntas de los agentes · Rechazos entre etapas · Tareas completadas · Sonido (cada una con su descripción).
3. **Conocimiento y skills:** `KnowledgePanel level="general"`.

## Elementos globales
- **Terminal acoplable** (`13a-terminal-acoplada.png`): ver TerminalDock. Atajo Ctrl+`.
- **Paleta de comandos** (`13b-paleta-de-comandos.png`): Ctrl+K desde cualquier pantalla.
- **Toast** de ejemplo, que salta 2,2 s después de arrancar: «QA ha rechazado «Login con Google» → vuelve a Desarrollo» con la acción «Ver tarea».
- **Estados de demostración** del prototipo: el ajuste `demoState` = `vacio` / `cargando` / `desconectado`.
