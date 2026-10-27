# Fase 18: Conexiones MCP · Validación

## Tests automáticos
```
Backend  (uv run pytest, suite completa)                  en verde (ver «Estado final»)
Backend  (test_connections_*, migración 0020)             en verde; incluye e2e con CLI falso + servidores MCP reales
Backend  (test_connections_e2e, sidecar empaquetado)      8 passed con AGENTIC_OS_E2E_BINARY (CA16)
Frontend (vitest run)                                     60 files · 552 tests passed (32 nuevos de conexiones)
Frontend (npm run build)                                  correcto
Lint                                                      ruff (check y format), eslint y prettier limpios
Prueba real (backend/scripts/real_cli_connections.py)     claude y agy reales: OK
```
- **Sidecar**: 163,5 MB (162,8 MB en la fase 17). Se añadieron `mcp.client` y `keyring` a `scripts/build-backend.ps1`; sin ellos el binario no probaba ni conectaba servidores.
- **Tests nuevos (backend)**: `test_migration_0020`, `test_connections_secrets`, `_library`, `_import`, `_probe`, `_resolve`, `_adapters`, `_oauth`, `_usage`, `_registries` (fuentes simuladas), `_e2e` y `_review` (regresiones de la revisión). Servidores de prueba en `tests/fixtures/mcp_servers/` (`stdio`, HTTP y servidor de autorización OAuth).
- **Tests nuevos (frontend)**: `connections.test`, `connections-use.test` y `connections-explore.test`.

### Estado final (2026-10-25)
- Suite completa del backend (1481 passed, 2 skipped, 1 h 6 min) y del frontend (552) en verde tras resolver la revisión de código.
- **Almacén de credenciales**: los tests usan un almacén en memoria; el e2e con el binario empaquetado escribe en el real y no dejó ninguna entrada (`cmdkey /list`).

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Un agente usa las herramientas de un MCP externo configurado desde la app | ✅ automático · ✅ `claude` real · ✅ `agy` real | `test_connections_e2e` (stdio + HTTP, ambos CLIs falsos). **Reales**: `real_cli_connections.py` con un servidor `stdio` propio; ambos CLIs llaman a `read_note` y `show_env`, las llamadas quedan registradas y la conexión pasa a «conectada». *No* se probó con el MCP de GitHub real (necesita cuenta) |
| CA2 | Crear, editar, apagar, exportar y borrar (formulario y JSON pegado); errores en palabras | ✅ | `test_connections_library`, `_import`, `connections.test` |
| CA3 | Los secretos no están en la base de datos, API, log, terminal ni exportación; sí llegan al servidor | ✅ | `test_connections_secrets`, `test_connections_e2e` (log y ficheros de la ejecución), y la prueba real (sin el secreto en el log ni en los ficheros) |
| CA4 | La prueba lista herramientas con su esquema y explica: comando inexistente, caída, *timeout*, 401, URL inaccesible | ✅ | `test_connections_probe` |
| CA5 | Una ejecución recibe solo sus conexiones por nivel, menos las quitadas; subagentes sí, *headless* ninguna | ✅ | `test_connections_resolve`, `test_connections_adapters` |
| CA6 | Quitar en una etapa (o rama) solo afecta a esa etapa | ✅ | `test_connections_resolve`, `test_connections_e2e::test_a_connection_taken_away_from_the_stage_is_not_given`, `connections-use.test` |
| CA7 | Las herramientas no permitidas no se pueden llamar; en *Restringido* las no pre-aprobadas piden permiso | ✅ automático · ✅ `claude` real | `test_connections_e2e::test_a_tool_the_person_did_not_allow_is_not_there`. **Real**: en *Restringido*, Claude preguntó por `read_note` de una conexión nueva y dejó de preguntar al pre-aprobarla |
| CA8 | OAuth: flujo con registro dinámico y con *client id* pegado, *tokens* en el almacén, renovación, fallo → «volver a conectar» + Inbox, desconectar | ✅ automático · ⚠️ servicio real **no probado** | `test_connections_oauth` (servidor de autorización de prueba) y `test_connections_e2e::test_a_run_reaches_an_oauth_server_with_the_stored_token`. **Falta** la prueba con Notion o Linear, que necesita la cuenta y el navegador de la persona |
| CA9 | Importar de `~/.claude.json` y de `.mcp.json`; secretos al almacén; el original no cambia | ✅ | `test_connections_import` (*hash* del original) |
| CA10 | La configuración del usuario no cambia | ✅ automático · ✅ manual | `test_connections_adapters` y la prueba real (`~/.claude.json` → `mcpServers`, `~/.claude/settings.json` y la de `agy` iguales; el plugin de `agy` se retira) |
| CA11 | Al terminar o cancelar no queda ningún proceso del servidor `stdio` | ✅ | `test_connections_e2e::test_no_server_process_outlives_the_run` |
| CA12 | Una conexión que no arranca no tumba la ejecución | ✅ | `test_connections_e2e::test_a_connection_that_cannot_be_given_is_skipped_and_the_run_goes_on` y, tras la revisión, un fallo del almacén de credenciales también la omite |
| CA13 | El registro dice qué conexiones recibió y qué herramientas llamó; la tarjeta muestra su uso | ✅ | `test_connections_usage`, `connections-use.test`; en la prueba real: `read_note` y `show_env` con su duración |
| CA14 | El explorador busca, filtra y lista los más usados; la ficha enseña comando exacto, requisitos, campos y procedencia; instalar crea la conexión fijada | ✅ fuentes simuladas · ⚠️ reales sin repasar a mano | `test_connections_registries`, `connections-explore.test`; `evidencias/s1-s6-conexiones.md` (S4 con las fuentes reales) |
| CA15 | Versiones nuevas avisadas con su diferencia y sin aplicar solas; sin conexión el catálogo sigue; una fuente caída no rompe las demás | ✅ | `test_connections_registries`, `connections-explore.test` |
| CA16 | Con el binario empaquetado funciona el flujo completo | ✅ (instalar desde una plantilla → probar → asignar → ejecutar) | `test_connections_e2e` con `AGENTIC_OS_E2E_BINARY`: 8 passed. El flujo desde el explorador con las fuentes reales no se repitió en el empaquetado |

## Code review
Revisión `/code-review` (nivel alto) sobre la rama: 9 hallazgos.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Una renovación OAuth que falla por red o por un 5xx marcaba «volver a conectar» | Alta | Corregido: solo un inicio de sesión perdido marca la conexión; una caída de red la omite en esa ejecución y se reintenta |
| Un fallo del almacén de credenciales al pedir el *token* tumbaba el lanzamiento | Alta | Corregido: la conexión se omite con el motivo (`runtime.py`) |
| `library.create` hacía `rollback` de toda la sesión al fallar un secreto (perdía las conexiones anteriores de una importación) | Media | Corregido: solo se deshace la conexión que falló |
| Con el almacén de credenciales no disponible, el catálogo entero daba 503 | Media | Corregido: `secrets.status` devuelve «sin poner» y el catálogo se lista |
| La página del retorno de OAuth ponía `error_description` sin escapar (XSS en el origen local) | Media | Corregido con `html.escape`. El parámetro `state` lo valida el cliente del SDK |
| El `cwd` de un servidor `stdio` se usaba en la prueba pero ninguno de los CLIs lo admite | Media | Corregido: la prueba ya no lo usa, para que dé el mismo resultado que la ejecución; queda documentado |
| La ficha no enseñaba las opciones de `docker run` ni los argumentos fijos del registro | Alta | Corregido: el comando mostrado es el que se ejecuta (`command_line`) |
| En Claude, «solo estas herramientas» solo quita las vistas en la última prueba | Media | Justificado: el CLI no tiene lista de permitidas por servidor; se documenta en el ADR 0025 (en `agy` sí es lista de permitidas) y la instalación fija la versión |
| `state = "done"` se publicaba antes de guardar el resultado de la prueba | Baja | Corregido: se guarda y luego se avisa |
| Reconectar y abandonar borraba los *tokens* que funcionaban | Media | Corregido: se devuelven los anteriores si el inicio de sesión no termina |

## Retro
- **Cambios respecto a la spec**: Glama y PulseMCP fuera de la fase (ambos exigen clave de API); las conexiones SSE se omiten en `agy` con aviso (no las admite); sin pasarela MCP (la inyección directa funcionó en los dos CLIs); `cwd` de los servidores `stdio` no se inyecta.
- **Hallazgos de la prueba real** que los tests automáticos no daban: los diálogos de confianza de la carpeta y del modo sin permisos de Claude, y que en *Restringido* una conexión nueva pregunta por cada herramienta hasta que se pre-aprueba.
- **Lecciones**: `uvicorn.Config(log_level=…)` cambia el nivel de logging global (usar `log_config=None`); invalidar un prefijo de consultas dentro de su propia función de consulta provoca un bucle (se hace en un `useEffect`); el SDK de MCP oculta el estado HTTP en un error genérico (un *hook* de respuesta lo recoge).
- **Pendiente para fases futuras**: prueba de OAuth con un servicio real; eventos en vivo para la prueba y el inicio de sesión (hoy la UI consulta cada segundo); comprobación previa para el estado «falló»; test inestable de la fase 14 (`test_knowledge_*`, orden de filas) ya anotado.
- **Impacto en fases futuras**: Codex y OpenCode (fase 22) tendrán que implementar su propia inyección en `adapters/` con el mismo contrato (`RunConnections`); el ADR 0018 queda ampliado («la app no guarda secretos en sus ficheros»).

## Cierre
- [x] OK del usuario («cierra la fase», 2026-10-25)
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v1.10`
- [x] `docs/roadmap.md` actualizado
