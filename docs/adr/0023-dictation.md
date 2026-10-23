# ADR 0023: Dictado por voz local

- **Estado**: aceptado (con una comprobación manual pendiente: el permiso del micrófono en la app instalada)
- **Fecha**: 2026-10-23
- **Contexto de decisión**: fase 16 ([`spec.md`](../phases/16-dictado-voz/spec.md), [`plan.md`](../phases/16-dictado-voz/plan.md), [`evidencias/s2-s3-whisper-cpp.md`](../phases/16-dictado-voz/evidencias/s2-s3-whisper-cpp.md))

## Contexto
La fase 16 permite dictar en los campos de texto largos. La transcripción tiene que ser local (la voz no sale del equipo, funciona sin conexión), rápida en CPU (CA1: menos de 10 s por minuto de audio con el modelo recomendado), sin hacer crecer el ejecutable del backend (162,6 MB) y sin depender de `ffmpeg`. La fase 14 ya resolvió cómo se descargan, verifican y eligen modelos y motores ([ADR 0021](0021-knowledge.md)) y cómo se ejecuta un motor aparte, `llama-server` ([fase 14, bloque 7](../phases/14-conocimiento/plan.md)).

## Decisión

### Motor: `whisper.cpp` como programa descargable, en un proceso aparte
- Se usa `whisper-server` de whisper.cpp (release `b5454`, 8,9 MB comprimido), igual que `llama.cpp`: entra en el catálogo como motor (`whisper-cpp`), se descarga bajo demanda, con tamaño y SHA-256 fijados, y **no va en el instalador ni en el sidecar**.
- Se descartan `faster-whisper` (más dependencias en el sidecar) y Whisper en ONNX (no se midió: `whisper.cpp` ya cumple CA1 con margen y repite un patrón que existe). Si en el futuro hace falta GPU, se añade otra entrada de motor sin tocar el resto.
- `ManagedServer` (`services/localmodels/server.py`) es el ciclo de vida común de los dos motores: puerto libre en `127.0.0.1`, sin ventana, espera de salud, comprobación de memoria, una petición a la vez y parada tras un rato sin uso. `LlamaServer` pasa a heredarlo sin cambiar de comportamiento; `WhisperServer` lo hereda con **prioridad normal** (el usuario espera) y **5 minutos** de inactividad.
- La transcripción nunca corre en el proceso de la API: el endpoint se ejecuta en un hilo de trabajo y el motor es otro proceso, así que la API y la interfaz siguen respondiendo (CA9).

### Modelos: tipo `speech` del catálogo
- Tres modelos fijados por revisión de `ggerganov/whisper.cpp`: `whisper-base` (148 MB, rápido), **`whisper-small`** (`small-q5_1`, 190 MB, recomendado) y `whisper-turbo` (`large-v3-turbo-q5_0`, 574 MB, el mejor y lento). Cada uno incluye el modelo de detección de voz (Silero v5.1.2, 885 KB), que pasa a ser parte de su descarga.
- Mediciones (Ryzen 5 5600G, 6 núcleos, solo CPU, 6 hilos): `base` 3,0 s por minuto de audio; `small-q5_1` 7,9 s con detección de voz (11,3 s sin ella); `large-v3-turbo-q5_0` 34 s, que no cumple CA1. La indicación de velocidad y calidad que se ve en Ajustes (`usage.speed`, `usage.quality`) es la de esa máquina.
- La elección se guarda como las demás (`selection.CHOOSABLE` gana `speech`) y funciona igual que en los otros tipos: sin elección se usa el recomendado, y una elección solo tiene efecto cuando ese modelo está descargado.
- El motor usa los **núcleos físicos** (con 12 hilos se gana menos de un 10 %).

### Detección de voz siempre activa, y filtro del texto
- Con 10 s de ruido sin voz, Whisper inventa texto con todos los modelos (`[Música]`, `[silbido]`, `Gracias.`, «Subtítulos…Amara.org»). El VAD de whisper.cpp (`--vad`) lo evita (el resultado es vacío) y además acelera, porque no procesa los silencios.
- El servicio añade dos defensas baratas: un audio sin ninguna ventana de 30 ms por encima de un RMS mínimo ni llega al motor (micrófono silenciado), y un resultado que es solo una etiqueta entre corchetes o una frase fantasma conocida se trata como `no_speech`.

### Vocabulario como pista
- Whisper recibe como `prompt` una frase corta con los términos del usuario y los nombres de agentes, proyectos, equipos y etapas (600 caracteres como máximo; en el idioma del dictado). En las mediciones los nombres propios pasaron de un 25 % de error a un 9 % con `small-q5_1`, y a 0 % con el turbo.

### El audio: WAV de 16 kHz en el navegador, en crudo, sin disco
- El navegador captura con `getUserMedia` y un `AudioWorklet` (`public/dictation-worklet.js`, servido desde `'self'`), remuestrea a 16 kHz y codifica **PCM de 16 bits mono en un WAV**. Así el motor no necesita `ffmpeg` (`--convert` no se usa) ni decodificar WebM/Opus.
- Se envía como cuerpo de `POST /api/dictation/transcribe` (`Content-Type: audio/wav`, máximo 30 MB), sin `multipart` en la API ni dependencias nuevas. El backend lo valida con `wave` en memoria y lo reenvía al motor desde la misma memoria. **Nunca se escribe en disco**; los registros solo guardan duración, modelo, número de caracteres y códigos de error, nunca el texto ni el audio.
- `whisper-server` responde `Access-Control-Allow-Origin: *` mientras está en marcha. Solo escucha en `127.0.0.1` y no hay nada que robar de él (solo transcribe lo que se le envíe), pero queda anotado como una limitación del motor.
- `POST /api/dictation/warmup` se pide al empezar a grabar: el modelo carga mientras la persona habla y el arranque en frío no se nota.

### Inserción en el campo
- El texto va donde estaba el cursor **al empezar a grabar**: un ancla que se corrige con cada `input` del campo (prefijo y sufijo comunes), así que escribir antes del ancla mientras se transcribe no desplaza el dictado. Si el campo ya no existe, el texto va al portapapeles y se avisa.
- Se inserta con `document.execCommand('insertText')` (entra en la pila de deshacer y dispara `input`), y donde no existe, con `setRangeText` más el evento `input`. Se añade un espacio por delante o por detrás solo si el texto se pegaría a una palabra.
- Las transcripciones se envían de una en una desde el cliente (el servidor además las serializa), y cada campo sabe si graba, espera o transcribe.

### Atajo de mantener pulsado
- `Ctrl+Espacio` por defecto, configurable (hace falta un modificador o una tecla de función, para que no escriba nada). Un único `keydown`/`keyup` en `capture` en el `AppShell`, que solo actúa si el foco está en un campo con micrófono, ignora la repetición de tecla, descarta pulsaciones de menos de 300 ms y para al soltar cualquier tecla de la combinación o al perder el foco la ventana. `Esc` cancela (también en `capture`, para que no cierre el diálogo).

### Micrófono en WebView2
- La CSP gana `media-src 'self' blob:` y `worker-src 'self'`.
- **Pendiente de verificar en la app instalada (CA5)**: si WebView2 pregunta una vez y recuerda la respuesta, no hace falta código en Rust. Si preguntara en cada arranque, se atenderá `PermissionRequested` desde `lib.rs` (con `webview2-com`) para el micrófono del origen propio. Si `getUserMedia` no funcionara dentro de Tauri, la alternativa es grabar desde el backend.

## Consecuencias
- El sidecar no crece: no se añadió ninguna dependencia al backend (el motor y los modelos se descargan, hasta 574 MB el más grande).
- El primer dictado sin motor ni modelo abre un diálogo que descarga el recomendado (199 MB entre motor y modelo) con progreso, y lo empieza a usar al terminar.
- Solo Windows x64, como `llama.cpp`: en otros sistemas el catálogo marca el motor como no disponible. La fase 22 (instaladores) y la 23 (modo servidor) deberán añadir los motores de las otras plataformas y decidir dónde se transcribe.
- Sin GPU. En un equipo más lento que el medido el modelo recomendado puede tardar más que el audio; el usuario puede bajar a `base`.
- La calidad medida usa una voz sintética limpia; las cifras absolutas serán peores con voz y micrófono reales, pero la comparación entre modelos y el efecto del vocabulario se mantienen. Queda una prueba manual con voz real.
