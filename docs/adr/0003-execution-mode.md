# ADR 0003: Modo de ejecución de los agentes y semántica de «Tomar control»

- **Estado**: aceptado
- **Fecha**: 2026-10-09
- **Contexto de decisión**: spike de la fase 01 ([`spike.md`](../phases/01-spike-clis/spike.md), P1–P3, P11)

## Contexto
Cada ejecución de un agente puede correr en el **modo interactivo** del CLI dentro de un pseudo-terminal (PTY), o en **modo headless** (`-p` + `stream-json`). El diseño de la app exige ver la terminal en vivo y que el humano pueda «Tomar control» y luego «Devolver al agente».

## Decisión
1. **Modo por defecto: PTY interactivo** (ConPTY vía pywinpty en Windows), tanto para Claude Code como para `agy`. Es lo único que da una terminal real que el usuario puede observar y en la que puede escribir.
2. **El estado se lee de señales estructuradas, no de la pantalla**:
   - fin de turno → hook `Stop` (los dos CLIs);
   - progreso y fin de tarea → herramientas MCP `report_status` / `complete_task` (ADR 0004);
   - la pantalla (pie de la TUI) solo complementa: «esperando permiso» o «esperando entrada».
3. **Headless como modo secundario**, para ejecuciones sin intervención humana posible (p. ej. tareas programadas) o como degradación si el PTY falla. Mismo adapter y mismos hooks y MCP; la salida `stream-json` se convierte en el log de la ejecución.
4. **«Tomar control»**:
   - La UI envía **Esc** al PTY: los dos CLIs interrumpen el turno en curso («Interrupted · What should … do instead?») sin matar la sesión.
   - El stdin pasa al usuario y la ejecución queda en estado «interviniendo»; el scheduler no envía nada mientras dure.
5. **«Devolver al agente»**: se devuelve el stdin al agente. Si el humano no ha dejado ningún mensaje pendiente, Agentic OS envía «Continúa con la tarea.» para que retome el trabajo.
6. **Salida**: Claude con `/exit`, `agy` con doble Ctrl+C. Si no responde en 15 s, se termina el proceso. Ctrl+C no sirve para Claude por ConPTY.
7. **Diálogo de confianza en la carpeta**: el adapter lo detecta en pantalla y lo acepta, reintentando la tecla hasta ver la opción seleccionada (las teclas que llegan antes de que el menú esté activo se pierden).

## Consecuencias
- ✅ Una sola experiencia para todos los CLIs: terminal real, interrupción con Esc y control compartido.
- ✅ El estado no depende de leer texto de la pantalla, que es frágil entre versiones.
- ⚠️ El adapter depende de detalles de la TUI para la confianza en la carpeta y para el estado del pie; hay que cubrirlo con tests de regresión por versión del CLI.
- ⚠️ Pendiente de verificar en la fase 03: qué hace Esc si el agente está mostrando una petición de permiso (en `agy`, el diálogo indica «esc to cancel»; previsiblemente la deniega). La UI deberá indicarlo.

## Alternativas descartadas
- **Solo headless**: sin terminal en vivo ni intervención humana real, que son requisitos centrales del producto.
- **Pausar el proceso** (suspender el hilo o el proceso): deja el CLI en un estado inconsistente y con timeouts de red; Esc es la interrupción nativa de los dos CLIs.
