# Agentic OS v7 · paquete de handoff

Diseño de alta fidelidad. Los archivos de `prototype/` son **referencias de diseño en HTML**: muestran el aspecto y el comportamiento, no son código de producción. Hay que recrearlos en la app real (React + Tailwind 4 + shadcn/ui), con los patrones que ya existen en `../code/` y `../v1.1/code/`.

Fuente Ubuntu / Ubuntu Mono, tema navy como principal y paleta corporativa **sin cambios**. Lo que cambia es la jerarquía de la información y el acabado visual.

```
v7/
  README.md            este resumen
  screens.md           pantallas: qué es NUEVO y qué CAMBIA respecto a v4/v1.1
  components.md        componentes NUEVOS y MODIFICADOS
  design-system.md     reglas visuales nuevas (jerarquía, ámbar, superficies, motion)
  tokens.css           tokens completos; los cambios van marcados con «v7»
  screenshots/         14 PNG de 1440×900, navy (03d en claro), sufijo -v2
  prototype/           Agentic OS v7.dc.html navegable (+ RequestActions, UsageBreakdown, support.js)
  code/                React + Tailwind 4 + shadcn de lo nuevo o modificado
```

## Cambios respecto al diseño anterior

**1 · Jerarquía de Inicio (CAMBIA).** El orden sigue las prioridades del usuario: responder → ver a los agentes → proyectos y gasto → configurar CLIs.
- Dos columnas: la principal (`minmax(0,1fr)`) y una **columna lateral de resumen** de 300px, fija al hacer scroll.
- «Te necesitan» ocupa todo el ancho y apila las 3 primeras peticiones con sus acciones. «Ver todas · n» despliega el resto en la misma lista (antes era un carrusel con un menú).
- Debajo van los agentes agrupados por equipo.
- La lateral no tiene tarjetas: muestra Proyectos, Gasto de hoy, CLIs (cuota más alta en gris, ámbar desde el 80 %, cuentas plegables) y Conocimiento.

**2 · Avisos de CLI (NUEVO).** Una cuenta al 95 % de cuota o más, o con la sesión caída, genera una petición en «Te necesitan» con las acciones «Revisar cuentas» / «Reconectar» y «Posponer».

**3 · Navegación superior (CAMBIA).** Tablero · Ejecuciones · **Conocimiento** · Ajustes pasan a la cabecera, que es translúcida. Conocimiento ya no es una tarjeta de Inicio.

**4 · Tarjeta de agente (CAMBIA).**
- Primario: nombre, estado y la tarea actual con su tiempo.
- Secundario (12px, muted): rol · CLI · tareas en cola.
- Al pasar el ratón o con el foco, la línea secundaria se sustituye por coste, tokens, barra de consumo y el botón «Asignar tarea».
- Si el agente está en ejecución, lleva una línea cian animada en el borde superior.

**5 · Otras pantallas (CAMBIA).**
- Ficha de agente: Equipo/CLI/Cuenta/Modelo/Permisos van en «Configuración», plegada al final.
- Detalle de tarea: los datos de sesión van bajo la salida en directo, en pequeño.
- Ejecuciones: la columna de cuenta va en muted y a 12px.

**6 · Acabado visual (CAMBIA).**
- Radios más grandes y separadores suaves.
- Superficies con degradado y sombras en capas.
- Vidrio (backdrop-blur) en la cabecera, los diálogos, Ctrl+K y los toasts.
- Fondo atmosférico con halos de color de marca y trama de puntos.
- Animaciones: entrada escalonada al cargar, botones que se encogen al pulsarlos y diálogos que aparecen con un ligero deslizamiento.

Detalle en `design-system.md`.

## Capturas

| Archivo | Qué muestra |
|---|---|
| `01a-lateral-cuentas-expandidas-v2` | Columna de resumen con las cuentas de Claude Code desplegadas |
| `01b-lateral-cuentas-plegadas-v2` | Columna de resumen plegada (estado por defecto) |
| `03a-inicio-v2` | Inicio normal |
| `03b-inicio-vacio-v2` | Inicio sin peticiones |
| `03c-inicio-aviso-clis-v2` | Inicio con el aviso de cuota de Antigravity al 96 % |
| `03d-inicio-claro-v2` | Inicio en tema claro |
| `04a-nueva-tarea-desde-cabecera-v2` | «Nueva tarea» abierta desde el buscador de la cabecera (Ctrl+K → Nueva tarea) |
| `04b-nueva-tarea-desde-agente-v2` | «Nueva tarea» abierta desde «+» en una tarjeta de agente (agente preseleccionado) |
| `05-nuevo-agente-v2` | Diálogo «Nuevo agente» |
| `06-nuevo-proyecto-v2` | Diálogo «Nuevo proyecto» |
| `07a-paleta-resultados-v2` | Ctrl+K con resultados |
| `07b-paleta-buscar-tarea-v2` | Ctrl+K buscando «login» |
| `08-ayuda-atajos-v2` | Ayuda de atajos (?) |
| `09-ajustes-v2` | Ajustes |

**Adaptaciones respecto a la lista pedida.** v7 no tiene algunas piezas de la entrega v1.1, así que la lista se ha ajustado a lo que existe:
- **Barra lateral expandida/colapsada → columna de resumen de Inicio con las cuentas de CLI desplegadas/plegadas.** v7 no tiene barra lateral de navegación; la navegación está en la cabecera.
- **«Nueva tarea» desde la cabecera → desde el buscador de la cabecera (Ctrl+K) o con la tecla N.** No hay botón dedicado.
- **Ajustes con su índice → Ajustes tal como está** (una sola sección, sin índice).

## Código (`code/`)

| Archivo | Contenido |
|---|---|
| `components/agentic/app-header.tsx` | Cabecera translúcida: migas, navegación superior, buscador, terminal, conexión y tema |
| `components/agentic/summary-aside.tsx` | Columna lateral agrupada de Inicio. Sustituye a «sidebar agrupada»: v7 no tiene sidebar de navegación |
| `components/agentic/command-palette.tsx` | Ctrl+K, `ShortcutsDialog` (?) y `useGlobalShortcuts` |
| `components/agentic/new-task-dialog.tsx` | «Nueva tarea» (título, proyecto, agente) |
| `screens/dashboard.tsx` | Inicio: `NeedsYouPanel`, `CliAlertItem`, `AgentCard` v7, equipos y estados |
| `screens/settings.tsx` | Ajustes |

Dependencias:
- Lo que ya existe en `../code/components/agentic/` (`primitives`, `cards`) y en `../v1.1/code/components/agentic/` (`kbd`, `request-actions`).
- shadcn: `button dialog command input select separator collapsible breadcrumb switch tooltip`.
- Tokens: `v7/tokens.css` sustituye a `../tokens.css`.

**Sin código React, solo prototipo y documentación:** NewAgentDialog, NewProjectDialog, la ficha de agente con «Configuración» plegada, el detalle de tarea y Ejecuciones. Se montan con los mismos componentes base.

## Abrir el prototipo

Abre `prototype/Agentic OS v7.dc.html` en un navegador; necesita los otros tres archivos de la carpeta al lado.

Rutas: `#/`, `#/tablero`, `#/ejecuciones`, `#/conocimiento`, `#/ajustes`, `#/clis`, `#/proyectos`, `#/agente/dev`, `#/tarea/t1`.

Atajos:
- Ctrl+K: paleta de comandos.
- N: nueva tarea.
- ?: ayuda de atajos.
- Ctrl+`: terminal.
- Esc: cerrar diálogo o panel.

Dato de ejemplo cambiado para mostrar el aviso de CLI: la cuota diaria de Antigravity pasa de 82 % a 96 %.
