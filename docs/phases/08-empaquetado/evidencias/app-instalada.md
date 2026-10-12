# Fase 08 · Pruebas con la app instalada

Fecha: 2026-10-12. Equipo de desarrollo (Windows 11 Pro 10.0.26200), instalador `Agentic OS_1.0.0_x64-setup.exe` (32,3 MiB), instalado en silencio (`/S`) en `%LOCALAPPDATA%\Agentic OS`. Las pruebas se hicieron con scripts de PowerShell contra la API del backend de la app instalada. El puerto se localiza por los sockets de los procesos `agentic-os-backend`.

## CA2 · Actualizar encima de una versión anterior con datos
1. Se instala `Agentic OS_0.1.0_x64-setup.exe` (build de la fase 03) y se crean un agente («Dev de prueba 0.1») y un proyecto («Web 0.1»).
2. Se cierra la app y se instala `1.0.0` encima, también en silencio.

```
install exit: 0
url: http://127.0.0.1:64293 · ready in 4 s (includes migrations)
{"status":"ok","name":"Agentic OS","version":"1.0.0"}
agent: Dev de prueba 0.1
project: Web 0.1
backups\agentic-os-0002-20261012-174633.db   61440
backend left:            (ningún proceso del backend tras cerrar)
```
La base de datos de la 0.1.0 (revisión `0002`) se copió antes de migrar y se migró hasta la `0007` sin perder datos.

## CA11 · Prueba de humo (`npm run smoke:installed`)
```
El backend responde                OK http://127.0.0.1:54907 · v1.0.0
Arranque (< 5 s hasta /api/health) OK 3,3 s
Carpeta de datos                   OK C:\Users\usuario\AppData\Roaming\AgenticOS
Base de datos                      OK …\AgenticOS\agentic-os.db
Log del backend                    OK …\AgenticOS\logs\backend.log
La app se cierra                   OK
Sin procesos del backend           OK 3,7 s tras cerrar
Sin CLIs nuevos                    OK antes 1, después 1   (el «claude» que queda es la sesión que hacía la prueba)
Sin carpetas _MEI nuevas           OK antes 0, después 0
```

## CA4 · Una sola instancia
```
1) first instance: http://127.0.0.1:59026 · app processes: 1 · backend processes: 2   (bootloader + Python)
2) after opening a second one: app processes: 1 · second exited: True · backend processes: 2
```

## CA5 · El backend se cae
Se mata el proceso Python que escucha (como en una caída real), cuatro veces seguidas:
```
start: http://127.0.0.1:55581
attempt 1: killed the Python process 8644 of http://127.0.0.1:55581
attempt 2: killed the Python process 7188 of http://127.0.0.1:54769    ← relanzado en otro puerto
attempt 3: killed the Python process 16016 of http://127.0.0.1:56638
attempt 4: killed the Python process 6700 of http://127.0.0.1:57860
(tras el 4.º fallo seguido no se relanza: error definitivo con «Reintentar» y «Abrir logs»)
```
Primer reinicio, matando todos los procesos del backend: relanzado en 3,8 s en un puerto nuevo.

**Limitación encontrada**: cuando el proceso Python muere de golpe, el *bootloader* de PyInstaller `--onefile` no siempre consigue borrar su carpeta `%TEMP%\_MEI*` (los archivos siguen bloqueados un instante). Quedaron 4 carpetas tras las 4 caídas provocadas; se borraron a mano. Solo pasa cuando el backend se cae; en un cierre normal no queda ninguna (prueba de humo). Queda anotado para una fase futura: `--onedir` lo evitaría.

## CA6 y CA7 · Cerrar con ejecuciones activas y «Reanudar sesión» (CLIs reales)
Dos tareas con la descripción «Recuerda la palabra clave GIRASOL. Ahora usa report_status… y espera. Cuando te diga que continúes, usa complete_task con la palabra clave como resumen.»:
- Claude Code 2.1.296: modelo `haiku`, permisos «Preguntar»;
- agy 1.3.3: modelo `gemini-3.8-flash-low`, «Autónomo».

Cuando las dos ejecuciones habían informado y esperaban, se cerró la app:
```
claude: task running · run running/idle · session a8c39ec6-… · reported: True
agy: task running · run running/idle · session 48ac384a-… · reported: True
processes before closing: claude 2 · agy 1
after closing the app: claude 1 · agy 0     (el «claude» restante es la sesión que hacía la prueba)
```
Al reabrir, «Reanudar sesión» (`POST /api/runs/{id}/resume`):
```
claude: old run interrupted · resumable True · task waiting_human/interrupted
claude: resumed as acbba237-… · session a8c39ec6-… (same: True)
agy: old run interrupted · resumable True · task waiting_human/interrupted
agy: resumed as 8084ca9b-… · session 48ac384a-… (same: True)
claude: task done · summary «GIRASOL» · resumed_from ok True
claude: usage old in=6 out=343 cost=0.00397014 · new in=4 out=113 cost=0.00093036 (cost-state)
agy: task done · summary «GIRASOL» · resumed_from ok True
agy: usage old in=40579 out=146 · new in=42665 out=154 (transcript_full)
```
Los dos agentes recuerdan la palabra de la sesión anterior y terminan la tarea. Cada ejecución tiene su propio consumo:
- en Claude, la sesión cortada no dejó `cost-state`, así que la reanudada empieza de cero;
- en agy, la reanudada solo cuenta sus pasos, que vuelven a enviar todo el contexto de la conversación.
