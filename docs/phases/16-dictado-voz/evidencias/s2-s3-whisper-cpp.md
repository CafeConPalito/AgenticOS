# S2 y S3 · whisper.cpp en CPU: velocidad, calidad, vocabulario y silencio

- **Fecha**: 2026-10-23
- **Máquina**: AMD Ryzen 5 5600G (6 núcleos, 12 hilos), 16 GB, solo CPU.
- **Motor**: `whisper-server.exe` de la release `b5454` de `ggml-org/whisper.cpp` (`whisper-bin-x64.zip`, 8,9 MB; 22 MB desplegado).
- **Scripts**: `spikes/dictation/make_samples.ps1`, `s2_whisper_cpp.py`, `s12_emit_pins.py`. Resultados en bruto en `spikes/dictation/out/` (no se versiona).
- **Audios**: voz «Microsoft Helena» (es-ES) a 16 kHz mono. `dictado.wav` dura 64 s; `nombres.wav` son 17 s con nombres inventados (Kestrel, Mirlo, Zafiro, Triaje, Cobalto, Lince) más Celery y Redis; `ruido.wav` son 10 s de ruido bajo sin voz.
- **Aviso**: una voz sintética es limpia, así que los WER son optimistas. Sirven para comparar modelos entre sí, no como cifra de calidad real. La prueba con voz y micrófono reales queda para el bloque 7.

## Velocidad, memoria y calidad (6 hilos)
Tiempos en el servidor ya caliente. «Por minuto» es el tiempo de transcripción por cada minuto de audio.

| Modelo | Disco | Memoria | Por minuto | WER dictado | WER nombres sin pista | WER nombres con pista |
|---|---|---|---|---|---|---|
| `base` | 148 MB | 365 MB | **3,0 s** | 1,6 % | 40,6 % | 18,8 % |
| `small-q5_1` | 190 MB | 510 MB | 11,3 s (7,9 s con VAD) | 1,1 % | 25,0 % | **9,4 %** |
| `small` | 488 MB | 798 MB | 11,5 s | 1,1 % | 31,2 % | 9,4 % |
| `large-v3-turbo-q5_0` | 574 MB | 837 MB | 34,2 s | 0,0 % | 6,2 % | 0,0 % |

- Carga en frío del proceso: 0,5 s con cualquiera (el modelo se mapea en memoria; la primera petición hace el trabajo de verdad).
- **Hilos**: con 12 hilos se gana menos de un 10 % frente a 6 (los núcleos físicos). Se usan los núcleos físicos.
- **Decodificación**: voraz (`-bs 1 -bo 1`) y sin retroceso de temperatura (`-nf`) no cambian ni la velocidad ni el texto.
- `small` sin cuantizar no mejora a `small-q5_1` y pesa el doble: se descarta.
- `large-v3-turbo` es la mejor, pero a 34 s por minuto **no cumple CA1** (< 10 s) en esta máquina. Se ofrece como «preciso», avisando de que es lento.

## La pista de vocabulario funciona
Con la pista («Agentes: Kestrel, Mirlo. Proyecto: Zafiro…») los nombres propios pasan de un 25 % de error a un 9 % en `small-q5_1`, y a 0 % en `large-v3-turbo`. Sin ella: «Asigna la tarea a la gente que estrele el del proyecto Zafiro… Selari con Ridis». Con ella: «…al agente Kestrel… Celery con Redis».

## S3 · el silencio hace que Whisper se invente texto
Con 10 s de ruido sin voz, y sin ningún filtro:

| Modelo | Texto devuelto |
|---|---|
| `base` | `[Música]` |
| `small-q5_1`, `small` | `[silbido]` |
| `large-v3-turbo-q5_0` | `Gracias.` |
| `small-q5_1` con `--suppress-nst` | `Subtítulos por la comunidad de Amara.org` |

El VAD (`--vad`, modelo Silero v5.1.2 de 885 KB) lo resuelve: con él, el silencio devuelve **texto vacío** con todos los modelos. Además **es más rápido** (`small-q5_1`: 11,3 → 7,9 s por minuto, porque no procesa los huecos entre frases) sin cambiar el WER.

## Decisiones
1. **Motor: `whisper.cpp` como motor descargable** (`whisper-server`), igual que `llama.cpp`. No hace crecer el sidecar ni exige `ffmpeg` si se le envía un WAV de 16 kHz (sin `--convert`, que además es lo que usaría ficheros temporales).
2. **Modelo recomendado: `small-q5_1`** (190 MB). Con VAD queda en ~8 s por minuto, dentro de CA1. Se ofrecen también `base` (rápido, 148 MB) y `large-v3-turbo-q5_0` (preciso, lento, 574 MB). No se incluye `small` sin cuantizar.
3. **VAD siempre activo**, con el modelo Silero (885 KB) como parte de la descarga del motor. Un resultado vacío se trata como `no_speech`.
4. **Filtro de texto, además del VAD**: si todo el texto devuelto es una etiqueta entre corchetes (`[Música]`, `[silbido]`…) o una frase fantasma conocida (`Subtítulos…Amara.org`, `Gracias.` solo, `Gracias por ver el vídeo`), se trata como `no_speech`. Cuesta poco y cubre los casos que el VAD deje pasar.
5. **Hilos**: los núcleos físicos (`psutil.cpu_count(logical=False)`).
6. **Pista**: «Agentes: …. Proyectos: …. Etapas: ….» más los términos del usuario, en una frase corta.

## Lo que no se ha medido
- Equipos más lentos que éste: la velocidad se indica en Ajustes como medida en esta máquina.
- Ningún candidato distinto de `whisper.cpp` (`faster-whisper`, ONNX): el primero ya cumple CA1 y encaja con el patrón de `llama.cpp`, así que no se han probado.
- Voz real con micrófono real (bloque 7).
