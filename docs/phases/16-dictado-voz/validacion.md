# Fase 16: Dictado por voz · Validación

## Tests automáticos
```
Backend  (uv run pytest tests, suite completa)     exit 0, 100 % ejecutada (1 prueba omitida, ya existente)
Backend  (dictado + modelos locales + describe)    todo en verde tras la revisión de código
Backend  (test_dictation_e2e, sidecar real)        1 passed   (AGENTIC_OS_E2E_BINARY = sidecar de 162,67 MB)
Frontend (vitest run)                              53 files · 503 tests passed
Frontend (npm run build)                           correcto
Lint                                               ruff, eslint, prettier, tsc, cargo fmt y spikes limpios
```
- Tests nuevos: `test_whisper_server` (servidor gestionado, retirada, catálogo y API de modelos), `test_dictation_api` (API, ajustes, pista, audio, cola, nada en disco), `test_dictation_real` y `test_dictation_e2e` (motor real; se saltan si los spikes no han descargado el motor y el modelo `base`) y, en el frontend, `dictation-lib` (WAV, inserción, atajo), `dictation` (componente y atajo mantenido), `dictation-fields`, `dictation-download` y `dictation-settings`.
- El sidecar pesa **162,67 MB** (162,63 MB antes): no se añadió ninguna dependencia. Motor y modelos se descargan.
- Los tests de la suite que marcan tiempo (la cola del dictado) se aflojaron tras fallar una vez con la máquina cargada.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Se dicta una descripción en español, sin conexión, y llega en pocos segundos (< 10 s por minuto de audio) | ⏳ medido en backend · ⏳ falta la prueba con la app instalada | `small-q5_1` con detección de voz: **7,9 s por minuto** (Ryzen 5 5600G, 6 núcleos, solo CPU); `base` 3,0 s; `turbo` 34 s (no cumple). Ver [evidencias](evidencias/s2-s3-whisper-cpp.md). Falta medir desde que se suelta hasta que aparece el texto, con voz real y la red desconectada |
| CA2 | El texto se inserta en el cursor o sustituye la selección sin perder lo que había, y se deshace con `Ctrl+Z` | ✅ inserción · ⏳ `Ctrl+Z` | `dictation-lib.test` y `dictation.test` (cursor, selección, espacios, el ancla sigue a lo que se escribe mientras se transcribe, campo cerrado → portapapeles). jsdom no tiene pila de deshacer: **`Ctrl+Z` queda por comprobar en WebView2** (S5) |
| CA3 | Funcionan el clic y el atajo mantenido; `Esc` cancela; la duración máxima avisa, corta y transcribe | ✅ componentes · ⏳ manual | `dictation.test`: clic, mantener y soltar sin escribir caracteres, repetición ignorada, pulsación corta descartada, pérdida de foco, `Esc`, aviso y corte (temporizadores falsos). Falta probar el atajo `Ctrl+Espacio` en WebView2 (S4) |
| CA4 | El micrófono está en todos los campos listados y es un único componente | ✅ | `dictation-fields.test`: editor Markdown, respuesta y rechazo de la Inbox, descripción de tarea y revisión de código fuente de los demás campos |
| CA5 | La app instalada pide el permiso una vez y lo recuerda; si se deniega, el error explica cómo concederlo | ⏳ | Solo la mitad automática: el error de permiso y su explicación (`dictation.test`, `dictation-settings.test`). **No verificado en WebView2** (S1); la CSP ya admite audio y *worklet* |
| CA6 | Sin modelo el micrófono ofrece descargarlo; los modelos se descargan, eligen y borran en Ajustes › Modelos locales | ✅ · ⏳ descarga real | `dictation-download.test`, `dictation-settings.test`, `test_whisper_server`. Los pines (tamaño y SHA-256) salen de los ficheros reales de los spikes; falta la descarga real desde la app |
| CA7 | El audio no queda en disco ni se hacen peticiones de red al dictar | ✅ disco · ⏳ red | `test_the_audio_never_touches_the_disk` y el e2e empaquetado (sin `.wav` en la carpeta de datos); el motor se lanza sin `--convert` y escucha solo en `127.0.0.1`. Falta revisar el tráfico en la prueba manual |
| CA8 | Con la pista, los nombres se aciertan más | ✅ | `test_the_names_of_the_app_help_whisper_get_the_names_right` (modelo `base` real): con vocabulario hay menos errores que sin él. Spike: 25 % → 9 % con `small`, 0 % con `turbo` (voz sintética) |
| CA9 | Dictar no bloquea la API y los dictados simultáneos se encolan | ✅ | `test_dictations_at_once_wait_for_each_other_and_the_api_stays_up`, `test_two_dictations_at_once_are_done_one_after_the_other` |
| CA10 | Con el sidecar empaquetado, la transcripción de un audio de ejemplo funciona | ✅ | `test_dictation_e2e` con el sidecar reconstruido tras la revisión: `warmup` → `transcribe` (WER < 35 %) y sin audio en disco |
| CA11 | Lint, tests en verde; ADR escrito; `/code-review` resuelto | ✅ | [ADR 0023](../../adr/0023-dictation.md); revisión abajo |

## Code review
`/code-review high` sobre la rama frente a `main`: 10 hallazgos, resueltos en `2565d9b`, cada uno con su test cuando era comprobable.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| `Intro` en la Inbox podía enviar una respuesta vacía, rechazar una revisión sin motivo o enviar dos veces | Alta | Corregido: solo envía con texto y sin otra acción en curso. Tests |
| Cambiar de modelo mataba la transcripción en curso y podía dejar un proceso `whisper-server` huérfano | Alta | Corregido: el servidor se «retira», termina lo que hace y se detiene solo; `stop()` también cierra los retirados. Test |
| Un dictado largo que contenía «suscríbete» o «gracias por ver el video» se descartaba como fantasma | Media | Corregido: las frases solo cuentan en resultados cortos. Test |
| Cerrar el campo o el diálogo mientras se grababa dejaba el micrófono abierto hasta el límite | Media | Corregido: quitar el campo cancela la grabación. Test |
| El atajo aceptaba `Mayús+A` o `Ctrl+Alt+…` (AltGr), que escriben caracteres | Media | Corregido: exige Ctrl, Alt o Meta (no juntos Ctrl y Alt) o una tecla F. Test |
| Mantener el atajo sin modelo grababa y tiraba el audio | Media | Corregido: abre el diálogo de descarga. Test |
| Se perdía el final de la última palabra al soltar | Media | Corregido: el *worklet* entrega el resto del bloque y el grabador lo espera antes de cerrar. Sin test (necesita audio real) |
| Remuestreo lineal sin filtro antialias | Baja | Corregido: se pide el contexto de audio a 16 kHz para que el navegador remuestree; si no puede, se conserva el remuestreo propio |
| Cada dictado leía todos los nombres de agentes, proyectos, equipos y etapas | Baja | Corregido: máximo 100 por tipo |
| Re-exportación muerta de `free_port` | Baja | Corregido |

## Comprobaciones manuales pendientes (con la app instalada y un micrófono)
1. **S1 · Permiso del micrófono en WebView2**: que pregunte una vez, lo recuerde tras reiniciar y que `getUserMedia` y el *worklet* funcionen con `http://tauri.localhost`. Si preguntara en cada arranque, añadir el manejo de `PermissionRequested` en `lib.rs`; si no funcionara, grabar desde el backend. **Cierra CA5.**
2. **S4 · `Ctrl+Espacio` mantenido** dentro de un campo de WebView2: que llegue el `keyup`, no escriba nada y no choque con el IME ni con atajos del sistema.
3. **S5 · `Ctrl+Z`** justo después de dictar: que quite lo dictado. Si no, usar un deshacer propio.
4. **CA1** con voz real: un par de párrafos, red desconectada, tiempo desde soltar hasta el texto.
5. **CA6/CA7**: descarga real del motor y del modelo desde el diálogo, y tráfico de red nulo al dictar.
6. Calidad con voz y micrófono reales (los números de los spikes son de una voz sintética limpia).

## Retro
- **Cambios respecto a la spec**:
  - Solo se midió `whisper.cpp`; `faster-whisper` y Whisper en ONNX no se probaron porque el primero ya cumplía y repite el patrón de `llama.cpp`.
  - El detector de voz (Silero, 885 KB) va siempre activo y se descarga con cada modelo: sin él Whisper inventa texto con el silencio.
  - No se pone en mayúscula la primera letra del texto dictado (Whisper ya lo hace); el espacio se añade por delante y por detrás según los vecinos.
  - Alcance ampliado: la respuesta y el rechazo de la Inbox pasan a ser campos que crecen con el texto (`Intro` envía, `Mayús+Intro` salto de línea), y se añaden las revisiones de propuestas y fichas de conocimiento.
  - **No hecho**: el manejo de `PermissionRequested` en Rust y el botón «Volver a preguntar» (dependen de S1); el plan lo recoge como no resuelto.
  - La indicación de velocidad y calidad de cada modelo es la medida en una sola máquina.
- **Impacto en fases futuras**:
  - La conversación con el Arquitecto (fase 19) tiene dictado añadiendo `dictation` al campo.
  - Fase 21 (instaladores): `whisper.cpp` y su modelo de voz solo existen para Windows x64; hay que añadir los motores de macOS y Linux al catálogo.
  - Fase 22 (modo servidor): decidir dónde se transcribe; hoy el audio va a la máquina del backend.
  - El motor responde con `Access-Control-Allow-Origin: *` mientras está en marcha (solo `127.0.0.1`, solo transcribe); conviene revisarlo si algún día se expone.
  - `ManagedServer` queda disponible para cualquier otro motor local.

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v1.8`
- [ ] `docs/roadmap.md` actualizado
