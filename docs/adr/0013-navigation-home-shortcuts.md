# ADR 0013: Navegación, Inicio y atajos

- **Estado**: aceptado
- **Fecha**: 2026-10-14
- **Contexto de decisión**: fase 09 ([`spec.md`](../phases/09-ux-ui/spec.md), [`plan.md`](../phases/09-ux-ui/plan.md), diseño [`v2`](../design/v2/README.md))

## Contexto
Con la v1.0 la barra lateral tenía ocho destinos al mismo nivel, el Dashboard estaba vacío y las tareas habituales (crear una tarea, aprobar una petición, llegar a la tarea de un agente) exigían varias pantallas.

## Decisión
- **Navegación en la cabecera, sin barra lateral.** Logo (Inicio), «Volver», migas, **Tablero · Ejecuciones · Ajustes** con contadores en vivo, buscador (Ctrl+K), terminal, estado de conexión y tema. Inbox («Peticiones»), Consumo, Agentes y Proyectos siguen con su ruta, pero se llega a ellos desde Inicio, las migas y Ctrl+K.
- **Inicio** (`/`) es el centro: «Te necesitan» (peticiones y avisos de CLI), la rejilla de agentes con sus sesiones y una columna de resumen (proyectos, gasto de hoy, CLIs).
- **Un endpoint agregado de solo lectura**, `GET /api/home`, sondeado cada 3 s, en lugar de componer Inicio con N consultas o de añadir un canal de eventos. Da el estado de cada agente (`running` · `waiting` · `idle` · `draft`, con `waiting` por delante de `running`), sus sesiones vivas o reanudables, los proyectos con quién trabaja en ellos y los contadores de la cabecera. El gasto, los límites y las peticiones siguen saliendo de `/usage/today`, `/inbox` y `/clis`. Pasar a WebSocket más adelante no cambia la UI. **Sin migraciones.**
- **Búsqueda de tareas** `GET /api/tasks?q=&limit=`: por título sin distinguir mayúsculas ni acentos, o por `T-n` / `n`. Se hace en Python (el `LIKE` de SQLite solo ignora mayúsculas ASCII).
- **Diálogos globales con un store** (`stores/dialogs.ts`): Nueva tarea, Nuevo agente, Nuevo proyecto, Ctrl+K y Atajos se montan una vez en `AppShell`. `/agentes/nuevo` y `/proyectos/nuevo` redirigen a la lista y abren el diálogo.
- **Un único gestor de atajos** (`lib/shortcuts.ts`) con la tabla de atajos como fuente única (listener, ayuda y pistas). Las teclas de un carácter (`N`, `?`) no actúan con un modificador, en un campo, en la terminal, con un diálogo abierto ni si «Atajos de una tecla» está apagado. **Ctrl+K no actúa con el foco en la terminal** (es «borrar hasta el final de la línea» en las shells y los CLIs); Ctrl+` y Esc siguen como antes.
- **Los avisos de CLI se derivan en el cliente** de datos existentes (peticiones `quota`/`limit`, `/clis` sin sesión o sin CLIs, límite diario ≥ 95 %). «Posponer» los oculta solo en la sesión. No hay modelo nuevo; la cuota por cuenta queda para la fase 10.
- **Acabado v7** en los tokens y en las primitivas de shadcn: todas las pantallas lo heredan sin tocarlas una a una. `prefers-reduced-motion` anula animaciones y transiciones.

## Alternativas descartadas
- Mantener la barra lateral colapsable: no reduce los destinos ni aclara dónde está cada cosa.
- Componer Inicio con las listas existentes: muchas consultas y el estado de cada agente tendría que calcularse en el navegador.
- Atajos por componente: se pisan entre sí y con la terminal.

## Consecuencias
- El contador de Tablero cuenta las tareas abiertas (todas salvo hechas y canceladas, backlog incluido).
- La columna de CLIs muestra el % del límite diario del usuario, no la cuota de la cuenta, que los CLIs no exponen.
