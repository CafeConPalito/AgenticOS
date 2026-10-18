# S8 · Recursos del equipo y proceso de trabajo

- **Fecha**: 2026-10-18 · Windows 11, Ryzen 5 5600G + Radeon integrada + NVIDIA RTX 3060.
- **Scripts**: `spikes/knowledge/s8_gpu.py`, `probe_worker.py`.

## CPU y memoria
`psutil` 7.2 (BSD): CPU total y por proceso, y memoria (RSS) de cualquier proceso hijo (`llama-server` incluido). Sin problemas.

## GPU de cualquier fabricante (contadores PDH)
Contador `\GPU Engine(*)\Utilization Percentage` leído con `ctypes` y `pdh.dll` (`PdhAddEnglishCounterW` + `PdhGetFormattedCounterArrayW`):

- Funciona **sin permisos de administrador** ni librerías de terceros. Devolvió **468 instancias** con la integrada y la RTX 3060 presentes.
- Cada instancia se llama `pid_<n>_luid_0x…_phys_<k>_eng_<j>_engtype_<tipo>`: el **`pid`** permite atribuir el uso a los procesos propios (backend, trabajador, `llama-server`), el **`luid`** distingue adaptadores y el **`engtype`** el tipo de motor (`3D`, `Compute_0`, `Copy`, `VideoDecode`…).
- Valor mostrado: para cada adaptador, el motor más ocupado (como el Administrador de tareas), y el de la app como la suma de sus procesos. Dos lecturas separadas 1 s; si el contador falla, la UI muestra «No disponible».
- Ejemplo de lectura en reposo: `3D 2,1 %`, `Copy 0,8 %`, `VideoDecode 1,8 %`.
- Hoy ni los *embeddings* ni el OCR ni `llama.cpp` (build CPU) usan la GPU, así que el valor sirve para ver que **no se está saturando** (que es lo que se pidió) y para el futuro uso de GPU.

## Proceso de trabajo con prioridad baja
`probe_worker.py` se relanza a sí mismo con `--worker`, `creationflags=BELOW_NORMAL_PRIORITY_CLASS | CREATE_NO_WINDOW`, y habla con su padre por líneas JSON (stdin/stdout).

- Prioridad comprobada con `psutil`: **16384 (`BELOW_NORMAL`)** en el trabajador frente a 32 (`NORMAL`) en el padre.
- Operaciones desde el trabajador, sin empaquetar: conversión de un `.docx` con MarkItDown (1,3 s), texto de un PDF (0,03 s), OCR (1,5 s) y *embeddings* de 8 textos con e5 (1,7 s).
- **Lección**: por tuberías, Windows usa la página de códigos local (cp1252) y no UTF-8; un `é` en el JSON rompía el lector del padre (`UnicodeDecodeError`). El protocolo **debe forzar UTF-8** en ambos extremos (`sys.stdin/stdout.reconfigure(encoding="utf-8")` y `encoding="utf-8"` en `Popen`).
- El trabajador ejecuta lo pesado; el padre solo reparte y escribe en la BD.

## Empaquetado del trabajador (ver `s1-markitdown.md`)
Resultado de la prueba con PyInstaller `--onefile`: tamaño del ejecutable y tiempo hasta que el trabajador está listo (relanzar el mismo `.exe` extrae otra vez el paquete).
