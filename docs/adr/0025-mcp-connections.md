# ADR 0025: Conexiones MCP con secretos en el almacén del sistema, inyección directa y registros públicos

- **Estado**: aceptado
- **Fecha**: 2026-10-25
- **Contexto de decisión**: fase 18 ([spec](../phases/18-conexiones-mcp/spec.md) · [plan](../phases/18-conexiones-mcp/plan.md) · [evidencias](../phases/18-conexiones-mcp/evidencias/s1-s6-conexiones.md))

## Contexto
Los agentes tienen que usar servidores MCP externos (GitHub, bases de datos, navegador…) configurados desde la app, sin que la persona toque a mano la configuración de cada CLI y sin que la app cambie la configuración del usuario (ADR 0004). Esos servidores necesitan secretos (tokens, contraseñas, OAuth), y el ADR 0018 decía que la app no guarda secretos propios.

## Decisión
1. **Secretos en el almacén de credenciales del sistema** (`keyring`; servicio `agentic-os`, nombre `mcp:<conexión>:<clave>`, troceados en piezas de 1000 caracteres por el límite de Windows).
   - En la base de datos solo hay marcadores `${secret:CLAVE}` / `${env:NOMBRE}`.
   - La API nunca devuelve un valor, solo si está puesto.
   - Un `Redactor` tapa (`•••`) los valores en el terminal, el log y los visores.
2. **Inyección directa, sin pasarela**. La app escribe la configuración que cada CLI ya sabe leer, solo para esa ejecución:
   - Claude: `<ejecución>/mcp.json` con referencias `${AOS_MCP_<n>_<CLAVE>}` y variables de entorno en el proceso;
   - `agy`: el `mcp_config.json` del plugin del espacio de trabajo, con los valores (no expande variables) y el plugin se retira al terminar. Las conexiones SSE se omiten con aviso.
3. **Herramientas filtradas por la app**: `--disallowedTools` en Claude (vale en todos los modos) y `enabledTools` / `disabledTools` en `agy`. Solo las herramientas marcadas como pre-aprobadas no piden permiso en *Restringido*.
4. **Niveles y exclusiones**: se reutilizan los de Conocimiento (general · proyecto · agente); un agente o una etapa del pipeline pueden quitar una conexión (sin modos automáticos).
5. **OAuth** con el cliente del SDK de MCP: receptor en `127.0.0.1` (puerto fijo configurable, por defecto 53682), registro dinámico o *client id* pegado, *tokens* en el almacén del sistema, renovación en segundo plano y antes de cada lanzamiento. Si falla, la conexión queda en «Hay que volver a conectar» y avisa en la Inbox.
6. **Registros públicos** detrás de un protocolo: el oficial de MCP, Smithery y paquetes (npm, PyPI, GitHub). Glama y PulseMCP quedan fuera porque exigen clave de API. Instalar no ejecuta nada y fija la versión exacta (`npx -y paquete@x`, `uvx paquete==x`); las actualizaciones se enseñan y nunca se aplican solas.
7. **Registro de uso** con los *hooks* de herramientas de cada CLI (`mcp__*` en Claude, `call_mcp_tool` en `agy`): qué conexiones recibió la ejecución y qué herramientas llamó.

## Alternativas descartadas
- **Pasarela MCP propia** que hable con los servidores en nombre del CLI: añade un salto y un punto de fallo, y los dos CLIs ya admiten servidores propios en su configuración.
- **Secretos cifrados en la base de datos**: obliga a guardar una clave en algún sitio; el almacén del sistema ya lo resuelve.
- **Modos automáticos de selección** de conexiones: tocan herramientas con efectos fuera del equipo; se prefiere que la persona decida y pueda quitar.

## Consecuencias
- **Límite conocido**: el agente puede leer las variables de entorno de su proceso. Un servidor `stdio` hereda el entorno del CLI y, en `agy`, los secretos de `env` y `headers` están en el `mcp_config.json` del plugin mientras dura la ejecución. Es inevitable si el CLI arranca el servidor; se avisa al crear una conexión.
- **Herramientas nuevas de un servidor**: en Claude, «solo estas herramientas» se aplica quitando las que se vieron en la última prueba (`--disallowedTools`); si el servidor añade después una, el CLI la ve hasta que se vuelva a probar la conexión. En `agy` sí es una lista de permitidas (`enabledTools`). Quien quiera cerrarlo del todo debe fijar la versión del servidor, que es lo que hace la instalación desde el explorador.
- El directorio de trabajo (`cwd`) de un servidor `stdio` no se inyecta: ninguno de los dos CLIs lo admite.
- El estado «falló» solo sale de llamadas reales; no hay comprobación previa al lanzar.
- La interfaz consulta cada segundo las pruebas y los inicios de sesión (sin eventos en vivo).
- El ejecutable empaquetado incluye `mcp.client` y `keyring`.
