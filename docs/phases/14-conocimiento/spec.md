# Fase 14: Conocimiento · Spec

- **Estado**: aprobada (2026-10-18)
- **Rama**: `phase/14-conocimiento`

## Objetivo
Que los agentes trabajen con **la documentación que les damos**: manuales, especificaciones, hojas de cálculo, páginas web o capturas. El conocimiento se organiza en **tres niveles (general, proyecto y agente)**. Los documentos pequeños entran enteros en el contexto de la ejecución y los grandes se consultan con **búsqueda local (RAG)** mediante la herramienta MCP `search_knowledge`. Nada sale de la máquina: la conversión, los *embeddings* y la búsqueda son locales. La app **no copia los ficheros**: guarda la referencia a su ubicación y solo lo imprescindible para la IA (el texto en Markdown y el índice de búsqueda).

## Punto de partida
- **Contexto de una ejecución** (`services/context.py`, ADR 0004): `build_instructions` junta el rol y las instrucciones del agente, el proyecto, los repos, las reglas de git, la **memoria del proyecto**, la tarea y las reglas de Agentic OS. `get_context` (MCP) devuelve lo mismo.
- **Memoria del proyecto** (fase 05): notas cortas en la BD que se inyectan siempre enteras. Es lo más parecido a esta fase, pero no admite ficheros ni búsqueda.
- **MCP `agentic-os`** (`services/mcp_server.py`): `get_context`, `report_status`, `complete_task`, `request_human`, `spawn_subagent`, `create_subtask` y `write_project_memory`, con token por ejecución.
- **UI**: la pestaña «Conocimiento» ya existe, vacía («Próximamente»), en el detalle del proyecto y en el editor del agente.
- **Empaquetado** (fase 08): el backend es un *sidecar* de PyInstaller. Lo que se añada (librerías de conversión, motor de *embeddings*) aumenta su tamaño y hay que validarlo en el instalador.
- **No hay modelos locales**: hoy todo lo que es LLM lo hacen los CLIs. Esta fase introduce el primero (*embeddings*), y la fase 16 (Whisper) reutilizará su gestión.

## Alcance
### Dentro

#### 1. Biblioteca en tres niveles
- **General**: lo ven todos los agentes en todos los proyectos (p. ej. guía de estilo de la empresa). Se gestiona en una página nueva **Conocimiento** del menú.
- **Proyecto**: lo ven los agentes que trabajan en ese proyecto (pestaña «Conocimiento» del proyecto).
- **Agente**: acompaña al agente en cualquier proyecto (pestaña «Conocimiento» del agente; p. ej. el manual de marca para el Redactor).
- Una ejecución ve **general + proyecto + agente**. Los subagentes ven lo mismo que su agente padre y además lo de su propio agente, si lo tienen.
- Cada documento tiene título (por defecto, el nombre del fichero o de la página), descripción opcional, nivel, origen, tamaño, fecha, estado de proceso y **modo de uso**:
  - **Automático** (por defecto): si es pequeño va al contexto y, si no, a búsqueda.
  - **Siempre en contexto**: se inyecta entero (se avisa si es grande).
  - **Solo búsqueda**: nunca va entero al contexto.
  - **Desactivado**: se conserva, pero los agentes no lo ven.
- Se pueden **mover** documentos entre niveles y **sustituir** el fichero conservando el título y el modo.

#### 2. Ficheros por referencia
- Al subir un fichero, la app **guarda su ruta local**, no una copia. De cada fichero conserva la ruta, el nombre, el tamaño, la fecha de modificación y una huella (*hash*) para saber si ha cambiado.
- **Qué conserva la app**: solo lo imprescindible para la IA, es decir, el **texto convertido a Markdown** (una sola vez; los trozos del índice apuntan a él) y el **índice de búsqueda**. Ni el original ni copias intermedias.
- **Abrir el original** desde la ficha del documento:
  - en un **visor dentro de la app** si el formato lo permite: PDF, imágenes, Markdown, texto y código (con resaltado) y CSV (como tabla);
  - si no (Word, Excel, PowerPoint…), **con la aplicación del sistema**;
  - además, **«Mostrar en la carpeta»** abre el explorador de archivos con el fichero seleccionado.
- **Fichero borrado o movido**: si al abrirlo, reprocesarlo o al revisar los documentos el fichero ya no está en su ruta, el documento se marca como **«No encontrado»** y se le indica al usuario que el fichero se borró o se movió. Puede:
  - **indicar la nueva ruta**: si la huella coincide, se conserva el índice; si no, se avisa de que es otro contenido y se reprocesa;
  - **quitarlo de la app**: se borran su Markdown y su índice;
  - **dejarlo como está**: los agentes siguen usando el Markdown ya convertido, porque no necesitan el original. Las imágenes son la excepción: sin el original el agente no puede verlas, así que se le ocultan.
- **Fichero cambiado**: si la fecha o la huella del original no coinciden con las procesadas, el documento muestra **«Ha cambiado»** con el botón de reprocesar. No se reprocesa solo.
- La comprobación se hace al abrir las páginas de conocimiento y antes de cada acción sobre el documento, no vigilando el disco.

#### 3. Fuentes y conversión
- **Una sola pipeline para todos los formatos**: fichero o URL → **MarkItDown** (convierte todo a Markdown) → pasos comunes (imágenes y OCR, troceado, *embeddings*). No hay una pipeline por tipo de fichero. Lo que MarkItDown no cubra bien (p. ej. marcas de página en PDF, imágenes incrustadas, páginas escaneadas) se añade como **plugin de MarkItDown**, que es su mecanismo de extensión, dentro del mismo flujo.
- **Texto y código**: `.md`, `.txt`, `.csv`, `.json`, `.yaml` y ficheros de código comunes. Se usan tal cual.
- **Ofimática**: PDF (con texto o escaneado), Word (`.docx`), Excel (`.xlsx`) y PowerPoint (`.pptx`). Se convierten a Markdown conservando títulos, listas y tablas, y cada hoja de Excel se convierte en una tabla. Las páginas de un PDF que no tienen texto (escaneadas) pasan por OCR.
- **URLs**: se descarga la página y se extrae el contenido principal a Markdown, sin guardar el HTML. «Abrir» lleva a la URL en el navegador del sistema, y **«Volver a descargar»** la reprocesa. No se rastrean otras páginas del sitio.
- **Imágenes** (`.png`, `.jpg`, `.webp`, `.gif`): se tratan como se describe en el apartado 4.
- Subida **arrastrando** varios ficheros a la vez o con el selector, y una URL por cada campo.
- **Barra de progreso** por documento, en vivo, con la fase (en cola → convirtiendo → indexando → listo) y el avance dentro de cada una (p. ej. página 34 de 120, trozos indexados).
- **Botón «Ver Markdown»**: muestra el texto convertido (renderizado o en crudo) para comprobar que la conversión ha salido bien, junto al botón de abrir el original para compararlos.
- **Botón «Reprocesar»**: vuelve a convertir e indexar desde el original (o desde la URL). Sirve tras un fallo, cuando el fichero ha cambiado o tras cambiar el modelo.
- **Fallos**: si la conversión o la indexación fallan, el documento queda marcado como **«Fallo»** y se muestra al usuario **por qué**, en lenguaje claro (p. ej. «El fichero está protegido con contraseña», «Formato no admitido», «No se pudo descargar la URL: 404», «No encontrado en la ruta»). El detalle técnico queda en el log. Un documento con fallo no se usa en las ejecuciones hasta que se reprocesa con éxito.
- Límite de tamaño por fichero, configurable, con un valor por defecto razonable que se fija en el plan.
- **Uso de recursos en vivo**: mientras se procesan documentos, la página de conocimiento muestra el **uso de CPU, GPU y memoria** del equipo y la parte que corresponde al procesado (backend y, si está activo, `llama.cpp`), para ver que nada se satura. La GPU se muestra si el sistema permite leerla (en Windows, con los contadores de rendimiento, de cualquier fabricante); si no, se indica «No disponible».
- **Para no saturar el equipo**: los documentos se procesan **de uno en uno** por defecto (configurable), con un número máximo de hilos de CPU para el OCR y los *embeddings* (por defecto, la mitad de los núcleos) y con **prioridad baja** del proceso de trabajo. Se puede **pausar y reanudar** el procesado.

#### 4. Imágenes
**Por defecto** (sin nada que configurar, todo en local):
- **Imágenes sueltas**: el agente recibe su **ruta original** y las abre con su propio CLI cuando las necesita. En la búsqueda cuentan su título, la descripción opcional del usuario y el **texto que saca el OCR**.
- **Imágenes dentro de PDF, Word y PowerPoint**: se **extraen** y se guardan aparte, porque el agente no puede sacarlas del original. Es lo único que se conserva además del Markdown. Se descartan las muy pequeñas (iconos, viñetas, logos repetidos) y las repetidas se guardan una sola vez.
- **En el Markdown**, cada imagen queda en su sitio con una marca (p. ej. `![Figura, p. 12](…)`) y, debajo, su texto por OCR, que entra en la búsqueda.
- **OCR local**: un motor ligero (ONNX, en CPU) que lee español e inglés. Se usa en las imágenes y en las páginas escaneadas.
- `search_knowledge` y `read_knowledge` devuelven la **ruta de las imágenes** del trozo, y las instrucciones de Agentic OS le dicen al agente que las abra si son relevantes para la tarea.

**Opcional: «Describir imágenes con IA»** (desactivado por defecto; se activa en Ajustes y se puede activar o desactivar por documento):
- La descripción se escribe en el Markdown junto a la imagen, marcada como generada, y entra en la búsqueda.
- El usuario elige con qué se describen:
  - **Un CLI en modo *headless*** (el mismo mecanismo que el decisor de la fase 13), con su cuenta y su modelo. Se avisa de que **las imágenes salen de la máquina** y de que **gasta cuota**. Su consumo se registra (fase 07) y respeta el límite diario.
  - **Un modelo de visión local con `llama.cpp`**. **`llama.cpp` no viene en el instalador**: la app lo descarga e instala la primera vez que se elige esta opción (binario oficial para la plataforma), junto con el modelo de visión que se elija en Ajustes › Modelos locales. Los modelos que se ofrecen son **Qwen 3.5** y **Gemma 4**, en su variante pequeña con visión y en GGUF cuantizado; el plan fija el tamaño concreto de cada uno según lo que soporte `llama.cpp` y lo que aguante una CPU. Lo arranca como proceso local cuando hay imágenes que describir y lo para al terminar. Se avisa de que es lento en CPU.
- Activarlo en un documento ya procesado ofrece reprocesarlo. La barra de progreso muestra también «describiendo imágenes (n de m)».

#### 5. Contexto y RAG local
- **Contexto de la ejecución**: se añade una sección «Conocimiento» con:
  - el **índice de todos los documentos visibles** (título, nivel, descripción y modo), para que el agente sepa qué hay aunque no lo tenga cargado;
  - el **texto entero** de los documentos que van al contexto (los de «Siempre en contexto» y los «Automático» pequeños), hasta un **presupuesto de tokens** configurable. Si se pasa del presupuesto, los automáticos que no caben quedan para búsqueda y se avisa en la UI;
  - las **rutas** de las imágenes.
- **Índice de búsqueda híbrido** (ver «Recuperación de información» en los riesgos): el Markdown se trocea respetando títulos y párrafos. Cada trozo guarda su documento y su ubicación (página, hoja o apartado) y se busca de dos formas, cuyos resultados se combinan:
  - **por palabras** (índice de texto completo de SQLite): acierta con términos exactos, como códigos de error, nombres propios o identificadores;
  - **por significado** (*embeddings* de un **modelo local** multilingüe, bueno en español, en CPU): acierta cuando la pregunta usa otras palabras que el documento («dar de baja» frente a «cancelar la suscripción»).
- **Cómo se generan los *embeddings***:
  - con **ONNX Runtime en CPU** dentro del backend (el mismo motor que el OCR), sin PyTorch ni `llama.cpp`, para que funcione siempre y sin instalar nada más que el modelo;
  - un **modelo multilingüe** que se descarga de Hugging Face en Ajustes › Modelos locales. Se ofrecen tres y el usuario elige:
    - `multilingual-e5-small` cuantizado (unos 120 MB, 384 dimensiones): el más ligero;
    - **EmbeddingGemma** de Google (unos 300 M de parámetros, 768 dimensiones que se pueden recortar; se usa la versión más reciente disponible, EmbeddingGemma 2 si ya está publicada en ONNX);
    - `bge-m3` (unos 600 MB cuantizado): el de más calidad y el más pesado.
    El spike del plan los compara en español (calidad, velocidad y memoria) y decide el modelo por defecto;
  - **trozos** de unos 300–500 tokens que respetan títulos y párrafos, con un pequeño solapamiento. Cada trozo lleva delante el título del documento y del apartado para que el vector tenga contexto;
  - los trozos y las consultas se codifican **por lotes en segundo plano**, con el prefijo que pida el modelo (`passage:` y `query:` en e5), y los vectores se normalizan;
  - los vectores se guardan en **SQLite** junto al trozo (como `float32`, o `int8` si el spike muestra que no pierde calidad) y se comparan por **similitud del coseno** con NumPy. Para miles de trozos tarda milisegundos y no hace falta una base vectorial aparte;
  - los dos rankings (palabras y significado) se combinan con **fusión de rangos recíprocos** (RRF), que no necesita ajustar pesos;
  - se guarda qué modelo generó cada vector: al cambiar de modelo se regeneran todos en segundo plano y, mientras tanto, la búsqueda usa solo las palabras.
- **MCP**:
  - `search_knowledge(query, limit?)`: devuelve los trozos más relevantes de los documentos visibles, con el documento, la ubicación y la puntuación;
  - `read_knowledge(document, location?)`: devuelve el texto convertido de un documento entero o de una parte (página, hoja o apartado), troceado si es muy largo.
- Las instrucciones de Agentic OS explican cuándo usar `search_knowledge` y `read_knowledge`.
- **Probar la búsqueda** desde la UI: en cada página de conocimiento, un buscador muestra lo que recibiría un agente para esa consulta.
- **Trazabilidad**: cada llamada a `search_knowledge` y `read_knowledge` queda en los eventos de la ejecución, con la consulta y los documentos devueltos.

#### 6. Modelos locales (base reutilizable)
- Sección nueva **Ajustes › Modelos locales**: lista de modelos con su función (*embeddings*, OCR y, si se activa, descripción de imágenes), tamaño, estado (no descargado, descargando con progreso, listo o error) y espacio en disco; descargar, cancelar y borrar.
- Además de los modelos, gestiona **motores** descargables: de momento `llama.cpp`, con su versión, estado y botón de borrar.
- Los modelos y los motores que se descargan se guardan en la carpeta de datos (fase 08) y no se incluyen en el instalador. Lo que sí va en el instalador son ONNX Runtime, las librerías de conversión y OCR y **los modelos de OCR (~18 MB)**, para que el OCR funcione desde el primer momento, sin configurar nada y sin conexión (decidido el 2026-10-19: esos modelos solo se publican en un servidor, `modelscope.cn`, sin espejo). Tras la descarga, todo lo demás funciona **sin conexión**.
- Si el modelo de OCR no está (una compilación sin él), las imágenes y las páginas escaneadas se procesan sin su texto y se avisa con un enlace a Ajustes, donde se puede descargar.
- Si falta el modelo de *embeddings*, los documentos se convierten igual y la búsqueda funciona **solo por palabras**. Se avisa con un enlace a Ajustes.
- Cambiar de modelo vuelve a indexar todos los documentos, en segundo plano y con su progreso.
- La gestión se diseña para que la fase 16 añada los modelos de Whisper sin rehacerla.

#### 7. Transversal
- **Almacenamiento**: la referencia al original, el Markdown, los trozos y el índice, en SQLite (migración de Alembic); las imágenes extraídas de los documentos, en la carpeta de datos. No se guardan copias de los originales. El tamaño ocupado aparece en Ajustes › General, junto a los demás datos.
- **Selección de ficheros con su ruta real**: el selector y el arrastrar y soltar usan los de Tauri, que dan la ruta del fichero (los del navegador no la dan).
- **Procesado en segundo plano**, sin bloquear la API, con progreso y eventos en vivo por WebSocket.
- **API REST** de documentos (añadir por ruta o URL, editar, mover, nueva ruta, borrar, reprocesar, Markdown, servir el original al visor, abrir con el sistema, mostrar en la carpeta), búsqueda de prueba y modelos locales.
- **Plantillas de agente** (fase 02): las de Redactor, Comercial y Analista mencionan el conocimiento en sus instrucciones.
- Textos en i18n; diseño v7 (`docs/design/v2/`); accesible con teclado.
- **Tests**: conversión de cada formato con ficheros de ejemplo, extracción de imágenes, OCR, troceado, búsqueda híbrida con un modelo de *embeddings* falso, descripción de imágenes con un CLI falso y un `llama.cpp` falso, presupuesto de contexto, herramientas MCP, migración y componentes de la UI.
- **ADR**: almacenamiento por referencia, conversión, imágenes y OCR, troceado, *embeddings* y búsqueda híbrida, presupuesto de contexto, modelos y motores locales.

### Fuera
- Uso de GPU para *embeddings*, OCR o `llama.cpp` (se puede añadir más adelante).
- Usar `llama.cpp` para algo que no sea describir imágenes (p. ej. como CLI de agente o para los *embeddings*).
- Rastrear sitios web enteros, actualizar URLs de forma periódica o sincronizar carpetas del disco con la biblioteca.
- Conectores a servicios (Google Drive, Notion, Confluence…); encajan mejor con Conexiones MCP (fase 18).
- Audio y vídeo.
- *Embeddings* o reranking con APIs externas.
- Que los agentes **escriban** en el conocimiento (para eso está `write_project_memory`).
- Permisos por documento más finos que el nivel.
- Vigilar el disco para detectar al momento que un original se ha movido o ha cambiado (se comprueba al abrir la página y antes de cada acción).
- Subir ficheros con copia al servidor (hará falta en el modo servidor, fase 24).

## Historias de usuario
- Como usuario, quiero subir el PDF de la especificación al proyecto para que los agentes la consulten sin pegarla en cada tarea.
- Como usuario, quiero dar al Redactor el manual de marca una sola vez y que lo use en cualquier proyecto.
- Como usuario, quiero añadir la URL de la documentación de una API y que el agente la tenga a mano.
- Como usuario, quiero ver cómo ha quedado convertido un Excel o un PDF para saber si el agente lo entenderá.
- Como usuario, quiero probar qué encontraría un agente al buscar algo, para saber si el conocimiento está bien subido.
- Como usuario, quiero saber qué documentos consultó un agente en una ejecución.
- Como usuario, quiero que mis documentos no salgan de mi máquina y que la app no los duplique, guardando solo lo que necesita la IA.
- Como usuario, quiero abrir el original desde la app y, si lo he movido, decirle dónde está ahora.
- Como usuario, quiero ver el progreso de la conversión y, si falla, saber por qué y reprocesarlo.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Un agente usa un PDF del proyecto para responder**: con un PDF grande subido al proyecto, una tarea cuya respuesta solo está en el PDF se resuelve citándolo, y la ejecución registra la llamada a `search_knowledge` | e2e con el CLI falso + prueba manual con Claude Code real |
| CA2 | Se añaden y convierten `.md`, código, PDF con texto, `.docx`, `.xlsx`, `.pptx`, una URL y una imagen; cada uno avanza con su barra de progreso hasta «listo» y «Ver Markdown» muestra el contenido (tablas incluidas) | Tests con ficheros de ejemplo + revisión manual |
| CA3 | La app no guarda copias de los originales; PDF, imágenes, Markdown, texto, código y CSV se abren en el visor de la app, y Word, Excel y PowerPoint con la aplicación del sistema | Tests + revisión manual |
| CA4 | Si se borra o se mueve el original, al abrirlo la app avisa de que se borró o se movió y permite indicar la nueva ruta o quitarlo; con la nueva ruta y el mismo contenido se conserva el índice; si el original cambia, se marca «Ha cambiado» | Tests de backend y de componentes |
| CA5 | Una ejecución ve exactamente el conocimiento general, el de su proyecto y el de su agente, y no el de otros proyectos ni agentes | Tests de backend |
| CA6 | Los documentos pequeños en modo automático y los de «Siempre en contexto» entran enteros en el contexto hasta el presupuesto; el resto aparece en el índice y se encuentra con `search_knowledge`; los desactivados no aparecen | Tests del constructor de contexto |
| CA7 | La búsqueda híbrida encuentra el trozo correcto con una pregunta en español formulada con otras palabras, y con palabras exactas (un código de error, un nombre propio) | Tests con un corpus de ejemplo y el modelo real |
| CA8 | Sin el modelo de *embeddings*, la conversión y la búsqueda por palabras funcionan y la UI avisa; tras descargarlo, se reindexa solo y la búsqueda es híbrida, sin conexión | Tests + prueba manual |
| CA9 | Un documento que falla queda marcado como «Fallo» con el motivo en lenguaje claro, no lo usan los agentes y «Reprocesar» lo recupera al corregir la causa; sustituir, mover y borrar actualizan el índice | Tests de la API y de componentes |
| CA10 | El instalador incluye lo necesario para convertir y hacer OCR (con sus modelos), pero no `llama.cpp` ni los demás modelos; en una máquina limpia el OCR funciona sin internet, y los modelos de búsqueda se descargan desde Ajustes y la búsqueda funciona | Prueba manual con el instalador |
| CA11 | Por defecto, un PDF escaneado y una captura con texto se encuentran por su texto (OCR); las imágenes de un `.docx` se extraen, aparecen en su sitio en el Markdown y el agente recibe su ruta y las abre | Tests con ficheros de ejemplo + prueba manual con Claude Code |
| CA12 | Con «Describir imágenes con IA» activado, la descripción entra en el Markdown y en la búsqueda, tanto con un CLI *headless* (con aviso y consumo registrado) como con `llama.cpp`, que la app descarga e instala la primera vez | Tests con un CLI falso y un `llama.cpp` falso + prueba manual con los reales |
| CA13 | Todos los formatos pasan por la misma pipeline (MarkItDown y los pasos comunes), sin código de conversión por tipo fuera de sus plugins | Revisión del código + tests |
| CA14 | Durante el procesado se ven en vivo el uso de CPU, GPU (o «No disponible») y memoria; con los valores por defecto, procesar un PDF grande no deja el equipo sin respuesta, y se puede pausar y reanudar | Tests de la API + prueba manual |
| CA15 | Se pueden descargar y elegir los tres modelos de *embeddings* y los dos de visión (Qwen y Gemma) desde Ajustes › Modelos locales; cambiar el de *embeddings* reindexa en segundo plano | Tests + prueba manual |
| CA16 | Lint, tests de backend y de frontend en verde; ADR escrito; `/code-review` resuelto | CI local |

## Prerrequisitos
- Fase 13 cerrada (`v1.5`).
- Claude Code con sesión iniciada, para la prueba manual de CA1.

## Riesgos y preguntas abiertas
- **Recuperación de información** (decidido, 2026-10-18): **búsqueda híbrida**, por palabras y por *embeddings*. Las dos alternativas por separado tienen huecos:
  - **solo *embeddings*** (búsqueda vectorial): entiende el significado, pero falla con términos exactos (`ERR_4012`, un nombre de clase, una referencia de producto);
  - **solo por palabras**: no necesita modelo y es muy ligera, pero no encuentra nada si la pregunta usa otras palabras que el documento.
  Combinarlas cubre ambos casos con poco coste: el índice de palabras ocupa poco y los vectores, unos 1,5 KB por trozo (unos 3 MB para un PDF de 500 páginas). El modelo se descarga una vez (unos 100–500 MB) y, mientras no está, se usa solo la búsqueda por palabras.
- **Ficheros referenciados**: si el usuario mueve o borra el original, los agentes siguen teniendo el Markdown, pero ya no se puede reprocesar ni abrir. Es el precio de no duplicar los ficheros; la UI lo deja claro con «No encontrado».
- **Visor de PDF**: el visor nativo de WebView2 o `pdf.js`. Hay que servir el original desde el backend o con el protocolo de ficheros de Tauri, sin abrir el acceso a todo el disco. Se decide en el plan.
- **Conversión con MarkItDown** (decidido, 2026-10-18; licencia MIT). Puntos que el spike tiene que comprobar con ficheros reales:
  - sus **PDFs** salen como texto plano, sin títulos ni tablas y quizá sin marcas de página; hace falta un plugin si la calidad no basta para trocear y citar la página;
  - no extrae las **imágenes incrustadas** ni hace **OCR** por defecto: van como plugin (con el OCR de ONNX);
  - sus dependencias (p. ej. `pandas` para Excel) pesan en PyInstaller: se instalan solo los extras de los formatos de la spec y se mide el tamaño;
  - su opción de describir imágenes con un LLM usa un cliente compatible con OpenAI; `llama-server` expone esa API, así que la descripción local puede ir por ahí.
  Se descartan las alternativas de una sola librería más completas, como Docling o Unstructured, porque arrastran PyTorch y son demasiado pesadas para el *sidecar*.
- **Modelos de Google con licencia aceptada**: algunos modelos Gemma en Hugging Face piden aceptar su licencia con una cuenta antes de descargarlos. El spike comprueba si hay versiones descargables sin cuenta (ONNX y GGUF). Si no las hay, Ajustes pide un *token* de Hugging Face, guardado de forma segura, solo para esos modelos.
- **Lectura de la GPU**: en Windows, con los contadores de rendimiento «GPU Engine», que sirven para cualquier fabricante; NVML solo cubre NVIDIA. Se decide en el plan; si no se puede leer, la UI muestra «No disponible».
- **Imágenes** (decidido, 2026-10-18): por defecto, OCR local y que el agente abra las imágenes con su CLI. La descripción con IA es opcional, con un CLI *headless* o con un modelo de visión local en `llama.cpp`, que se descarga aparte.
- **Motor de *embeddings***: ONNX Runtime en CPU, usado directamente (con `tokenizers`) o a través de `fastembed`. Se descarta `sentence-transformers`, que arrastra PyTorch y es demasiado pesado para el *sidecar*. Spike corto en el plan: calidad en español de `multilingual-e5-small`, EmbeddingGemma y `bge-m3`, velocidad indexando un PDF de 200 páginas y tamaño.
- **Vectores**: se propone guardarlos en SQLite y compararlos por fuerza bruta con NumPy, que basta para decenas de miles de trozos. Si el volumen crece mucho, se puede pasar a la extensión `sqlite-vec` sin cambiar la API.
- **Motor de OCR**: RapidOCR (modelos de PaddleOCR en ONNX) u otro equivalente en ONNX. El spike mide la calidad con capturas y escaneos en español y el tamaño.
- **`llama.cpp` descargado**: hay que fijar qué versión y qué binario se descargan (CPU, por plataforma; de momento Windows), verificar su suma de comprobación y arrancar `llama-server` en un puerto local con el modelo de visión (GGUF + proyector `mmproj`). Modelos: Qwen 3.5 y Gemma 4 en su variante pequeña con visión, con aviso de la lentitud en CPU; el spike mide cuánto tarda cada uno por imagen y cuánta memoria usa. Algunos antivirus pueden avisar al bajar un ejecutable: se documenta y se muestra un error claro si no arranca.
- **Imágenes fuera de la carpeta de trabajo**: el agente tiene que leer las imágenes en su ruta original, fuera del workspace. Hay que comprobar cómo dar acceso en cada CLI (`--add-dir` en Claude Code; en `agy`, por confirmar). Si no se puede, se copian temporalmente a una carpeta del workspace que no se añade a git y se borra al terminar la ejecución.
- **Presupuesto de contexto**: inyectar demasiado encarece cada ejecución y ocupa la ventana del CLI. Se propone un valor por defecto prudente (p. ej. 8.000 tokens en total y 2.000 por documento para considerarlo «pequeño»), ajustable en Ajustes. Los tokens se estiman sin tokenizador exacto.
- **Tamaño del instalador**: las librerías de conversión, el OCR y ONNX Runtime pueden añadir bastante peso al *sidecar*. Se mide en el plan; los modelos y `llama.cpp` siempre se descargan aparte.
- **Tamaño de la fase**: es grande. El plan la dividirá en bloques: spike → ficheros por referencia y conversión → búsqueda híbrida y MCP → imágenes y OCR → modelos locales → descripción opcional (CLI y `llama.cpp`) → UI.
