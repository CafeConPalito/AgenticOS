# ADR 0026: Meta-agentes: el Arquitecto como un CLI por conversación y propuestas con aprobación

- **Estado**: propuesto
- **Fecha**: 2026-10-25
- **Contexto de decisión**: fase 19 ([spec](../phases/19-meta-agentes/spec.md) · [plan](../phases/19-meta-agentes/plan.md))

## Contexto
La persona quiere crear y mejorar agentes, equipos y pipelines conversando con un **Agente Arquitecto**, y que los agentes puedan proponer agentes nuevos. Nada de eso puede cambiar la configuración sin su aprobación, el Arquitecto debe usar solo lo que existe en la instalación (CLIs, cuentas, skills, documentos, conexiones) y su consumo tiene que contar como el de cualquier otra llamada a un CLI.

## Decisión
1. **El Arquitecto es un CLI interactivo por conversación**: una ejecución de tipo `architect` en un PTY, lanzada con el adapter del CLI (Claude o `agy`) como las de los agentes, en una carpeta de trabajo propia, sin las herramientas propias del CLI y con un **MCP propio** (`/a/<token>/mcp`, *token* por ejecución) de lectura de la instalación y edición de su ficha.
   - Cada mensaje de la persona se escribe en ese mismo proceso; el fin del turno llega por el *hook* `Stop` y el texto de la respuesta se lee del transcript del CLI (por bloques, no letra a letra). La ficha se actualiza en el momento por las llamadas MCP.
   - Tras un rato sin uso, el proceso se cierra y la conversación queda dormida; el siguiente mensaje la retoma con `--resume` / `--conversation` (fase 08). Hay un tope de procesos vivos a la vez.
   - «Nueva conversación» y «Reiniciar» arrancan un CLI limpio, sin el contexto anterior.
   - No es un agente: no aparece en la lista ni recibe tareas.
2. **Nunca escribe fuera de su ficha.** Todo lo que propone (el Arquitecto o un agente con `propose_agent`) es una **`Proposal`** que solo se aplica al aprobarla, en una transacción, entera o por campos.
3. **Conflictos por valor de partida**: una propuesta de cambios guarda el valor de cada campo cuando se hizo; si al aplicarla el valor actual es otro, la persona elige.
4. **Los agentes nuevos existen como borradores desde que se proponen** (se ven, se editan y no reciben tareas); las propuestas de cambios no tocan nada hasta aplicarse, así que el agente sigue trabajando y las ejecuciones en marcha no cambian.
5. **Una sola validación** para la ficha del Arquitecto, `propose_agent` y la importación: las referencias deben existir y el pipeline pasa las reglas del editor (fases 05 y 13).
6. **Campos fijados**: lo que la persona edita a mano queda fijado; el Arquitecto solo puede pedir que se suelte.
7. **Formato `agentic-os.agent` v1** (JSON sin secretos ni ids locales) para exportar, importar y guardar plantillas del usuario.
8. **Cada conversación es una ejecución `architect`**: su consumo se lee del transcript como el de un agente, cuenta en el panel y en el límite diario, y antes de cada mensaje se comprueba que la cuenta esté disponible.

## Alternativas descartadas
- **Una llamada *headless* por turno** (`claude -p --resume`, `agy -p`): permite ver la respuesta letra a letra, pero cada turno arranca el CLI y recarga la sesión (varios segundos), y no estaba claro que `agy -p` admitiera sesión y MCP. Un proceso por conversación reutiliza todo lo de las ejecuciones (PTY, *hooks*, transcript, retomar) y funciona igual en los dos CLIs.
- **Que el Arquitecto cree o cambie agentes directamente** con la API: rompe la aprobación y deja estados intermedios si la conversación se corta.
- **Mandar todo el catálogo en el prompt**: caro y crece con la instalación; las herramientas lo consultan bajo demanda.

## Consecuencias
- Nuevas tablas: conversaciones y mensajes del Arquitecto, propuestas, historial de cambios del agente y plantillas del usuario; `Run.kind` admite `architect`.
- La calidad depende del modelo y de las instrucciones base, que son editables en Ajustes.
- Un CLI vivo ocupa memoria mientras la conversación está abierta; de ahí el cierre por inactividad y el tope de procesos.
- Una conversación larga acumula contexto y encarece cada turno; «Reiniciar» lo limpia y la pantalla muestra lo gastado.
- Si `agy` no permite limitar sus herramientas propias, el Arquitecto funciona solo con Claude hasta que lo permita.
