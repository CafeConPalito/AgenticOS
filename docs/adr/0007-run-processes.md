# ADR 0007: Procesos de las ejecuciones

- **Estado**: aceptado
- **Fecha**: 2026-10-10
- **Contexto de decisión**: fase 03 ([`plan.md`](../phases/03-terminales/plan.md), [`validacion.md`](../phases/03-terminales/validacion.md))

## Contexto
Cada ejecución es un CLI interactivo (Claude Code, agy) en una terminal real (ADR 0003). Varias vistas de la UI tienen que verla a la vez, una persona tiene que poder tomar el control, la sesión tiene que sobrevivir a que se cierre la vista y nada puede quedar huérfano cuando se cierra la app.

## Decisión
- **El backend es el dueño del PTY** (ConPTY vía pywinpty en Windows, ptyprocess en Unix). La UI nunca habla con el proceso; cerrar una vista no afecta a la ejecución.
- **Scrollback y log**: toda la salida se guarda en `runs/<id>.log` en la carpeta de datos, y los últimos 2 MB se guardan en memoria. Un visor que se conecta recibe primero un `snapshot` con ese scrollback; una ejecución terminada se reproduce desde el log.
- **Pantalla emulada** (pyte) por ejecución: el backend «lee» la TUI para aceptar el diálogo de confianza, calcular la actividad (`busy`/`idle`) y confirmar que el CLI aceptó la salida.
- **WebSocket por ejecución con varios visores y un único controlador**:
  - el servidor envía `snapshot`, `output`, `state` (estado, actividad, controlador, tamaño) y `exit`;
  - solo el controlador puede escribir. Mientras nadie tiene el control, cualquier visor puede fijar el tamaño;
  - el dock es un **visor pasivo**: adopta el tamaño del PTY y no lo cambia.
- **Tomar control** envía Esc (interrumpe el turno, conserva la sesión). Al **devolver** el control sin haber escrito nada, se manda «Continúa con la tarea.».
- **Parar** = salida ordenada **verificada**:
  - Claude: Esc + `/exit` + Enter. agy: Ctrl+C, esperar el aviso «press ctrl+c again» y un segundo Ctrl+C.
  - Se repite hasta que el CLI muestra su aviso de reanudación. Las TUI descartan las teclas que llegan mientras están ocupadas: medido con los CLIs reales, Claude pierde el primer intento justo después de un turno.
  - Una vez aceptada la salida, el CLI tiene 10 s para cerrarse solo; si no la acepta en 15 s, se termina el proceso.
- **Sin huérfanos**: el backend crea al arrancar un **Job Object con `KILL_ON_JOB_CLOSE`** y se asigna a sí mismo. Todos sus hijos (los CLIs y los procesos que lancen) heredan el job y mueren con él, aunque el backend muera a la fuerza.
- **Recuperación**: al arrancar, las ejecuciones que figuraban vivas se marcan como `interrupted`. Un proceso no puede volver a adoptarse.
- **Empaquetado**: el sidecar incluye `OpenConsole.exe` y `winpty-agent.exe` de pywinpty (`conpty.dll` los arranca desde su carpeta) y la librería `websockets` para uvicorn.

## Consecuencias
- ✅ Varias vistas (página + dock, o dos ventanas) ven lo mismo; reconectar no pierde nada.
- ✅ Cerrar la app con ejecuciones activas no deja ningún CLI vivo, verificado con el sidecar empaquetado (CA7).
- ⚠️ Reiniciar el backend corta las ejecuciones activas: no hay reanudación automática. Se podrá usar `claude --resume <id>` / `agy -c` en una fase futura.
- ⚠️ El flujo depende de textos de las TUIs (diálogo de confianza, pie «esc to…», avisos de salida). Si cambian, fallarán los tests de la pantalla y los de los CLIs reales, no los tests con el CLI falso.
- ⚠️ La actividad de agy marca `idle` durante el arranque, antes de que empiece el turno. Pararlo en ese momento interrumpe el turno y la salida tarda ~18 s (3 intentos), aunque acaba de forma ordenada.
