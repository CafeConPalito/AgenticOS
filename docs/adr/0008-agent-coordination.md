# ADR 0008: Coordinación entre los agentes y Agentic OS

- **Estado**: aceptado
- **Fecha**: 2026-10-10
- **Contexto de decisión**: fase 04 ([`plan.md`](../phases/04-adapters-mcp/plan.md), [`validacion.md`](../phases/04-adapters-mcp/validacion.md))

## Contexto
Para que el scheduler de la fase 05 pueda encadenar trabajo sin que nadie mire la terminal, cada ejecución tiene que:
- arrancar con el contexto de su agente;
- informar de su progreso;
- avisar de que ha terminado;
- dejar un resumen.

El ADR 0004 fijó *cómo* llegan instructions, MCP y hooks a cada CLI sin tocar la configuración del usuario. Este ADR fija el protocolo y los detalles que solo aparecieron con los CLIs reales.

## Decisión
### Servidor MCP `agentic-os`
- Montado en el **propio backend** (`/r/<token>/mcp`), con el SDK oficial `mcp`. No hay un segundo puerto ni un segundo proceso.
- **Token por ejecución**, en memoria; muere con la ejecución (o con el backend).
  - Llega en la ruta (agy) o en `Authorization: Bearer` (Claude).
  - Una pasarela lo traduce a la ejecución y **sobrescribe** cualquier cabecera interna que mande el cliente, así que un token solo actúa sobre su propia ejecución.
- Herramientas: `get_context`, `report_status`, `complete_task` y `write_project_memory`. Cada llamada se guarda como **evento** de la ejecución y se emite en vivo por su WebSocket.

### Hooks
- Un `hook.cmd` por ejecución en la carpeta de datos, referenciado por su **ruta corta 8.3**: agy los ejecuta por `cmd.exe` y rompe las rutas entre comillas.
- Hace un POST con `curl.exe` (incluido en Windows 10/11) a `/r/<token>/hook/<evento>` y **siempre sale con 0**: un hook que falla bloquea la herramienta en agy.
- Eventos:
  - Claude: `SessionStart`, `UserPromptSubmit`, `Stop`, `SessionEnd`;
  - agy: `PreInvocation` (se dispara en cada paso del modelo; solo se registra el que abre turno) y `Stop`.
- En cuanto llegan hooks, **la actividad la marcan ellos** y no la pantalla. agy deja de marcar «Esperando» de forma falsa durante el arranque.

### Fin de la tarea
`complete_task` guarda el resumen. Al siguiente fin de turno (o a los 60 s si no llega), Agentic OS cierra el CLI de forma ordenada y la ejecución termina en el estado nuevo **`completed`**.

### Detalles de agy verificados con agy 1.3.3
- **Conecta el MCP de los plugins de forma perezosa**: hasta que se abre `/mcp` (o el modelo arranca) no hay conexión. El adapter espera a que la entrada esté lista («? for shortcuts»), escribe `/mcp`, espera la conexión, cierra el panel con Esc y entonces escribe el prompt. Así el modelo ve las herramientas desde el primer turno.
- **Ningún archivo de proyecto ni de plugin preaprueba herramientas MCP**: las reglas `mcp(...)` solo valen en la configuración global, que no se toca. Se probaron cinco candidatos. El backend acepta desde la pantalla el diálogo «Allow calling this tool?» **solo para las herramientas `agentic-os_agentic-os/*`**, con «always allow … in this conversation», y deja cualquier otro diálogo al usuario.
- El diálogo de confianza aceptado **se queda dibujado** encima de la TUI: los diálogos solo cuentan si están al final de la pantalla.
- **Prompt de varias líneas**: Enter lo enviaría en el primer salto de línea. Se escribe la primera línea con una indicación, y la tarea completa va a las reglas del plugin (sección «Tarea»).
- **Una sola ejecución de agy por carpeta**, porque el plugin es por carpeta: un segundo lanzamiento recibe 409 `agy_folder_busy`.
- El plugin se borra al terminar y en la recuperación (marcado con el id de la ejecución), y queda excluido de git con `.git/info/exclude`.

### Lo que Agentic OS no responde nunca por el usuario
El aviso de Claude Code al arrancar por primera vez en `bypassPermissions` («Autónomo») es un consentimiento que Claude guarda en la configuración global. La ejecución registra un evento `waiting_for_human` y la UI pide al usuario que tome el control y responda. Solo hay que hacerlo una vez.

## Consecuencias
- ✅ Los dos CLIs reales completan una tarea de principio a fin:
  - leen sus instrucciones y la memoria del proyecto;
  - informan de su estado y escriben memoria;
  - terminan «Completada» con su resumen y cierran solos.

  Funciona también en el sidecar empaquetado.
- ✅ La configuración global del usuario no cambia. Las únicas entradas nuevas son las de agy que ya preveía el ADR 0004: la confianza en la carpeta, y su propio historial de prompts.
- ⚠️ En agy, «Preguntar» no pide permiso para editar archivos del workspace (es la política de agy en su modo por defecto). Sí lo pide para los comandos.
- ⚠️ El flujo de agy depende de textos de su TUI («? for shortcuts», «Allow calling this tool?», `/mcp`). Están centralizados en `services/runs/screen.py` y cubiertos por tests con textos reales.
- ⚠️ Si el modelo no llama a `complete_task`, la ejecución sigue abierta en «Esperando» hasta que el usuario la pare.
