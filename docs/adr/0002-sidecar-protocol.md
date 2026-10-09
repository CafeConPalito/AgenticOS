# ADR 0002: Protocolo del backend como sidecar de Tauri

- **Estado**: aceptado
- **Fecha**: 2026-10-08

## Contexto
La app de escritorio (Tauri) arranca el backend FastAPI empaquetado con PyInstaller como un proceso hijo (*sidecar*). Hay que resolver tres cosas:
- cómo saber en qué puerto escucha el backend, sin chocar con otros procesos de la máquina;
- cuándo está listo para recibir peticiones;
- cómo garantizar que no queda vivo cuando la app se cierra, aunque se cierre de forma brusca.

## Decisión
1. **Puerto libre**: Tauri lanza el backend con `--port 0`. El backend abre el socket él mismo (el sistema operativo asigna un puerto libre) y se lo pasa a uvicorn, así que no hay carrera entre elegir el puerto y usarlo.
2. **Handshake por stdout**: cuando uvicorn termina el arranque, el backend imprime una sola línea:
   `AGENTIC_OS_READY {"port": N}`.
   Tauri lee el stdout del sidecar, interpreta esa línea y guarda `http://127.0.0.1:N`.
3. **Descubrimiento desde la UI**: el comando Tauri `backend_url` devuelve la URL o el error `starting`; el frontend reintenta cada 250 ms durante un máximo de 30 s. En desarrollo (build debug) Tauri no lanza el sidecar y devuelve `AGENTIC_OS_BACKEND_URL` o `http://127.0.0.1:8765`.
4. **Sin huérfanos, sin matar el sidecar**: el backend recibe `--parent-pid <pid de Tauri>` y un hilo *watchdog* espera a que ese proceso termine. En Windows abre el handle del proceso al arrancar y bloquea en `WaitForSingleObject`: la detección es inmediata y no puede confundirse si Windows reutiliza el PID. En otros sistemas sondea cada 2 s. Cuando el padre muere, el backend pide el apagado ordenado y, si a los 5 s sigue vivo, fuerza la salida con `os._exit`. **Tauri no mata el sidecar al salir**: hacerlo terminaría el bootloader de PyInstaller `--onefile` antes de que borrase su carpeta de extracción `_MEI*` en `%TEMP%`. El watchdog cubre el cierre normal y el forzado.
5. **Errores de arranque visibles**: si el sidecar no se puede lanzar o termina, Tauri guarda el error y `backend_url` lo devuelve. La UI solo reintenta mientras el error es `starting`; cualquier otro error es definitivo y se muestra al momento. La app no se cae.
6. **Logs a archivo**: el ejecutable empaquetado escribe sus logs en `%APPDATA%\AgenticOS\logs\backend.log` (rotativo, 5 MB × 3), porque Tauri no conserva el stderr del sidecar.
7. **Permisos mínimos**: el sidecar se lanza desde Rust, así que la UI no recibe ningún permiso `shell:*` (capability `core:default` únicamente).

## Consecuencias
- ✅ No hay puertos fijos ni conflictos, y varias instancias pueden convivir.
- ✅ El backend se cierra con la app en todos los casos (verificado en la validación de la fase 00).
- ⚠️ El backend no debe escribir en stdout antes de la línea `AGENTIC_OS_READY`, salvo líneas que Tauri ignora. Los logs van a stderr y al archivo de log.
- ✅ La carpeta temporal de PyInstaller se limpia en cada cierre, tanto normal como forzado.
- ⚠️ El sidecar no se reinicia si se cae: el botón «Reintentar» solo vuelve a consultar. El reinicio automático queda para la fase 08 (robustez).

## Alternativas descartadas
- **Puerto fijo**: choques con otros procesos y con una segunda instancia.
- **Fichero con el puerto en disco**: condiciones de carrera y ficheros que limpiar.
- **Job Objects de Windows**: es específico de Windows y la sustitución del proceso que hace PyInstaller `--onefile` lo complica. El watchdog es multiplataforma y sirve igual en modo servidor.
