# Fase 16: Dictado por voz · Spec

- **Estado**: aprobada
- **Rama**: `phase/16-dictado-voz`

## Objetivo
Poder **dictar en lugar de escribir** en los campos donde se escribe mucho (descripción de una tarea, instrucciones de un agente, motivo de un rechazo…). La transcripción la hace **Whisper en local**: el audio no sale de la máquina y, una vez descargado el modelo, funciona sin conexión. El texto aparece donde está el cursor, listo para corregirlo.

## Punto de partida
- **Campos de texto largo** (todos usan `Textarea` o `MarkdownEditor`, salvo la respuesta de la Inbox):
  - descripción de la tarea al crearla (`NewTaskDialog`); en `TaskPage` la descripción solo se lee, y se escriben el **resumen al completar** y el **motivo de rechazo**;
  - instrucciones del agente (`InstructionsTab` con `MarkdownEditor`) y su descripción (`NewAgentDialog`, `GeneralTab`);
  - memoria del proyecto (`MemoryTab`);
  - prompt de una ejecución manual (`LaunchRunDialog`);
  - respuesta a una petición (`RequestActions`, usado en la Inbox y en Inicio): es un `Input` de una línea;
  - revisión de una propuesta de conocimiento (fase 15, `ProposalReview`): descripción y texto; y la descripción de un documento (`DocSheet`);
  - condición de una rama del pipeline (fase 13, `Panels`), que lee el decisor LLM.
  - El Arquitecto (fase 19) todavía no existe.
- **Modelos locales** (fases 14 y 15): `services/localmodels/catalog.py` es un catálogo fijado (revisión, tamaño y SHA-256) con tipos `embedding`, `ocr`, `vision` y `engine`. Las descargas son reanudables y se verifican, y Ajustes › Modelos locales las descarga, elige y borra. Ya hay un **motor descargable** (`llama.cpp`, con `llama-server`) que se usa como proceso aparte. La validación de la fase 15 dejó previsto un tipo `speech` para esta fase.
- **Procesos**: el trabajo pesado del conocimiento va en un trabajador de **baja prioridad**. Ese trabajador no sirve para el dictado, que el usuario está esperando.
- **Tauri + WebView2** (fase 08): la CSP de `desktop/src-tauri/tauri.conf.json` no tiene `media-src` y nunca se ha pedido el micrófono. Falta comprobar cómo se comporta el permiso de WebView2 dentro de Tauri.
- **Atajos** (fase 09, ADR 0013): `lib/shortcuts.ts` tiene un único `keydown` global, que ignora los campos de texto y la terminal. El dictado necesita además `keyup` (mantener pulsado) dentro de los campos.
- **Sidecar**: ahora mismo pesa 162,6 MB.

## Alcance
### Dentro

#### 1. Dictado en los campos
- **Botón de micrófono** en todos los campos listados en el punto de partida, salvo la condición de rama, que es corta. Quedan fuera los mensajes de commit, el cuerpo de los pull requests y el editor de conflictos.
- La **respuesta de la Inbox** pasa a ser un campo que crece con el texto (sigue enviándose con `Enter`), para que quepa una respuesta dictada.
- Un **componente reutilizable** para que cualquier campo nuevo (p. ej. la conversación con el Arquitecto en la fase 19) tenga dictado con una línea.
- **Dos formas de dictar**:
  - **Clic para empezar y otro para terminar** en el micrófono.
  - **Mantener pulsado** un atajo de teclado (configurable; el de por defecto se fija en el plan): graba mientras está pulsado, en el campo que tiene el foco, y no escribe ningún carácter en él. Solo funciona con la ventana de la app activa.
- **Mientras graba**: el botón cambia de estado, se ven el nivel de audio y el tiempo, y `Esc` cancela sin transcribir. Hay una duración máxima (5 minutos por defecto) con aviso 15 s antes; al llegar, se para y transcribe lo grabado.
- **Al terminar**: se ve «Transcribiendo…» y el texto **se inserta en el cursor** o sustituye la selección, con un espacio delante si hace falta. Se deshace con `Ctrl+Z` como cualquier otra edición. Mientras transcribe se puede seguir escribiendo en ese campo o en otros, y el texto entra donde estaba el cursor al empezar a grabar. Si el campo ya no existe (p. ej. se cerró el diálogo), el texto se copia al portapapeles y se avisa.
- **Errores claros**, sin perder nunca lo que ya había en el campo: sin modelo («Descarga un modelo de voz», con la descarga allí mismo), sin micrófono, permiso denegado (con cómo concederlo), audio sin voz y fallo de la transcripción.

#### 2. Transcripción local
- El frontend graba el micrófono y, al terminar, envía el audio al backend, que lo **transcribe con Whisper** y devuelve el texto. El formato y el camino del audio se deciden en el plan; la preferencia es convertirlo en el navegador a PCM de 16 kHz mono para que el backend no necesite `ffmpeg`.
- La transcripción va **fuera del proceso de la API** (no la bloquea) y con prioridad normal, no en el trabajador de baja prioridad del conocimiento. El modelo se queda cargado unos minutos después de usarlo, para que el siguiente dictado sea inmediato, y luego se libera la memoria.
- **Idioma**: español por defecto, configurable (detección automática o un idioma fijo).
- **Vocabulario**: para que Whisper acierte los nombres propios, recibe como pista los nombres de los agentes, proyectos, equipos y etapas, más una lista de términos que el usuario añade en Ajustes.
- **El audio no se guarda**: se procesa en memoria o en un temporal que se borra al terminar, también si falla, y nunca sale de la máquina.
- **Una transcripción a la vez**: las demás se encolan y el botón de cada campo muestra que está esperando.
- La transcripción no cuenta como consumo de los CLIs (fase 07), porque es local y gratuita.

#### 3. Modelos y ajustes
- **Catálogo**: un tipo nuevo `speech` con modelos de Whisper de varios tamaños (de rápido y ligero a preciso y pesado, p. ej. *base*, *small* y *large-v3-turbo*), fijados como el resto. Si el motor elegido es un programa aparte, como `whisper.cpp`, entra como `engine`, igual que `llama.cpp`. En **Ajustes › Modelos locales** se ven su tamaño y una indicación de velocidad y calidad (medidas en el spike), y se elige el que se usa para dictar.
- **Ajustes › Dictado** (sección nueva): activar o desactivar el dictado (desactivado, no se ven los micrófonos), modelo, idioma, atajo, micrófono (si hay varios), duración máxima y vocabulario.
- La primera vez que se pulsa un micrófono sin modelo, se ofrece descargar el recomendado allí mismo, con su progreso.

#### 4. Transversal
- **Permiso del micrófono en Tauri/WebView2**: la app pide el micrófono con el aviso del sistema y recuerda la respuesta entre arranques. Se ajusta la CSP para el audio.
- **API**: transcripción (se sube el audio y se recibe el texto, o un error con su motivo), estado del motor (sin modelo, cargando, listo, ocupado) y ajustes del dictado. Los modelos van por la API de modelos locales que ya existe.
- Textos en i18n y diseño v7 (`docs/design/v2/`). El botón se usa con teclado y lector de pantalla: anuncia «Grabando», «Transcribiendo» y el error, si lo hay.
- **Tests**: el componente con un micrófono y una transcripción falsos (inserción en el cursor, selección, `Ctrl+Z`, cancelar, duración máxima, campo cerrado, errores) y el atajo de mantener pulsado. En el backend: la API con un motor falso, la cola, el borrado del audio y una transcripción real de un audio corto en español incluido en el repo. Además, los ajustes y un e2e con el sidecar empaquetado.
- **ADR**: motor de Whisper y cómo se ejecuta, formato del audio y su viaje al backend, permiso del micrófono en WebView2, atajo de mantener pulsado y modelos de voz en el catálogo.

### Fuera
- Transcripción **en vivo** mientras se habla (texto parcial que va apareciendo): solo al terminar.
- Comandos de voz («nueva tarea», «aprobar»…) y dictar fuera de los campos.
- Atajo global del sistema con la app en segundo plano.
- Dictar dentro de la terminal de una ejecución (xterm.js).
- Leer en voz alta (texto a voz).
- Uso de GPU: solo CPU. Se puede añadir más adelante si el spike muestra que merece la pena.
- Transcribir en el servidor o en el cliente cuando la app se despliegue en un servidor (fase 24).
- Que un LLM reescriba, puntúe o resuma el texto dictado.
- Instalar un modelo de voz con la app: se descarga desde Ajustes.

## Historias de usuario
- Como usuario, quiero dictar la descripción de una tarea de un par de párrafos en lugar de escribirla, para ir más rápido.
- Como usuario, quiero explicar de viva voz por qué rechazo una tarea o una propuesta, para dar más detalle sin esfuerzo.
- Como usuario, quiero responder a un agente que me pregunta algo en la Inbox hablando, sin teclear.
- Como usuario, quiero mantener pulsada una tecla, hablar y soltar, sin tocar el ratón.
- Como usuario, quiero que mi voz no salga de mi ordenador y que funcione sin internet.
- Como usuario, quiero que acierte los nombres de mis agentes y proyectos.
- Como usuario, quiero elegir un modelo más rápido o más preciso según mi ordenador.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Se dicta en español una descripción de tarea de un par de párrafos sin conexión a internet y llega al campo en pocos segundos** (objetivo: menos de 10 s para un minuto de audio con el modelo recomendado en un portátil normal, sin contar la primera carga del modelo) | Prueba manual con la app instalada y la red desconectada, con el tiempo medido |
| CA2 | El texto se inserta en el cursor o sustituye la selección sin perder lo que había, también si se sigue escribiendo mientras transcribe, y se deshace con `Ctrl+Z` | Tests de componentes |
| CA3 | Funcionan el clic y el atajo de mantener pulsado (sin escribir caracteres en el campo); `Esc` cancela; la duración máxima avisa, corta y transcribe lo grabado | Tests de componentes + prueba manual |
| CA4 | El micrófono está en todos los campos listados, con un único componente reutilizado | Tests de componentes + revisión |
| CA5 | La app instalada pide el permiso del micrófono una vez y lo recuerda entre arranques; si se deniega, el error explica cómo concederlo | Prueba manual con el instalador |
| CA6 | Sin modelo, el micrófono ofrece descargarlo; los modelos de voz se descargan (verificados), eligen y borran en Ajustes › Modelos locales | Tests + prueba manual |
| CA7 | El audio no queda en disco tras la transcripción (ni si falla) y no se hace ninguna petición de red al dictar | Test del backend + revisión del tráfico en la prueba manual |
| CA8 | Con la pista, los nombres de agentes y proyectos y el vocabulario de Ajustes se aciertan más que sin ella | Prueba con un audio de ejemplo, con y sin vocabulario |
| CA9 | Dictar no bloquea la API ni la interfaz, y los dictados simultáneos se encolan | Test del backend |
| CA10 | Con el sidecar empaquetado, la transcripción de un audio de ejemplo funciona | e2e con el binario |
| CA11 | Lint, tests de backend y de frontend en verde; ADR escrito; `/code-review` resuelto | CI local |

## Prerrequisitos
- Fases 14 y 15 cerradas (catálogo y Ajustes › Modelos locales).
- Un micrófono en la máquina de pruebas.

## Riesgos y preguntas abiertas
- **Permiso del micrófono en WebView2** (riesgo principal, **spike al principio del plan**): `getUserMedia` dentro de Tauri en Windows puede fallar o preguntar en cada arranque, y puede hacer falta atender desde Rust el evento `PermissionRequested` de WebView2. Si no se resuelve, la alternativa es grabar desde el backend (p. ej. con `sounddevice`), aunque entonces el micrófono se elige fuera del navegador.
- **Motor de Whisper** (spike): hay tres candidatos.
  - `whisper.cpp` como motor descargable (`whisper-server`, como `llama.cpp`): no hace crecer el sidecar y sigue un patrón que ya existe.
  - `faster-whisper` (CTranslate2, int8 en CPU): rápido, pero añade dependencias al sidecar.
  - Whisper en ONNX con el `onnxruntime` que ya va en el sidecar.
  
  Se decide en el plan con la velocidad en CPU, el tamaño añadido, el arranque en frío y si necesita `ffmpeg`.
- **Velocidad en máquinas modestas**: en CPU, los modelos grandes pueden tardar más que el propio audio. El modelo recomendado sale del spike y se indica en Ajustes.
- **Atajo de mantener pulsado**: tiene que funcionar dentro de un campo sin escribir caracteres y sin chocar con los atajos de la fase 09 ni con los del sistema y WebView2 (la repetición de tecla dispara muchos `keydown`). El valor por defecto se decide en el plan.
- **Memoria**: un modelo grande cargado puede ocupar más de 1 GB, y además puede estar cargado el de *embeddings*. Se libera tras unos minutos sin usarlo, y el plan fija ese tiempo.
