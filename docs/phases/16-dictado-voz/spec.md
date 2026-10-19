# Fase 16: Dictado por voz · Spec

- **Estado**: borrador
- **Rama**: `phase/16-dictado-voz`

## Objetivo
Poder **dictar en lugar de escribir** en los campos donde se escribe mucho (descripción de una tarea, instrucciones de un agente, motivo de un rechazo…). La transcripción la hace **Whisper en local**, en el backend: el audio no sale de la máquina y funciona sin conexión una vez descargado el modelo. El texto aparece donde está el cursor, listo para corregirlo.

## Punto de partida
- **Campos de texto largos**: `NewTaskDialog` y `TaskPage` (descripción y motivo de rechazo), las instrucciones del agente (`MarkdownEditor`), la memoria del proyecto (`MemoryTab`), las respuestas de la Inbox y el diálogo de lanzar una ejecución (`LaunchRunDialog`). El Arquitecto (fase 19) todavía no existe.
- **Modelos locales** (fase 14): Ajustes › Modelos locales descarga, lista y borra modelos en la carpeta de datos. Esta fase añade los de Whisper.
- **Tauri + WebView2** (fase 08): la CSP de `tauri.conf.json` no contempla audio. Nunca se ha pedido el micrófono, y el permiso de WebView2 en una app Tauri hay que comprobarlo.
- **Atajos de teclado** (fase 09, ADR 0013): hay un sistema de atajos globales al que se añade el del dictado.

## Alcance
### Dentro

#### 1. Dictado en los campos
- **Botón de micrófono** en los campos de texto largo: descripción de la tarea (al crearla y al editarla), motivo de rechazo, instrucciones del agente, memoria del proyecto, respuesta a una petición de la Inbox y prompt de una ejecución manual.
- Un **componente reutilizable** con el que cualquier campo nuevo (p. ej. la conversación con el Arquitecto en la fase 19) pueda tener dictado añadiendo una línea.
- **Dos formas de dictar**:
  - **Pulsar para empezar y para terminar**: clic en el micrófono;
  - **Mantener pulsado**: un atajo de teclado (configurable; por defecto se fija en el plan) graba mientras está pulsado, en el campo que tiene el foco.
- **Mientras graba**: el botón cambia de estado, se ve el nivel de audio y el tiempo, y `Esc` cancela sin transcribir. Hay una duración máxima (p. ej. 5 minutos) con aviso antes de llegar.
- **Al terminar**: se muestra «Transcribiendo…» y el texto **se inserta en el cursor** o sustituye la selección, con un espacio delante si hace falta. Se deshace con `Ctrl+Z` como cualquier edición. Se puede seguir escribiendo en otros campos mientras transcribe.
- **Errores claros**: sin modelo («Descarga un modelo de voz en Ajustes», con enlace), sin micrófono, permiso denegado (con cómo concederlo), audio vacío o sin voz, y fallo de transcripción. El campo no pierde lo que ya tenía.

#### 2. Transcripción local en el backend
- El frontend graba con el micrófono del sistema y envía el audio al backend al terminar; el backend lo **transcribe con Whisper** y devuelve el texto.
- **Idioma**: español por defecto, configurable (detección automática o un idioma fijo).
- **Vocabulario del proyecto**: para que Whisper acierte los nombres propios, se le pasan como pista los nombres de los agentes, proyectos y etapas, y una lista de términos que el usuario añade en Ajustes.
- **El audio no se guarda**: se procesa en memoria o en un temporal que se borra al terminar, y nunca sale de la máquina.
- Una transcripción a la vez: si llegan varias, se encolan.
- La transcripción no cuenta como consumo de los CLIs (fase 07), porque es local y gratuita.

#### 3. Modelos y ajustes
- **Ajustes › Modelos locales** incluye los modelos de Whisper en varios tamaños (de rápido y ligero a preciso y pesado, p. ej. *base*, *small* y *large-v3-turbo*), con su tamaño en disco y una indicación de velocidad y calidad. Se elige el que se usa para dictar.
- **Ajustes › Dictado**: activar o desactivar el dictado (si está desactivado, no se ven los micrófonos), modelo, idioma, atajo, micrófono (si hay varios), duración máxima y vocabulario.
- La primera vez que se pulsa un micrófono sin modelo descargado, se ofrece descargar el recomendado allí mismo, con su progreso.

#### 4. Transversal
- **Permiso del micrófono en Tauri/WebView2**: la app pide el micrófono con el aviso del sistema y recuerda el permiso. Se ajusta la CSP para el audio.
- **API** de transcripción (subir el audio y recibir el texto) y de ajustes de dictado. Los modelos van por la API de modelos locales de la fase 14.
- Textos en i18n; diseño v7 (`docs/design/v2/`); botón accesible con teclado y lector de pantalla (anuncia «Grabando» y «Transcribiendo»).
- **Tests**: componente de dictado con un micrófono y una transcripción falsos (inserción en el cursor, selección, cancelar, errores), API con un motor de Whisper falso, una transcripción real de un audio corto de ejemplo en español y ajustes.
- **ADR**: motor de Whisper, formato del audio y su viaje al backend, permiso del micrófono en WebView2 y gestión de los modelos de voz.

### Fuera
- Transcripción **en vivo** mientras se habla (texto parcial que va apareciendo); solo al terminar.
- Comandos de voz («nueva tarea», «aprobar»…) o dictar en cualquier parte de la app, fuera de los campos.
- Dictar dentro de la terminal de una ejecución (xterm.js).
- Leer en voz alta (texto a voz).
- Uso de GPU (solo CPU; se puede añadir más adelante si el spike muestra que merece la pena).
- Transcribir en el servidor o en el cliente cuando la app se despliegue en un servidor (fase 22).
- Que un LLM reescriba o resuma el texto dictado.

## Historias de usuario
- Como usuario, quiero dictar la descripción de una tarea de un par de párrafos en lugar de escribirla, para ir más rápido.
- Como usuario, quiero explicar de viva voz por qué rechazo una tarea, para dar más detalle sin esfuerzo.
- Como usuario, quiero mantener pulsada una tecla, hablar y soltar, sin tocar el ratón.
- Como usuario, quiero que mi voz no salga de mi ordenador y que funcione sin internet.
- Como usuario, quiero que acierte los nombres de mis agentes y proyectos.
- Como usuario, quiero elegir un modelo más rápido o más preciso según mi ordenador.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Se dicta en español una descripción de tarea de un par de párrafos sin conexión a internet y llega al campo en pocos segundos** (objetivo: menos de 10 s para un minuto de audio con el modelo recomendado en un portátil normal) | Prueba manual con la app instalada y la red desconectada, con el tiempo medido |
| CA2 | El texto se inserta en el cursor o sustituye la selección sin perder lo que había, y se deshace con `Ctrl+Z` | Tests de componentes |
| CA3 | Funcionan el clic y el atajo de mantener pulsado; `Esc` cancela; la duración máxima corta y transcribe lo grabado | Tests de componentes + prueba manual |
| CA4 | El micrófono está en todos los campos listados y el componente se reutiliza | Tests de componentes + revisión |
| CA5 | La app instalada pide el permiso del micrófono una vez y lo recuerda; si se deniega, el error explica cómo concederlo | Prueba manual con el instalador |
| CA6 | Sin modelo, el micrófono ofrece descargarlo; los modelos de voz se descargan, eligen y borran en Ajustes › Modelos locales | Tests + prueba manual |
| CA7 | El audio no queda en disco tras la transcripción y no se hace ninguna petición de red al dictar | Test del backend + revisión del tráfico en la prueba manual |
| CA8 | Los nombres de agentes y proyectos y el vocabulario de Ajustes se transcriben bien con más frecuencia que sin la pista | Prueba manual con un audio de ejemplo, con y sin vocabulario |
| CA9 | Lint, tests de backend y de frontend en verde; ADR escrito; `/code-review` resuelto | CI local |

## Prerrequisitos
- Fase 14 cerrada, con Ajustes › Modelos locales.
- Un micrófono en la máquina de pruebas.

## Riesgos y preguntas abiertas
- **Permiso del micrófono en WebView2** (riesgo principal, **spike al principio del plan**): `getUserMedia` dentro de Tauri en Windows puede fallar o preguntar en cada arranque. Puede hacer falta atender el evento de permisos de WebView2 desde Rust. Si no se resuelve, la alternativa es grabar desde el backend (p. ej. con `sounddevice`), con el coste de elegir el micrófono fuera del navegador.
- **Motor de Whisper**: `faster-whisper` (CTranslate2, buena velocidad en CPU con int8) frente a `whisper.cpp` con *bindings* de Python. Se decide en el plan según la velocidad en CPU, el tamaño en PyInstaller y si decodifica el audio del navegador (WebM/Opus) sin `ffmpeg` externo.
- **Velocidad en máquinas modestas**: los modelos grandes pueden tardar más que el audio en CPU. El modelo recomendado se elige en el spike y se indica en Ajustes. Si hay mucha diferencia entre equipos, se puede proponer el modelo según una prueba rápida de la máquina.
- **Atajo de mantener pulsado**: tiene que funcionar dentro de un campo de texto sin escribir caracteres y sin chocar con los atajos de la fase 09 ni con los del sistema. El valor por defecto se decide en el plan.
- **Spec antes de cerrar la fase 14**: esta spec se escribe a la vez que la de la fase 14, pero el desarrollo empieza cuando esa esté cerrada, porque depende de su gestión de modelos locales.
