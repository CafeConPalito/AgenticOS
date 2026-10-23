# Fase 17: Skills · Spec

- **Estado**: borrador
- **Rama**: `phase/17-skills`

## Objetivo
Que los agentes trabajen con **skills**: paquetes de instrucciones reutilizables (un `SKILL.md` con su descripción y, si hace falta, ficheros de apoyo) que enseñan a hacer algo concreto («revisión de código», «escribir una migración de Alembic», «redactar una propuesta comercial»). El usuario las tiene en una **biblioteca de tres niveles** (general, proyecto, agente). En cada ejecución, **la skill adecuada se carga sola** según la tarea, con cualquier CLI. Los agentes pueden **proponer skills nuevas** a partir de lo que han aprendido, que el usuario aprueba o rechaza. Cada skill tiene su **historial de cambios**. Y el usuario puede **explorar los registros públicos más usados** e instalar desde ellos las skills que quiera.

## Punto de partida (fases 04, 14 y 15)
- Cada ejecución recibe sus instrucciones y el MCP `agentic-os` sin tocar la configuración del usuario (ADR 0004): Claude Code por *flags* y `agy` por un plugin de workspace en `.agents/plugins/agentic-os/`.
- El conocimiento ya tiene los mismos tres niveles (general, proyecto, agente), un índice dentro del presupuesto de contexto, búsqueda por significado con el modelo local de *embeddings* y propuestas de los agentes con confirmación en la Inbox (`propose_knowledge`). Las skills reutilizan estas piezas en vez de crear otras.
- El diseño ya reserva el sitio: la pestaña **Skills** del agente y la sección «Biblioteca de skills» del `KnowledgePanel` (`docs/design/screens.md` §10), con tarjetas, interruptor, chip «Autoseleccionada», contador de uso y propuestas con borde violeta.
- Claude Code y Antigravity tienen su propio mecanismo de skills (carpetas con `SKILL.md` que el modelo carga según la descripción). Su comportamiento con el aislamiento de ADR 0004 no está verificado: se resuelve en el spike del bloque 0.

## Alcance
### Dentro
**A. Biblioteca de skills**
- Una skill es una **carpeta** con `SKILL.md` (cabecera YAML con `name` y `description`, y el cuerpo en Markdown) y ficheros opcionales (plantillas, ejemplos, *scripts*). Es el mismo formato que usan Claude Code y Antigravity, así que una skill hecha para ellos sirve tal cual.
- **Tres niveles**, como el conocimiento: **general** (todos los agentes), **proyecto** (las ejecuciones de ese proyecto) y **agente** (solo ese agente). Una ejecución ve las generales, las de su proyecto y las de su agente. Si dos se llaman igual, gana la más concreta (agente > proyecto > general).
- **Crear y editar** desde la app: nombre, descripción, editor Markdown con vista previa (el de las instrucciones del agente) y lista de ficheros de apoyo (añadir, ver, quitar).
- **Importar** una carpeta, un `.zip` o un `SKILL.md` suelto (arrastrar y soltar o examinar).
- **Importar las skills que el usuario ya tiene** en sus CLIs (`~/.claude/skills`, la carpeta de skills de Antigravity, `.claude/skills` del proyecto):
  - la app las lista y el usuario elige cuáles importar y **a qué nivel** (general, un proyecto o un agente);
  - se copian sin tocar el original.
- **Exportar** una skill como `.zip`.
- Las skills se guardan en la carpeta de datos de Agentic OS, nunca en el repo del proyecto.
- Cada skill se puede **activar o apagar**. Se valida al guardar: cabecera correcta, nombre único en su nivel, descripción no vacía y tamaño máximo.
- **Historial de cambios** de cada skill:
  - cada cambio guarda una versión nueva, con su autor y su origen: el usuario, un agente (propuesta aprobada), una importación o una actualización desde un registro público;
  - se ve la lista de versiones con fecha, autor y un resumen;
  - se ven las **diferencias** entre dos versiones cualesquiera, línea a línea, en `SKILL.md` y en los ficheros de apoyo (con el visor de diffs de la fase 11);
  - se puede **restaurar** cualquier versión, lo que crea una versión nueva sin borrar las anteriores;
  - en el registro de cada ejecución queda qué versión de cada skill usó.
- Pantallas, según el diseño: «Conocimiento y skills» en la navegación, `KnowledgePanel` con la sección de skills en Ajustes (general), Proyecto › Conocimiento y Agente › Skills, con el contador «N activas de M».

**B. Uso en las ejecuciones y autoselección**
- **Por agente y por etapa del pipeline**, cada skill visible puede ser:
  - **Automática** (por defecto): se ofrece si encaja con la tarea;
  - **Siempre**: se carga entera en todas sus ejecuciones;
  - **Nunca**: no se ofrece.
- Se configura en la pestaña Skills del agente y en cada etapa del editor de pipeline. Si la etapa y el agente dicen cosas distintas, **manda la etapa**. Por ejemplo, la etapa QA puede fijar «revisión de código» como Siempre aunque el agente la tenga en Automática. Lo que no fije la etapa lo decide el agente. Las ramas de un pipeline (fase 13) son etapas, así que también tienen su configuración.
- **Autoselección en dos pasos**, igual con todos los CLIs:
  1. Agentic OS elige las skills candidatas para la tarea, comparando su descripción con el texto de la tarea, la etapa y el rol del agente. Usa el modelo de significado de la fase 14 o, si no hay, las palabras clave.
  2. La ejecución recibe una sección **«Skills»** en su contexto con las candidatas (nombre y descripción en una línea, dentro de un presupuesto de tokens) y las de «Siempre» enteras. El agente carga el resto cuando le hagan falta con la herramienta MCP **`use_skill`**, y lee los ficheros de apoyo con **`read_skill_file`**.
- **Mecanismo nativo del CLI** (si el spike lo confirma): además de lo anterior, las skills de la ejecución se pasan al CLI por su propio mecanismo, sin tocar la configuración del usuario. En Claude Code sería un plugin o directorio por ejecución; en `agy`, dentro del plugin de workspace de ADR 0004. Así el CLI las carga como suyas, con sus *scripts*.
- **Aislamiento**: por defecto la ejecución **solo** ve las skills de la biblioteca, no las que el usuario tenga instaladas en sus CLIs. Así la ejecución es la misma en cualquier máquina y no carga skills que nadie ha elegido (si el spike lo permite).
- **Registro**: en cada ejecución queda qué skills se ofrecieron, cuáles cargó el agente y por qué vía (contexto, `use_skill` o mecanismo nativo). En la tarjeta de cada skill se ve cuántas veces se ha usado y cuándo fue la última, y en la ejecución aparece el chip «Autoseleccionada».
- **Probador**: dado el texto de una tarea y un agente, la app muestra qué skills se ofrecerían y en qué orden, como el probador de búsqueda de la fase 14.

**C. Skills propuestas por los agentes**
- Herramienta MCP **`propose_skill`** para todos los agentes y CLIs: nombre, descripción, cuerpo Markdown, ficheros de apoyo opcionales (texto) y el nivel sugerido. También puede proponer una **versión nueva** de una skill existente, que queda como propuesta «reemplaza a…».
- La propuesta **no bloquea** al agente. Queda en estado **«Propuesta»**: no se ofrece a ninguna ejecución hasta que el usuario la aprueba.
- **Confirmación del usuario** en la **Inbox** (nueva clase de petición «Skill propuesta») y en la biblioteca (tarjeta con borde violeta: «Propuesta por Dev – pendiente de aprobar»). El usuario ve el texto y los ficheros, puede **editarlos**, elige el **nivel** y **aprueba o rechaza**.
- Los **ficheros ejecutables** de una propuesta (*scripts*) se marcan aparte y el usuario tiene que verlos antes de aprobar.
- **Nunca se modifica una skill existente** sin aprobación. Una versión nueva aprobada pasa a ser la actual y queda en el historial; antes de aprobarla se ven sus diferencias con la versión actual.
- **Procedencia** visible: qué agente la propuso, en qué ejecución y tarea, y cuándo. Las skills aprobadas llevan la marca **«Creada por agente»**.
- **Controles anti-ruido** (como en la fase 15):
  - máximo de propuestas por ejecución (1 por defecto, configurable) y tamaño máximo;
  - aviso al agente si ya existe una skill muy parecida;
  - el rechazo queda registrado para no volver a proponer lo mismo;
  - un ajuste global para desactivar las propuestas.

**D. Explorador de registros públicos**
- Vista **«Explorar»** en «Conocimiento y skills» para buscar e instalar skills de los **registros públicos más usados**. Se empieza con estos cuatro, a confirmar en el spike según la API que ofrezca cada uno:
  - **skills.sh** (Vercel): clasificación por instalaciones;
  - **`anthropics/skills`** en GitHub: skills oficiales de Anthropic;
  - **SkillsMP**: el índice más grande, rastreado de GitHub;
  - **ClawHub**.
- Cada registro es una **fuente** que se puede activar o apagar en Ajustes. También se puede instalar desde la URL de cualquier repositorio de GitHub que contenga skills.
- **Búsqueda** por texto en todas las fuentes activas, con filtros por fuente y por categoría (si la fuente las tiene). La lista por defecto muestra las **más usadas**, por instalaciones o estrellas.
- **Ficha** de cada skill antes de instalarla:
  - descripción, autor, fuente, enlace al repositorio, instalaciones o estrellas y fecha de la última actualización;
  - el `SKILL.md` completo y la lista de ficheros, con los **ejecutables marcados**.
- **Instalar** copia la skill a la biblioteca en el **nivel que elija el usuario**. A partir de ahí es una skill más: se puede editar, apagar o borrar, y tiene su historial (la primera versión es «instalada desde…»).
- **Procedencia y actualizaciones**:
  - la skill guarda de dónde vino (fuente, repositorio y versión o *commit*);
  - la app avisa cuando la fuente tiene una versión nueva y enseña las diferencias antes de actualizar;
  - nunca se actualiza sola;
  - si el usuario la había editado, la actualización llega como una versión nueva del historial, sin perder sus cambios anteriores.
- **Seguridad**:
  - no se instala nada sin la confirmación del usuario;
  - antes de instalar una skill con *scripts*, el usuario tiene que haberlos visto;
  - se muestra un aviso permanente de que las skills de terceros pueden traer código malicioso;
  - si la fuente da un análisis de seguridad (p. ej. el de skills.sh), se enseña en la ficha.
- Las búsquedas se cachean un tiempo corto. Sin conexión, la vista lo dice y la biblioteca local funciona igual.

### Fuera
- **Publicar** skills en registros públicos, valorarlas o comentarlas. Solo se explora e instala.
- Registros de pago o que exijan cuenta, salvo un *token* opcional de GitHub para no chocar con su límite de peticiones.
- Sincronizar la biblioteca con las carpetas de skills de los CLIs en ambos sentidos. Solo se importa y se exporta.
- Que los agentes editen o borren skills directamente. Solo proponen.
- Aprobar propuestas de forma automática.
- Comandos de barra (`/comando`), *hooks* o agentes definidos dentro de un plugin; solo skills.
- Skills para Codex y OpenCode: llegan con sus adapters en la fase 21, que deberá cubrirlas.
- El Arquitecto asignando skills a un agente nuevo (fase 19).

## Historias de usuario
- Como usuario, quiero tener mis skills (p. ej. «revisión de código» o «migraciones de Alembic») en una biblioteca y decidir si valen para todos, para un proyecto o para un agente, para no repetir las mismas instrucciones en cada agente.
- Como usuario, quiero importar las skills que ya uso con Claude Code, para no reescribirlas.
- Como usuario, quiero que el agente use la skill que corresponde a la tarea sin que yo la elija, y ver después cuál usó.
- Como usuario, quiero fijar una skill como «siempre» en un agente concreto o en una etapa del pipeline, o prohibirla, para tener control cuando la autoselección no basta.
- Como usuario, quiero ver qué ha cambiado en una skill, quién lo cambió y volver a una versión anterior si la nueva funciona peor.
- Como usuario, quiero buscar en los registros públicos las skills más usadas, revisar una antes de instalarla y elegir a qué nivel la instalo.
- Como agente, quiero ver una lista corta de las skills que encajan con mi tarea y cargar la que necesito, para no llenar el contexto con todas.
- Como usuario, quiero que un agente que ha descubierto una forma de hacer algo pueda proponerla como skill, y revisarla (sobre todo sus *scripts*) antes de que nadie la use.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | Se crea, edita, apaga, exporta y borra una skill en cada nivel desde la UI. Una skill con cabecera mal formada o con el nombre repetido en su nivel no se guarda y el error se explica con palabras | tests de API + UI |
| CA2 | Se importan una carpeta, un `.zip` y las skills de `~/.claude/skills`, eligiendo para cada una el nivel. El original no cambia (mismo hash) y la skill importada funciona igual en una ejecución | tests + manual |
| CA3 | La sección «Skills» de una ejecución contiene solo las skills visibles para su agente y su proyecto, aplica la precedencia agente > proyecto > general, respeta «Siempre» y «Nunca» y no pasa del presupuesto de tokens | tests |
| CA4 | Los modos de la etapa mandan sobre los del agente: una skill en Siempre en la etapa QA se carga entera aunque el agente la tenga en Automática, y una en Nunca en la etapa no se ofrece aunque el agente la tenga en Siempre. Lo mismo en una rama | tests |
| CA5 | Con un corpus de prueba de al menos 15 skills, la skill relevante queda entre las 3 primeras candidatas en al menos el 90 % de las tareas de prueba, con modelo de significado y sin él | test de calidad (como el de la fase 14) |
| CA6 | **La skill relevante se carga sola**: un agente (CLI falso con cliente MCP real, y `claude` y `agy` en la prueba manual) recibe una tarea que encaja con una skill, la carga con `use_skill` o por el mecanismo nativo y la sigue. El registro de la ejecución dice cuál y por qué vía | test e2e + manual |
| CA7 | `read_skill_file` solo da ficheros de skills visibles para esa ejecución, y nunca una ruta fuera de la carpeta de la skill | tests |
| CA8 | La configuración del usuario no cambia: `~/.claude`, sus skills y la configuración de `agy` están igual antes y después de una ejecución con skills (comparando snapshots, como en el spike de la fase 01) | test + manual |
| CA9 | **Se registra una skill creada por un agente**: `propose_skill` crea una skill «Propuesta» que aparece en la Inbox y en la biblioteca, no se ofrece a nadie hasta aprobarla y, al aprobarla (editada y con otro nivel), se ofrece a la siguiente ejecución con la marca «Creada por agente» y su procedencia | test e2e + UI |
| CA10 | Se respetan el máximo de propuestas por ejecución, el tamaño máximo, el aviso de skill parecida, el rechazo registrado y el ajuste que desactiva las propuestas. El agente recibe el motivo con palabras | tests |
| CA11 | Una versión nueva propuesta de una skill no cambia la actual hasta aprobarla, y antes de aprobarla se ven sus diferencias | tests + UI |
| CA12 | Cada cambio (usuario, agente, importación o actualización desde un registro) crea una versión con autor y origen. Se ven las diferencias entre dos versiones cualesquiera, restaurar crea una versión nueva sin borrar ninguna, y la ejecución registra qué versión usó | tests + UI |
| CA13 | Las propuestas con *scripts* los muestran marcados como ejecutables, y la UI no deja aprobarlas sin haberlos abierto | test de UI |
| CA14 | El uso de cada skill (veces y última fecha) y el chip «Autoseleccionada» se ven en la tarjeta y en la ejecución | test + UI |
| CA15 | Con el binario empaquetado funciona el flujo completo: importar → ejecución que carga la skill → proponer → Inbox → aprobar | e2e empaquetado |
| CA16 | El explorador busca en las fuentes activas y lista por defecto las más usadas. La ficha muestra el `SKILL.md`, los ficheros (con los ejecutables marcados) y la procedencia, e instalar la copia al nivel elegido con su primera versión «instalada desde…» | tests con las fuentes simuladas + manual con las reales |
| CA17 | Cuando la fuente publica una versión nueva, la app la avisa y enseña las diferencias. No actualiza sin confirmación, y si la skill estaba editada no se pierde nada del historial | tests |
| CA18 | No se instala una skill con *scripts* sin haberlos abierto. Sin conexión, el explorador lo dice y la biblioteca funciona igual. Una fuente que falla no rompe las demás | tests + UI |

## Prerrequisitos
- **Fase 16 cerrada** (hecho).
- Lo reutilizado de las fases 14 y 15: niveles, modelo local de significado, presupuesto de contexto, Inbox y flujo de propuestas.

## Riesgos y preguntas abiertas
- **Mecanismo nativo de cada CLI (spike, bloque 0)**. Hay que comprobar en Windows:
  - si Claude Code carga skills de un directorio o plugin indicado por *flag* sin escribir en `~/.claude`;
  - si `--setting-sources project,local` deja fuera las skills personales del usuario;
  - si `agy` admite skills dentro de un plugin de workspace;
  - cómo se comportan los *scripts* de una skill con cada modo de permisos.

  Si algún CLI no lo permite, se queda solo con la vía común (contexto + `use_skill`), que funciona en todos.
- **Seguridad de los *scripts***: una skill puede traer código que el agente ejecutará con sus permisos. El riesgo crece con los registros públicos: en enero de 2026 ClawHub sufrió una campaña con más de 335 skills maliciosas. Mitigación:
  - los *scripts* de las propuestas y de las skills instaladas desde un registro se revisan sí o sí;
  - las importadas muestran sus ficheros ejecutables;
  - las skills no cambian los permisos del agente;
  - se enseña el análisis de seguridad de la fuente cuando lo hay;
  - en el spike se decide si ClawHub entra en las fuentes activas por defecto.
- **APIs de los registros (spike, bloque 0)**: hay que comprobar qué ofrece cada fuente (API pública, límites de peticiones, si da instalaciones o estrellas, versiones, licencia) y si sus condiciones permiten usarla desde una app. Una fuente sin API estable se sustituye por otra de las más usadas o se lee a través de su repositorio de GitHub.
- **Licencias**: cada skill de terceros tiene la suya. La ficha la muestra y se guarda con la procedencia.
- **Tamaño del historial**: guardar cada versión con sus ficheros ocupa espacio. Se guarda de forma eficiente (sin duplicar ficheros que no han cambiado), y su uso de disco se ve en Ajustes.
- **Calidad de la autoselección**: con descripciones pobres se eligen mal. Se calibra con el corpus de prueba y el probador ayuda al usuario a mejorar las descripciones. Por eso existen «Siempre» y «Nunca».
- **Coste en tokens**: muchas skills llenan el contexto. Por eso el índice va acotado, el cuerpo solo se carga a demanda y «Siempre» tiene un tope de tamaño.
- **Doble carga**: si el CLI carga una skill por su cuenta y además está en el contexto, se repite. El plan decide qué va por cada vía según el resultado del spike.

## Decisiones del usuario sobre el borrador (2026-10-23)
1. **Skills personales**: las ejecuciones **ignoran** las skills ya instaladas en los CLIs. El usuario puede importarlas al nivel que quiera.
2. **Modos**: Automática, Siempre y Nunca se eligen **por agente y por etapa del pipeline**, y manda la etapa.
3. **Propuestas**: máximo **1 por ejecución** por defecto.
4. **Versiones**: **historial de cambios completo**, con diferencias entre versiones y restauración.
5. **Registros públicos**: se añade un **explorador** de los registros más usados (apartado D). Cambia lo que decía `docs/vision.md`, que dejaba los registros fuera.
