# Fase 18: Conexiones MCP · Spec

- **Estado**: aprobada (2026-10-24)
- **Rama**: `phase/18-conexiones-mcp`
- **Plan**: [plan.md](plan.md)

## Objetivo
Que los agentes usen **servidores MCP externos** (GitHub, una base de datos, un navegador, Notion, servicios propios…) configurados una sola vez desde la app. El usuario tiene un **catálogo de conexiones** con sus credenciales guardadas de forma segura (también con inicio de sesión OAuth), decide qué agentes, proyectos y etapas usan cada una, y cada ejecución las recibe en la configuración de su CLI, junto al MCP `agentic-os`, **sin tocar la configuración del usuario**. Antes de asignarla, el usuario puede **probar la conexión**, ver sus herramientas y elegir cuáles se permiten. Y puede **explorar los registros públicos de servidores MCP** e instalar desde ellos los que quiera, como con las skills.

## Punto de partida (fases 01, 04, 12 y 17)
- Cada ejecución recibe su MCP `agentic-os` sin tocar la configuración del usuario (ADR 0004):
  - **Claude Code**: `--mcp-config <run>/mcp.json --strict-mcp-config`. El `--strict-mcp-config` hace que **no** arranquen los MCP que el usuario tenga configurados en `~/.claude.json` (evita los huérfanos vistos en el spike de la fase 01). Hoy, por tanto, ningún agente tiene MCP externos.
  - **`agy`**: plugin de workspace `.agents/plugins/agentic-os/` con `mcp_config.json`. Solo se ha probado con una URL; ni `stdio`, ni cabeceras, ni variables de entorno.
- Las herramientas propias se preaprueban (`--allowedTools mcp__agentic-os__*`); las demás siguen el modo de permisos del agente.
- Secretos: la app no guarda ningún secreto propio (ADR 0018). Los *tokens* de GitHub, GitLab y Hugging Face van al *helper* de credenciales de git. Las conexiones MCP necesitan más que un *token* por host (variables de entorno, cabeceras, cadenas de conexión, *tokens* OAuth), así que van al almacén del sistema (decisión 1).
- Las skills (fase 17) y el conocimiento (fase 14) ya tienen tres niveles, configuración por agente y por etapa, un explorador de registros públicos y un registro de uso por ejecución. Las conexiones reutilizan esas piezas donde encajan.
- El diseño ya menciona «Navegador (Playwright)» entre las herramientas permitidas del agente (`docs/design/screens.md` §2).

## Alcance
### Dentro
**A. Catálogo de conexiones**
- Una **conexión** es un servidor MCP con nombre, descripción, icono y transporte:
  - **`stdio`**: comando, argumentos, carpeta de trabajo y variables de entorno (p. ej. `npx -y @modelcontextprotocol/server-postgres`);
  - **HTTP** (*streamable HTTP*, y SSE si el CLI lo admite): URL y cabeceras.
- **Crear y editar** desde la app, con un formulario por transporte y un modo «JSON» que acepta el bloque `mcpServers` que publican casi todos los servidores (pegar y listo).
- **Plantillas** de los servidores más usados para empezar en un clic, con los campos que piden: GitHub, Playwright, PostgreSQL, SQLite, Filesystem, Fetch, Context7 y algún servicio remoto (Notion o Linear), a confirmar en el spike. Una plantilla solo rellena el formulario: no instala nada sin que el usuario lo pida. Para el resto está el explorador (apartado G).
- **Importar** las conexiones que el usuario ya tiene en sus CLIs (`~/.claude.json`, `.mcp.json` del proyecto, la configuración MCP de `agy`): la app las lista, el usuario elige cuáles importar y a qué nivel, y los secretos que encuentre pasan al almacén del sistema. Se copian sin tocar el original.
- **Exportar** una conexión como JSON `mcpServers`, **sin** secretos (quedan como `${NOMBRE}`).
- Cada conexión se puede **activar o apagar** globalmente. Se valida al guardar: nombre único con caracteres válidos para el prefijo de herramientas (`mcp__<nombre>__…`), comando o URL presentes y sin colisión con `agentic-os`.
- Las conexiones se guardan en la base de datos de Agentic OS, nunca en el repo del proyecto.

**B. Credenciales**
- Los valores secretos (variables de entorno, cabeceras como `Authorization`, contraseñas dentro de una cadena de conexión) se marcan como **secretos** y se guardan en el **almacén del sistema** (Administrador de credenciales de Windows, Llavero de macOS, Secret Service en Linux, con la librería `keyring`), una entrada por secreto; nunca en la base de datos ni en los registros. Se amplía ADR 0018.
- La API nunca devuelve un secreto: solo si está puesto, y la UI permite reemplazarlo o borrarlo.
- Un secreto puede **referenciar** una variable de entorno del sistema (`${GITHUB_TOKEN}`) en vez de guardarse.
- En la ejecución, los secretos llegan al CLI de la forma menos expuesta que permita cada uno (spike): como variables de entorno del proceso y referencias `${VAR}` en el fichero, en lugar de escribirlos en claro en `<run>/mcp.json` o en el plugin de `agy`. Si un CLI obliga a escribirlos en un fichero, ese fichero vive solo en la carpeta de la ejecución (o en el plugin temporal de `agy`), se borra al terminar y queda fuera de git.
- Los secretos se **ocultan** en el terminal, el log de la ejecución y los diagnósticos (se sustituyen por `•••`).
- **OAuth** para servidores remotos que lo exigen (Notion, Linear, Atlassian, el MCP remoto de GitHub…):
  - botón **«Conectar»** en la conexión: la app hace el flujo OAuth del estándar MCP (descubrimiento del servidor de autorización, registro dinámico del cliente cuando lo hay y PKCE), abriendo el navegador del sistema y recibiendo la respuesta en `127.0.0.1`;
  - si el servidor no admite registro dinámico, el usuario pega su *client id* (y el secreto si hace falta);
  - el *token* y el de renovación van al almacén del sistema; la app lo **renueva** antes de cada ejecución si va a caducar y lo pasa como cabecera `Authorization`;
  - la conexión muestra la cuenta conectada y la caducidad, y se puede **desconectar** (borra los *tokens* y, si el servidor lo admite, los revoca);
  - si la renovación falla, la conexión queda como «Hay que volver a conectar», la ejecución sigue sin ella y llega un aviso a la Inbox.

**C. Prueba de conexión y herramientas**
- **Probar** una conexión: Agentic OS arranca el servidor (o conecta a la URL) como cliente MCP, hace el `initialize` y lista sus **herramientas**, **recursos** y **prompts**, con la descripción y el esquema de cada herramienta.
- El resultado dice con palabras qué ha fallado: comando no encontrado (p. ej. falta Node para `npx`), el proceso se cae (con las últimas líneas de su `stderr`), *timeout*, 401/403, URL inaccesible o protocolo incompatible.
- La lista de herramientas se guarda con la fecha de la prueba y se puede volver a pedir. Si cambia (herramientas nuevas o quitadas), la app lo avisa.
- **Herramientas permitidas** por conexión: todas por defecto, o una selección. Las no permitidas no llegan al agente (filtradas por el CLI cuando lo permita; si no, con la pasarela del apartado E).
- Marca de **solo lectura / escritura** por herramienta cuando el servidor la declara (`readOnlyHint`, `destructiveHint`), para ayudar a elegir.

**D. Asignación**
- Una conexión se asigna a nivel **general** (todos los agentes), **proyecto** (las ejecuciones de ese proyecto) o **agente** (solo ese agente), como el conocimiento y las skills. Una ejecución recibe las conexiones generales, las de su proyecto y las de su agente que estén activas.
- **Por agente** se puede quitar una conexión que le llegue de un nivel superior (p. ej. el agente «Redactor» sin acceso a la base de datos del proyecto).
- **Por etapa del pipeline** (y por rama, que es una etapa): se puede **quitar** una conexión en esa etapa (p. ej. QA sin acceso de escritura a la base de datos). No hay autoselección ni modos Automática/Siempre/Nunca: una conexión asignada siempre llega, porque sus herramientas ya se describen solas al CLI.
- Se configura en una pestaña **«Conexiones»** del agente y del proyecto, en cada etapa del editor de pipeline y en Ajustes › Conexiones (catálogo y nivel general).
- Los **subagentes** (`spawn_subagent`) reciben las conexiones de su agente, no las del padre.
- Las ejecuciones *headless* internas (decisor de ramas de la fase 13, descripción de imágenes de la fase 14) no reciben conexiones externas.

**E. Inyección en cada CLI**
- **Claude Code**: las conexiones de la ejecución se añaden al `<run>/mcp.json` junto a `agentic-os`, se sigue usando `--strict-mcp-config` y las herramientas permitidas se reflejan en `--allowedTools` / `--disallowedTools` según el modo de permisos del agente.
- **`agy`**: dentro del plugin de workspace de ADR 0004, si el spike confirma que su `mcp_config.json` admite `stdio`, cabeceras y entorno.
- **Pasarela de respaldo**: solo para lo que un CLI no admita (lo dice el spike), Agentic OS reexpone el servidor externo por HTTP en `127.0.0.1` con el *token* de la ejecución, le pasa los secretos y filtra sus herramientas. Por defecto, la inyección es directa.
- **Permisos**: las herramientas externas **no** se preaprueban como las de `agentic-os`. Siguen el modo del agente: en *Autónomo* se usan sin preguntar; en *Restringido* y *Preguntar* el usuario puede marcar por conexión qué herramientas se preaprueban, y el resto pide permiso como cualquier otra herramienta.
- **Ciclo de vida**: los servidores `stdio` los arranca el CLI como hijos suyos; al terminar o cancelar la ejecución no queda ningún proceso huérfano (se comprueba con el árbol de procesos de ADR 0007).
- Si una conexión no arranca en una ejecución, la ejecución **sigue** sin ella y queda un aviso en el registro y en la página de la ejecución.
- Se mantiene ADR 0004: la configuración del usuario no cambia.

**F. Registro y uso**
- En cada ejecución queda qué conexiones recibió (con su versión de configuración, sin secretos), si conectaron y qué herramientas externas llamó el agente (nombre, hora, duración y si falló), leído del transcript del CLI.
- La página de la ejecución muestra estas llamadas en «Eventos MCP», distinguiendo las de `agentic-os` de las externas.
- En la tarjeta de cada conexión: número de ejecuciones que la usaron, llamadas y la fecha del último uso. (Un panel de estadísticas completo como el de las skills queda fuera.)

**G. Explorador de registros públicos**
- Vista **«Explorar»** en Conexiones para buscar e instalar servidores MCP de los **registros públicos más usados**, como el explorador de skills de la fase 17. Se empieza con estos, a confirmar en el spike según la API que ofrezca cada uno:
  - el **registro oficial de MCP** (`registry.modelcontextprotocol.io`), con su API abierta y el formato `server.json`;
  - **Smithery**;
  - **Glama**;
  - **PulseMCP**.
- Cada registro es una **fuente** que se puede activar o apagar en Ajustes. También se puede instalar desde la URL de un repositorio de GitHub o de un paquete npm o PyPI.
- **Búsqueda** por texto en todas las fuentes activas, con filtros por fuente, categoría (si la fuente las tiene) y transporte (local `stdio` o remoto HTTP). La lista por defecto muestra los **más usados**, por instalaciones, descargas o estrellas.
- **Ficha** de cada servidor antes de instalarlo:
  - descripción, autor, fuente, enlace al repositorio, licencia, instalaciones o estrellas, versión y fecha de la última actualización;
  - cómo se ejecuta: paquete (npm, PyPI, imagen de Docker) o URL remota, con el **comando exacto** que se lanzará y los **requisitos** (Node, Python, Docker), marcando los que faltan en la máquina;
  - las variables y cabeceras que pide, cuáles son secretas y si usa OAuth;
  - las herramientas que declara, si la fuente las da;
  - si es oficial del servicio (p. ej. el de GitHub publicado por GitHub) o de un tercero, y el análisis de seguridad si la fuente lo tiene.
- **Instalar** crea una conexión en el catálogo, al **nivel que elija el usuario**, con el formulario ya rellenado: el usuario completa los secretos (o pulsa «Conectar» si es OAuth), la prueba y la guarda. A partir de ahí es una conexión más.
- Los paquetes se ejecutan **fijados a la versión** instalada (`paquete@1.2.3`), no a la última, para que el código no cambie sin saberlo.
- **Procedencia y actualizaciones**:
  - la conexión guarda de dónde vino (fuente, paquete o URL y versión);
  - la app avisa cuando hay una versión nueva y enseña qué cambia (versión, comando, variables y herramientas declaradas) antes de actualizar;
  - nunca se actualiza sola.
- **Seguridad**:
  - no se instala nada sin la confirmación del usuario, y antes se ve el comando que se va a ejecutar;
  - aviso permanente de que los servidores de terceros ejecutan código en la máquina o reciben los datos que les mande el agente;
  - los servidores oficiales del servicio se distinguen de los de terceros.
- Las búsquedas se cachean un tiempo corto. Sin conexión, la vista lo dice y el catálogo local funciona igual; una fuente que falla no rompe las demás.

### Fuera
- **Publicar** servidores en los registros, valorarlos o comentarlos. Solo se explora e instala.
- Registros de pago o que exijan cuenta, salvo un *token* opcional de GitHub o de la fuente para no chocar con su límite de peticiones.
- Instalar automáticamente los requisitos de un servidor (Node, Python, Docker). La ficha y la prueba de conexión dicen qué falta; la instalación de requisitos llega con la fase 22.
- Ejecutar los servidores en contenedores o *sandbox*.
- Que los agentes creen, editen o propongan conexiones.
- Usar los recursos y prompts MCP desde la app (solo se listan en la prueba).
- Estadísticas de uso con filtros, gráficos y CSV como las de la fase 17.
- Conexiones para Codex y OpenCode: llegan con sus adapters en la fase 22, que deberá cubrirlas.
- El Arquitecto asignando conexiones a un agente nuevo (fase 19).
- Modo servidor y credenciales compartidas entre usuarios (fase 24).

## Historias de usuario
- Como usuario, quiero dar de alta el MCP de GitHub una vez, con mi *token*, y que lo usen los agentes de mis proyectos, sin editar a mano la configuración de cada CLI.
- Como usuario, quiero conectar Notion o Linear con mi cuenta pulsando un botón, sin buscar *tokens*.
- Como usuario, quiero conectar la base de datos de un proyecto solo a los agentes de ese proyecto, y quitársela a un agente concreto o a una etapa (p. ej. que QA no escriba en ella).
- Como usuario, quiero reutilizar los MCP que ya tengo configurados en Claude Code, para no volver a escribirlos.
- Como usuario, quiero probar una conexión y ver sus herramientas antes de dársela a un agente, y saber con palabras por qué falla si falla.
- Como usuario, quiero que mis credenciales no queden en claro en la base de datos, en los logs ni en el repo.
- Como usuario, quiero elegir qué herramientas de una conexión puede usar un agente, para no darle las que borran o escriben si no hace falta.
- Como usuario, quiero buscar en los registros públicos los servidores MCP más usados, ver qué comando ejecutan y qué piden antes de instalarlos, y elegir a qué nivel los instalo.
- Como usuario, quiero ver en una ejecución qué herramientas externas llamó el agente.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | **Un agente usa en una tarea las herramientas de un MCP externo configurado desde la app**, sin tocar a mano la configuración del CLI: con un servidor `stdio` y con uno HTTP de prueba (CLI falso con cliente MCP real), y con `claude` y `agy` en la prueba manual (p. ej. el MCP de GitHub leyendo una *issue*) | test e2e + manual |
| CA2 | Se crea, edita, apaga, exporta y borra una conexión `stdio` y otra HTTP desde la UI, también pegando un bloque JSON `mcpServers`. Un nombre repetido, inválido o `agentic-os` no se guarda y el error se explica con palabras | tests de API + UI |
| CA3 | Los secretos no aparecen en la base de datos, en las respuestas de la API, en el log ni en el terminal de la ejecución, ni en la exportación; sí llegan al servidor MCP, que los usa | tests |
| CA4 | La prueba de conexión lista las herramientas de un servidor de prueba con su esquema, y da un error con palabras para: comando inexistente, proceso que se cae, *timeout*, 401 y URL inaccesible | tests |
| CA5 | Una ejecución recibe solo las conexiones activas de su nivel general, su proyecto y su agente, menos las que su agente haya quitado; los subagentes reciben las de su agente y las ejecuciones *headless* internas ninguna | tests |
| CA6 | Una conexión quitada en una etapa (o una rama) no llega a las ejecuciones de esa etapa aunque el agente o el proyecto la tengan, y sí a las demás | tests |
| CA7 | Las herramientas no permitidas de una conexión no se pueden llamar en la ejecución, y en *Restringido* las no preaprobadas piden permiso | tests + manual |
| CA8 | **OAuth**: con un servidor de autorización de prueba, «Conectar» completa el flujo (con registro dinámico y con *client id* pegado), guarda los *tokens* en el almacén del sistema, la ejecución recibe la cabecera, un *token* a punto de caducar se renueva antes de lanzarla y una renovación fallida deja la conexión en «Hay que volver a conectar» con aviso en la Inbox. Desconectar borra los *tokens*. Con un servicio real (p. ej. Notion o Linear) en la prueba manual | tests + manual |
| CA9 | Se importan las conexiones de `~/.claude.json` y de un `.mcp.json` de proyecto; los secretos van al almacén del sistema y el original no cambia (mismo hash) | tests |
| CA10 | La configuración del usuario no cambia: `~/.claude`, `~/.claude.json` y la configuración de `agy` están igual antes y después de una ejecución con conexiones (snapshots, como en el spike de la fase 01) | test + manual |
| CA11 | Al terminar o cancelar una ejecución con un servidor `stdio`, no queda ningún proceso suyo vivo | test |
| CA12 | Una conexión que no arranca no tumba la ejecución: el agente sigue con las demás y la ejecución muestra el aviso | test |
| CA13 | El registro de la ejecución dice qué conexiones recibió y qué herramientas externas llamó el agente, y la tarjeta de la conexión muestra su uso | tests + UI |
| CA14 | El explorador busca en las fuentes activas, filtra por fuente y transporte y lista por defecto los más usados. La ficha muestra el comando exacto, los requisitos (marcando los que faltan), las variables y secretos y la procedencia; instalar crea la conexión al nivel elegido, fijada a su versión y con la procedencia guardada | tests con las fuentes simuladas + manual con las reales |
| CA15 | Cuando la fuente publica una versión nueva, la app la avisa y enseña qué cambia; no actualiza sin confirmación. Sin conexión, el explorador lo dice y el catálogo funciona igual; una fuente que falla no rompe las demás | tests |
| CA16 | Con el binario empaquetado funciona el flujo completo: instalar un servidor desde el explorador (o una plantilla) → probarlo → asignarlo a un agente → ejecución que lo usa | e2e empaquetado |

## Prerrequisitos
- **Fase 17 cerrada** (hecho, `v1.9`).
- Lo reutilizado: adapters y aislamiento de ADR 0004, procesos de las ejecuciones de ADR 0007, credenciales de ADR 0018, niveles y explorador de las fases 14 y 17, lectura de transcripts de la fase 07.

## Riesgos y preguntas abiertas
- **`agy` y el filtrado de herramientas (spike, bloque 0).** Hay que comprobar en Windows si el `mcp_config.json` del plugin admite `stdio`, `env`, cabeceras y referencias `${VAR}`, y si `agy` permite filtrar herramientas por servidor; y en Claude, si `--allowedTools`/`--disallowedTools` con `mcp__<servidor>__<herramienta>` basta y si `${VAR}` en `mcp.json` se expande desde el entorno del proceso. Lo que no se admita va por la pasarela de respaldo.
- **OAuth (spike).** Comprobar el flujo con al menos un servidor remoto real (registro dinámico, puerto de retorno en `127.0.0.1`, renovación) y cómo se comporta con varias cuentas del mismo servicio.
- **APIs de los registros (spike).** Comprobar qué ofrece cada fuente (API pública, límites, si da instalaciones o estrellas, versiones, licencia, cómo se ejecuta cada servidor) y si sus condiciones permiten usarla desde una app. Una fuente sin API estable se sustituye por otra o se deja fuera.
- **Coste en contexto.** Cada servidor añade las descripciones de sus herramientas al contexto (algunos, decenas). Mitigación: herramientas permitidas por conexión y un aviso en la pestaña del agente con el número total de herramientas y una estimación de tokens.
- **Seguridad.** Un servidor `stdio` es código que se ejecuta con los permisos del usuario, y uno remoto recibe lo que el agente le mande (riesgo de inyección de *prompts* y fuga de datos). El riesgo crece con los registros públicos. Mitigación: nada se instala sin confirmación y sin ver el comando, versiones fijadas, aviso al crear o importar una conexión `stdio`, distinción entre oficiales y terceros, herramientas permitidas y preaprobación explícita en *Restringido* y *Preguntar*.
- **Requisitos de los servidores** (Node para `npx`, Python para `uvx`, Docker). La ficha y la prueba de conexión los detectan y lo dicen; la app no los instala en esta fase.
- **Servidores `stdio` lentos al arrancar** (`npx -y` descarga el paquete la primera vez). En `agy` hay que esperar a que conecten antes de escribir el prompt (ADR 0004). El spike mide los tiempos y el plan fija un *timeout*; la prueba de conexión sirve también para dejar el paquete descargado.

## Decisiones del usuario sobre el borrador (2026-10-24)
1. **Secretos**: en el almacén del sistema con `keyring` (se amplía ADR 0018).
2. **OAuth**: incluido; la app hace el flujo y guarda y renueva los *tokens*.
3. **Inyección**: directa en los dos CLIs; la pasarela en el backend solo para lo que el spike demuestre que un CLI no admite.
4. **Etapas**: se puede quitar una conexión en una etapa o rama, sin modos de autoselección.
5. **Explorador**: se añade un explorador de los registros públicos de servidores MCP, como el de skills (apartado G).

## Cambios tras la aprobación (2026-10-24)
Tras los spikes (bloque 0), aprobado por el usuario:
- **Explorador (apartado G)**: las fuentes son el **registro oficial de MCP** y **Smithery**, más la instalación desde un paquete npm o PyPI o un repositorio de GitHub. **Glama** (exige clave de API y atribución) y **PulseMCP** (retiró su API anterior y la nueva exige clave) quedan fuera de la fase. «Más usados» sale del `useCount` de Smithery y de las descargas semanales de npm.
- **Conexiones SSE en `agy`**: `agy` no admite SSE; la conexión se omite en esa ejecución con un aviso.
- **Pasarela de respaldo (apartado E)**: no hace falta, los dos CLIs admiten la inyección directa y el filtrado de herramientas.
