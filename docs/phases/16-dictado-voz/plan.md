# Fase 16: Dictado por voz · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-23) · en desarrollo (bloque 0)

## Lo que ya se sabe (revisado al escribir el plan)
- **Catálogo** (`services/localmodels/catalog.py`): entradas fijadas (revisión, tamaño y SHA-256) de tipo `embedding`, `ocr`, `vision` y `engine`. Los datos de Hugging Face se generan en `_pins.py` con `spikes/knowledge/s10_emit_catalog.py`. Un `engine` llega como zip (`unpack`) y su `usage.executable` dice qué programa lanzar. Las entradas tienen `platforms = ("win32",)`.
- **Elección** (`selection.py`): `CHOOSABLE = (EMBEDDING, OCR, VISION)` en `app_state["local_models"]`. Hasta que el usuario elige, se usa el modelo por defecto del catálogo, y `active()` solo devuelve un modelo si ya está descargado.
- **Motor como proceso aparte** (`llama.py`, `LlamaServer`): puerto libre en `127.0.0.1`, lanzado sin ventana y con prioridad baja, espera a `/health` y comprueba la memoria libre antes de arrancar. Un hilo lo para tras `IDLE_SECONDS` sin uso, y un candado hace las peticiones de una en una. Es el patrón que sigue el dictado.
- **Ajustes**: los del conocimiento viven en `app_state` (JSON) con `load`/`normalized`/`save` (`knowledge/config.py`) y `GET/PUT /api/settings/knowledge`.
- **Subidas**: la API no usa `multipart` en ningún sitio (los ficheros del conocimiento van por referencia) y `python-multipart` no está en las dependencias.
- **Atajos** (`frontend/src/lib/shortcuts.ts`): una tabla `SHORTCUTS` y un único `keydown` global. `shortcutFor` ignora los campos, la terminal y los diálogos abiertos, y no hay `keyup`.
- **Campos**: `components/ui/textarea.tsx` es el `Textarea` de shadcn, y `MarkdownEditor` lo usa por dentro. La respuesta de la Inbox es un `Input` en `components/requests/RequestActions.tsx`.
- **Tauri** (`desktop/src-tauri`): `tauri = "2"` sin *features*, `lib.rs` solo gestiona el sidecar y no hay código de WebView2. La CSP no tiene `media-src` ni `worker-src`.
- **Sidecar**: 162,6 MB. `onnxruntime`, `numpy` y `tokenizers` ya van dentro.
- **Últimos números**: migración `0018` (esta fase no necesita migración) y ADR `0022`.

## Bloque 0 · Spikes (antes de programar)
Scripts en `spikes/dictation/` y evidencias en `evidencias/`.

**Audios de prueba**: `make_samples.ps1` los genera con las voces españolas de Windows (`System.Speech`), así que son reproducibles y sin licencias. Hay tres:
1. un dictado de ~1 minuto, para la velocidad;
2. uno de ~20 s con nombres propios (agentes, proyectos y términos inventados), para el vocabulario;
3. 10 s de silencio con ruido de fondo, para las alucinaciones.

Además se graba un audio con voz real y micrófono del portátil, que se guarda fuera del repo.

| # | Pregunta | Si falla |
|---|---|---|
| S1 | **Micrófono en WebView2** con la app **empaquetada** (origen `http://tauri.localhost`, no el servidor de desarrollo): ¿`getUserMedia` funciona? ¿Pregunta en cada arranque, una vez o nunca? ¿Hace falta atender `PermissionRequested` desde Rust (`with_webview` + `webview2-com`) y guardar la decisión con `ICoreWebView2Profile4::SetPermissionState`? ¿Qué pasa al denegar y cómo se vuelve a conceder? ¿Cargan un `AudioWorklet` servido desde `'self'` y `enumerateDevices` con etiquetas? | Grabar desde el backend con `sounddevice` (PortAudio). El micrófono se elige en Ajustes con la lista del backend y el nivel llega por WebSocket |
| S2 | **Motor**: se comparan tres candidatos con los tres audios, en CPU, con 4 y 8 hilos.<br>1. `whisper.cpp` (`whisper-server` de la última *release* para Windows x64) con `base`, `small`, `small-q5_1`, `large-v3-turbo-q5_0` y `large-v3-turbo`.<br>2. `faster-whisper` int8 con *small* y *large-v3-turbo*.<br>3. Whisper en ONNX (`onnx-community`) con el `onnxruntime` que ya va dentro.<br>Para cada uno se mide: tiempo de un minuto de audio (CA1: < 10 s), arranque en frío, memoria, palabras erróneas (WER) frente al texto original, tamaño añadido al sidecar o a la descarga, y si acepta PCM sin `ffmpeg` | Si ninguno baja de 10 s con buena calidad, el recomendado es el mejor por debajo de 10 s y en Ajustes se avisa de la calidad |
| S3 | **Vocabulario y alucinaciones**: con el motor de S2, ¿la pista (`prompt` inicial) mejora los nombres propios del audio 2 y cuántos términos caben (≈ 224 *tokens*)? Con el audio 3, ¿qué devuelve Whisper (en español es típico «Subtítulos realizados por la comunidad de Amara.org»)? ¿Bastan el filtro de energía previo y `no_speech_thold`, o hace falta el VAD de `whisper.cpp` (`--vad`, con un modelo Silero de ~1 MB)? | Lista de frases fantasma conocidas que se quitan del resultado si son todo el texto |
| S4 | **Atajo de mantener pulsado** en WebView2: `Ctrl+Espacio`, `Ctrl+Mayús+Espacio`, `F9` y `AltGr`. Para cada uno se comprueba: si llega `keyup`, si `preventDefault` evita escribir el carácter, la repetición de tecla (`e.repeat`), si choca con el IME o con los atajos del sistema y de WebView2, y qué pasa si se suelta con la ventana sin foco | El atajo pasa a ser de pulsar y volver a pulsar, sin mantener |
| S5 | **Insertar con `Ctrl+Z`**: en un `Textarea` controlado por React dentro de WebView2, ¿`document.execCommand('insertText')` en un campo que no tiene el foco (se enfoca, se inserta y se devuelve el foco) entra en la pila de deshacer, dispara `onChange` y deja el cursor bien? | `setRangeText` + evento `input`, con un deshacer propio del componente (`Ctrl+Z` justo después de dictar quita lo dictado) |

## Diseño ([ADR 0023](../../adr/0023-dictation.md), nuevo)
El diseño de abajo da por hecho lo que se espera de los spikes: **`whisper.cpp` como motor descargable**, porque el sidecar no crece y repite el patrón de `llama.cpp`, y **micrófono en el navegador**. Si S1 o S2 dicen otra cosa, se anota en «Cambios al diseño por los spikes» antes de seguir.

### 1. Catálogo y motor (`services/localmodels/`)
- **`catalog.py`**:
  - tipo nuevo `SPEECH = "speech"` en `KINDS`;
  - un motor `whisper-cpp` (`ENGINE`, zip de la *release* fijada, `usage.executable = "whisper-server.exe"`);
  - tres modelos `speech` (p. ej. `whisper-base`, `whisper-small` y `whisper-large-v3-turbo-q5`). Cada `usage` lleva `model` (el `.bin`), `speed` y `quality` (de S2, para Ajustes), `engine = "whisper-cpp"` y, si S3 lo pide, el modelo VAD. El recomendado de S2 es `default`.
  - Los datos se generan en `_pins.py` ampliando el generador de la fase 14.
- **`selection.py`**: `SPEECH` entra en `CHOOSABLE`, y así el tipo `speech` aparece en Ajustes › Modelos locales sin cambios en su API.
- **`server.py`** (nuevo): `ManagedServer` sale de `LlamaServer` y se queda con lo común:
  - puerto libre y lanzamiento con la prioridad como parámetro;
  - espera a que esté listo, comprobación de memoria libre;
  - hilo que lo para tras un tiempo sin uso, candado y `stop()`.

  `LlamaServer` pasa a heredar de él sin cambiar su comportamiento: sus tests no se tocan y tienen que seguir en verde.
- **`whisper.py`** (nuevo, `WhisperServer(ManagedServer)`):
  - lanza `whisper-server -m <modelo> -t <núcleos físicos> --host 127.0.0.1 --port N` (más `--vad` si S3 lo pide) con **prioridad normal**;
  - se para tras **5 minutos** sin uso;
  - `transcribe(wav: bytes, language, prompt)` hace `POST /inference` (`multipart` con el WAV desde memoria, `response_format=json`, `temperature=0`) y devuelve el texto o un `WhisperError(code)`;
  - `warmup()` arranca el motor sin transcribir;
  - `state` puede ser `stopped`, `loading`, `ready` o `busy`;
  - si cambia el modelo elegido, para el proceso y arranca con el nuevo en la siguiente petición.

### 2. Dictado (`services/dictation/`)
- **`config.py`**: ajustes en `app_state["dictation"]`, con el patrón `load`/`normalized`/`save`.
  - `enabled` (sí)
  - `language` (`"es"`, `"auto"` o un código ISO de la lista de Whisper)
  - `shortcut` (el de S4)
  - `max_seconds` (300, entre 30 y 900)
  - `vocabulary` (hasta 200 términos de hasta 60 caracteres)

  El micrófono elegido **no** va aquí: el `deviceId` es del navegador y se guarda en `ui-prefs`.
- **`audio.py`**:
  - valida el WAV con `wave` de la biblioteca estándar: PCM de 16 bits, mono, 16 kHz, no vacío y no más de `max_seconds + 5` s; si no, `bad_audio` o `too_long`;
  - calcula la energía (RMS por ventanas de 30 ms con NumPy) y, si ninguna ventana pasa el umbral de S3, `no_speech` sin llamar al motor.

  Todo en memoria: el audio **nunca se escribe en disco**, ni en el backend ni en `whisper-server` (recibe el `multipart` en memoria y, sin `--convert`, no crea temporales; S2 lo comprueba).
- **`hints.py`**: el `prompt` para Whisper. Primero los términos del usuario y después los nombres de agentes, proyectos, equipos y etapas, sin repetir, hasta el presupuesto de S3. Va en el idioma elegido y en forma de frase: «Agentic OS. Agentes: Kestrel, Lince…», que es como mejor lo usa Whisper.
- **`service.py`**:
  - `transcribe(db, wav)`: ajustes → modelo activo (`no_model` si no hay, `engine_missing` si falta el motor) → `audio.py` → pista → `WhisperServer.transcribe`;
  - limpia el texto: espacios, y frases fantasma de S3 cuando son todo el resultado (en ese caso, `no_speech`);
  - devuelve `{text, seconds, model}`.

  El candado de `WhisperServer` hace las transcripciones de una en una. La espera se cuenta (`queued`) para el estado.

### 3. API (`api/dictation.py`)
- `POST /api/dictation/transcribe`: el cuerpo es el WAV en crudo (`Content-Type: audio/wav`, máximo 30 MB), así que no hace falta `python-multipart`.
  - El *endpoint* es síncrono: FastAPI lo ejecuta en su *pool* de hilos y no bloquea la API (CA9).
  - Responde `{text, seconds, model}`, o `422` / `409` / `503` con `{code, message}`. Los códigos posibles son `disabled`, `no_model`, `engine_missing`, `bad_audio`, `too_long`, `no_speech`, `not_enough_memory`, `start_failed` y `transcription_failed`.
- `POST /api/dictation/warmup`: el frontend lo llama **al empezar a grabar**, así el modelo carga mientras el usuario habla y el arranque en frío no se nota (CA1). Responde `202`.
- `GET /api/dictation/status`: `{enabled, model, engine_installed, model_installed, state, queued}`.
- `GET/PUT /api/settings/dictation`.
- `app.py`: registra el router y crea el `WhisperServer`. Al cerrar la app hace `stop()`, igual que con `LlamaServer`.
- **No se registra nada del contenido**: los logs solo guardan la duración, el modelo, el tiempo y el código de error, nunca el texto ni el audio.

### 4. Frontend
- **Grabación** (`lib/dictation/recorder.ts`): interfaz `Recorder` con `start(deviceId)`, `stop() → Blob`, `cancel()` y `onLevel`. Los tests usan una implementación falsa.
  - La real: `getUserMedia({audio: {deviceId, channelCount: 1, echoCancellation: true, noiseSuppression: true}})` → `AudioContext` → `AudioWorklet` (`public/dictation-worklet.js`, servido desde `'self'`) que acumula `Float32` → al parar, se remuestrea a 16 kHz y se codifica a WAV de 16 bits (`wav.ts`, puro y probado).
  - El nivel sale de un `AnalyserNode` y se actualiza unas 15 veces por segundo.
  - Al parar o cancelar se cierran las pistas y el contexto, para que se apague el indicador de micrófono de Windows.
- **Cola y estado** (`stores/dictation.ts`, zustand):
  - hay una sola grabación a la vez; empezar otra para la anterior y la transcribe;
  - las transcripciones se envían **de una en una** y cada campo sabe si está grabando, en cola, transcribiendo o con error;
  - límite de duración: aviso a los `max − 15` s y parada a los `max`.
- **Inserción** (`lib/dictation/insert.ts`):
  - al empezar se guarda el **ancla**, que es el campo y su selección;
  - mientras se transcribe, un *listener* de `input` sobre el campo desplaza el ancla si el usuario cambia el texto antes de ella (se compara el prefijo común);
  - al llegar el texto se inserta en el ancla, o sustituye lo seleccionado si la selección no ha cambiado, con el método de S5. Si hace falta se añade un espacio delante, y la primera letra va en mayúscula si empieza frase;
  - si el campo ya no está en el documento, el texto va al portapapeles (`navigator.clipboard.writeText`) con un aviso.
- **Componente** (`components/dictation/DictationButton.tsx`):
  - micrófono con sus estados (normal, grabando con nivel y tiempo, en cola, transcribiendo, error con *tooltip* y acción);
  - `aria-pressed`, `aria-live="polite"` para anunciar «Grabando», «Transcribiendo» y el error, y `Esc` cancela;
  - **en una línea**: `Textarea` e `Input` (`components/ui/`) ganan la *prop* `dictation`, que coloca el botón en la esquina y le pasa la referencia del campo. `MarkdownEditor` la reenvía;
  - si el dictado está desactivado (`status.enabled = false`), la *prop* no pinta nada.
- **Sin modelo**: al pulsar sale un *popover* «Descarga un modelo de voz» con el recomendado (tamaño y velocidad) y «Descargar». Usa los *hooks* de descarga de modelos locales y descarga también el motor si falta, con su progreso. Al terminar, el dictado queda listo sin recargar.
- **Atajo de mantener pulsado** (`lib/dictation/hold.ts`, montado una vez en `AppShell`):
  - `keydown` con el atajo de los ajustes (sin contar `e.repeat`) → `preventDefault()` y, si el foco está en un campo con dictado, empieza a grabar en él;
  - `keyup` de cualquiera de sus teclas, o `blur` de la ventana → para y transcribe;
  - una pulsación de menos de 300 ms se descarta sin transcribir.

  Se añade a `SHORTCUTS` (grupo `dictation`, `global: false`) para que salga en la ayuda `?`, y `shortcutFor` no lo trata como de una tecla.
- **Campos** (CA4): `NewTaskDialog` (descripción), `TaskPage` (resumen al completar y motivo de rechazo), `InstructionsTab`, `NewAgentDialog` y `GeneralTab` (descripción del agente), `MemoryTab`, `LaunchRunDialog`, `ProposalReview` (descripción y texto), `DocSheet` (descripción) y `RequestActions`.
- **Respuesta de la Inbox**: el `Input` pasa a `Textarea` de 1 a 6 líneas que crece con el texto. `Enter` envía y `Mayús+Enter` hace salto de línea.
- **Ajustes**:
  - `LocalModelsSection` gana el grupo `speech` con velocidad y calidad, y el motor `whisper-cpp` aparece con los demás motores;
  - **Ajustes › Dictado** (`DictationSection.tsx`, nueva): activar, modelo (atajo a Modelos locales), idioma, atajo (captura de tecla), micrófono (`enumerateDevices`, con «Probar» y su nivel), duración máxima y vocabulario (etiquetas, con los nombres automáticos en gris solo para ver).
- **API** (`api/dictation.ts`): `useDictationStatus`, `useDictationSettings`, `transcribe(blob)` y `warmup()`, más el `fake-backend` de los tests.
- **i18n**: claves `dictation.*` y `settings.dictation.*` en `es.json`.

### 5. Tauri y CSP
- **CSP**: `media-src 'self' blob:` (la prueba de micrófono de Ajustes reproduce lo grabado) y `worker-src 'self'` para el *worklet*.
- **Permiso** (según S1): si WebView2 pregunta en cada arranque, `lib.rs` atiende `PermissionRequested` en la ventana principal (dependencia `webview2-com`, solo en Windows). Para el micrófono y desde el origen de la app, deja que salga el aviso del sistema la primera vez y guarda la respuesta con `SetPermissionState` en el perfil, que persiste. Cualquier otro permiso u origen se deniega.
- **Denegado**: la pestaña Ajustes › Dictado lo detecta (`navigator.permissions.query({name: 'microphone'})` o el error `NotAllowedError`) y explica cómo concederlo: el botón «Volver a preguntar» borra el estado guardado (comando de Tauri) y, si el bloqueo es de Windows, abre `ms-settings:privacy-microphone`.

## Archivos
| Archivo | Cambio |
|---|---|
| `backend/src/agentic_os/services/localmodels/catalog.py`, `_pins.py`, `selection.py` | modificado |
| `backend/src/agentic_os/services/localmodels/server.py`, `whisper.py` | nuevo |
| `backend/src/agentic_os/services/localmodels/llama.py` | modificado (hereda de `ManagedServer`) |
| `backend/src/agentic_os/services/dictation/` (`config.py`, `audio.py`, `hints.py`, `service.py`) | nuevo |
| `backend/src/agentic_os/api/dictation.py`, `schemas/dictation.py` | nuevo |
| `backend/src/agentic_os/app.py` | modificado |
| `backend/tests/test_dictation_audio.py`, `test_dictation_api.py`, `test_dictation_hints.py`, `test_whisper_server.py`, `test_dictation_real.py`, `test_dictation_e2e.py` | nuevo |
| `backend/tests/data/dictation/*.wav` (generados por `make_samples.ps1`, < 2 MB en total) | nuevo |
| `frontend/src/lib/dictation/` (`recorder.ts`, `wav.ts`, `insert.ts`, `hold.ts`) y `stores/dictation.ts` | nuevo |
| `frontend/public/dictation-worklet.js` | nuevo |
| `frontend/src/components/dictation/DictationButton.tsx`, `DownloadSpeechModel.tsx` | nuevo |
| `frontend/src/components/ui/textarea.tsx`, `input.tsx`, `components/MarkdownEditor.tsx` | modificado (`dictation`) |
| `frontend/src/components/requests/RequestActions.tsx` y los campos de la lista del apartado 4 | modificado |
| `frontend/src/lib/shortcuts.ts`, `components/palette/ShortcutsDialog.tsx`, `AppShell` | modificado |
| `frontend/src/pages/settings/DictationSection.tsx` (nuevo), `LocalModelsSection.tsx`, `SettingsPage.tsx` | nuevo / modificado |
| `frontend/src/api/dictation.ts` (nuevo), `stores/ui-prefs.ts`, `i18n/es.json`, `test/fake-backend.ts` | nuevo / modificado |
| `desktop/src-tauri/tauri.conf.json` (CSP), `src/lib.rs`, `Cargo.toml` (según S1) | modificado |
| `docs/adr/0023-dictation.md` | nuevo |
| `spikes/dictation/` | nuevo |

## Tareas (en orden)
1. [ ] **Bloque 0 · Spikes** S1–S5, con sus evidencias, el modelo recomendado, el atajo por defecto y los cambios al diseño anotados en este plan.
2. [x] **Bloque 1 · Motor y catálogo**: `ManagedServer` extraído (con los tests de `LlamaServer` en verde), `WhisperServer`, tipo `speech`, motor y modelos fijados, `selection`.
3. [x] **Bloque 2 · Dictado (backend)**: ajustes, validación del audio y silencio, pista, servicio, limpieza del texto, API (`transcribe`, `warmup`, `status`, ajustes), cola y nada en disco.
4. [x] **Bloque 3 · Núcleo del frontend**: grabador y *worklet*, WAV, cola y estado, inserción con ancla, `DictationButton`, *prop* `dictation`, atajo de mantener pulsado.
5. [x] **Bloque 4 · Campos**: micrófono en todos los campos de la lista y respuesta de la Inbox que crece con el texto.
6. [ ] **Bloque 5 · Ajustes y modelos**: Ajustes › Dictado, grupo `speech` en Modelos locales, descarga desde el micrófono.
7. [ ] **Bloque 6 · Tauri**: CSP, permiso de WebView2 según S1, «Volver a preguntar», prueba con el instalador.
8. [ ] **Bloque 7 · Calidad y e2e**: transcripción real, vocabulario (CA8), e2e con el sidecar empaquetado (CA10) y pruebas manuales CA1, CA3, CA5 y CA7.
9. [ ] **Bloque 8 · Cierre**: `/code-review`, ADR 0023 definitivo, README, `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| Manual: app instalada, red desconectada, dictado de un par de párrafos con el modelo recomendado; tiempo desde soltar hasta el texto (objetivo < 10 s por minuto de audio) | CA1 |
| `dictation.test.tsx` + `insert.test.ts`: inserción en el cursor, sustitución de la selección, espacio y mayúscula, el ancla se desplaza al escribir antes de ella mientras transcribe, otro campo editado no cambia, `Ctrl+Z` quita lo dictado, texto previo intacto ante cualquier error | CA2 |
| `dictation.test.tsx` + `hold.test.ts` (grabador falso y temporizadores falsos): clic para empezar y parar; mantener el atajo graba y soltar transcribe; repetición ignorada; pulsación corta descartada; `blur` para; `Esc` cancela sin llamar a la API; aviso a `max − 15` s y corte a `max` con transcripción | CA3 |
| `dictation-fields.test.tsx`: cada campo de la lista tiene el micrófono; con el dictado desactivado no hay ninguno; la Inbox envía con `Enter` y hace salto con `Mayús+Enter` | CA4 |
| Manual con el instalador: aviso del micrófono una vez, recordado al reiniciar; denegar → mensaje y «Volver a preguntar» | CA5 |
| `dictation-download.test.tsx` (sin modelo → *popover* → descarga del motor y el modelo → listo) + `test_local_models` (tipo `speech` elegible) + prueba manual de descarga real | CA6 |
| `test_dictation_api.py`: con un `WhisperServer` falso, ningún fichero nuevo en la carpeta de datos ni en `%TEMP%` tras transcribir, también si falla; el motor solo escucha en `127.0.0.1` (`test_whisper_server.py`) + revisión del tráfico en la prueba manual | CA7 |
| `test_dictation_real.py` (se salta si no están el motor y el modelo descargados): el audio de nombres propios con y sin vocabulario; con la pista acierta más nombres | CA8 |
| `test_dictation_api.py`: dos transcripciones a la vez se hacen una tras otra (`queued = 1`) mientras otra petición de la API responde al momento | CA9 |
| `test_dictation_e2e.py` (con `AGENTIC_OS_E2E_BINARY` y los modelos descargados): `warmup` → `transcribe` del audio de ejemplo → texto esperado (WER bajo el umbral de S2) | CA10 |
| `test_dictation_audio.py` (WAV erróneo, demasiado largo, silencio → `no_speech`, frase fantasma → `no_speech`), `test_dictation_hints.py` (orden, sin repetidos, presupuesto), `test_whisper_server.py` (arranque, se para sin uso, cambio de modelo, errores), `wav.test.ts` (remuestreo y cabecera) | CA2, CA7, CA8 |
| Lint, suites completas de backend y frontend, `npm run build`, `/code-review` | CA11 |

## Decisiones (ADR)
- [ADR 0023](../../adr/0023-dictation.md) (se escribe en el bloque 0 con los resultados de los spikes):
  - motor de Whisper como programa descargable que corre como proceso aparte con prioridad normal y se para tras 5 minutos sin uso;
  - audio PCM de 16 kHz en WAV, generado en el navegador y enviado en crudo, que nunca se escribe en disco;
  - permiso del micrófono en WebView2;
  - atajo de mantener pulsado;
  - modelos de voz como tipo `speech` del catálogo;
  - `ManagedServer` común con `llama.cpp`.
- Pendiente de los spikes:
  - micrófono en el navegador o en el backend (S1);
  - `whisper.cpp`, `faster-whisper` u ONNX, y el modelo recomendado (S2);
  - VAD o filtro de energía (S3);
  - atajo por defecto (S4);
  - `execCommand` o deshacer propio (S5).
