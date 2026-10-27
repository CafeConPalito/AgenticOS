# Fase 17: Skills · Validación

## Tests automáticos
```
Backend  (uv run pytest tests, suite completa)        ver «Estado final» abajo
Backend  (test_skills_*, 13 ficheros, 130 tests)        en verde
Backend  (test_skills_quality, e5 real)                 2 passed (con modelo ≥ 0,9 en las 3 primeras; sin modelo ≥ 0,9 en el mismo idioma)
Backend  (test_skills_e2e, CLI falso + MCP real)        2 passed, también con AGENTIC_OS_E2E_BINARY (sidecar empaquetado)
Backend  (test_knowledge_e2e + test_dictation_e2e)      6 passed con el sidecar empaquetado
Frontend (vitest run)                                   57 files · 520 tests passed (17 nuevos de skills)
Frontend (npm run build, tsc -b)                        correcto
Lint                                                    ruff, eslint, prettier y spikes limpios
```
- **Sidecar**: 162,84 MB (162,67 MB en la fase 16). `pyyaml` ya estaba dentro, como dependencia transitiva.
- **Tests nuevos (backend)**:
  - `test_migration_0019`, `test_skills_format`, `test_skills_library`, `test_skills_import`, `test_skills_selection`, `test_skills_tools`, `test_skills_native`, `test_skills_proposals`, `test_skills_registries` (fuentes simuladas con `httpx.MockTransport`), `test_skills_stats` (incluido el de rendimiento), `test_skills_quality` y `test_skills_e2e`;
  - ampliados: `test_adapters` (el *matcher* de Claude incluye `Skill`) y `test_runs` (un lanzamiento fallido no deja ficheros de skills).
- **Tests nuevos (frontend)**: `skills.test` (biblioteca, editor, historial, importar, modos, ejecución), `skill-proposal.test`, `registry-explorer.test` y `skill-stats.test`.

### Estado final (2026-10-24)
- Backend, suite completa: todo en verde salvo 2 tests de la fase 14 (`test_knowledge_docs::test_the_three_levels` y `test_knowledge_context::test_the_index_says_what_each_document_is_and_the_small_ones_come_whole`). Fallan solo con la suite entera, por el orden de filas creadas casi a la vez, y pasan al lanzarlos solos. No dependen de skills; se anota como test inestable para una fase futura.
- Frontend: 57 ficheros · 520 tests, `npm run build`, eslint y prettier en verde.
- Backend: ruff (`check` y `format`) limpio.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Crear, editar, apagar, exportar y borrar en cada nivel; errores en palabras | ✅ | `test_skills_library` (14), `test_skills_format` (24), `skills.test` |
| CA2 | Importar carpeta, `.zip` y `~/.claude/skills` eligiendo el nivel; el original no cambia | ✅ | `test_skills_import` (*hash* del original antes y después; `.zip` de macOS; rutas que se salen), `skills.test` («De mis CLIs» con nivel por fila) |
| CA3 | Sección «Skills» con visibles, precedencia, Siempre / Nunca y presupuesto | ✅ | `test_skills_selection` |
| CA4 | La etapa manda sobre el agente (también en una rama) | ✅ | `test_skills_selection::test_the_stage_wins_over_the_agent`, `test_modes_api_shows_what_a_run_gets` (las ramas son etapas: el mismo `stage_id`) |
| CA5 | ≥ 90 % en las 3 primeras con modelo; sin modelo, ≥ 90 % en el mismo idioma | ✅ | `test_skills_quality` con e5 real (20 skills, 40 tareas). S4c: e5 0,925–0,938, Gemma 1,000, bge-m3 0,958–0,975 (ver evidencias) |
| CA6 | La skill relevante se carga sola y el registro dice cuál y por qué vía | ✅ automático · ✅ `claude` real · ✅ `agy` real | `test_skills_e2e` (CLI falso con MCP real). **Claude Code real** (haiku, modo Restringido): primera candidata, cargada como **nativa** por el plugin, script ejecutado, `saludo.txt` correcto, 25 s. **`agy` real** (Autónomo): cargada nativa y con `use_skill`, script ejecutado, 82 s ([`real-cli-*.json`](evidencias/)) |
| CA7 | `read_skill_file` solo da ficheros de skills visibles, nunca fuera de la carpeta | ✅ | `test_skills_tools` (`..`, rutas absolutas, skill ajena o en Nunca) |
| CA8 | La configuración del usuario no cambia | ✅ automático · ✅ manual | `test_skills_native` (*snapshot* de un `~/.claude` y un `~/.gemini` falsos con los dos CLIs) y S1/S2 y prueba real (sin cambios en `~/.claude/settings.json`, `~/.claude/skills`, `installed_plugins.json` ni `~/.gemini/config`). Lo único que cambió fue la confianza de `agy` en la carpeta temporal de la prueba (comportamiento conocido del ADR 0004), que se quitó a mano |
| CA9 | `propose_skill` → Inbox, invisible hasta aprobar; aprobada editada y en otro nivel, con «Creada por agente» | ✅ | `test_skills_proposals`, `test_skills_e2e::test_import_run_propose_and_approve`, `skill-proposal.test` |
| CA10 | Límites, tamaño, parecida, rechazada, desactivadas, con motivo | ✅ | `test_skills_proposals` (incluida la versión pendiente igual) |
| CA11 | Una versión nueva no cambia la actual hasta aprobarla; diff antes | ✅ | `test_skills_proposals::test_a_new_version_changes_nothing_until_approved` |
| CA12 | Historial con autor y origen, diff entre dos cualesquiera, restaurar, versión por ejecución | ✅ | `test_skills_library`, `test_skills_registries` (autores registro/usuario/registro), `RunSkill.version_id` en `test_skills_e2e` |
| CA13 | No se aprueba sin abrir los *scripts* | ✅ | 409 `scripts_not_opened` en `test_skills_proposals`; «Aprobar» deshabilitado en `skill-proposal.test` |
| CA14 | Uso y última fecha en la tarjeta; «Autoseleccionada» en la ejecución | ✅ | `skills.test`, `test_skills_e2e` (`used == 1`) |
| CA15 | Flujo completo con el binario empaquetado | ✅ | `test_skills_e2e` con `AGENTIC_OS_E2E_BINARY` (importar → ejecución que carga → proponer → Inbox → aprobar → la siguiente la recibe) |
| CA16 | Explorador: más usadas, búsqueda, ficha con ejecutables y procedencia, instalar al nivel | ✅ simulado · ✅ fuentes reales (lectura) | `test_skills_registries`, `registry-explorer.test`; prueba contra skills.sh, `anthropics/skills`, SkillsMP, ClawHub, la clasificación y una URL de GitHub (bloque 6) |
| CA17 | Actualizaciones con diff, nunca solas, historial intacto | ✅ | `test_skills_registries::test_updates_are_offered_with_their_diff_and_keep_the_persons_edits` |
| CA18 | Sin abrir *scripts* no se instala; sin red lo dice; una fuente caída no rompe las demás | ✅ | `test_skills_registries`, `registry-explorer.test` |
| CA19 | Cifras exactas con filtros, agrupación, «nunca usadas» | ✅ | `test_skills_stats` (10 combinaciones de filtros, 8 agrupaciones, serie diaria, CSV) |
| CA20 | La vista ordena, filtra, agrupa, pinta, abre ejecuciones y exporta; < 1 s con 50 skills y 20 000 ejecuciones | ✅ | `skill-stats.test`; `test_skills_stats::test_fifty_skills_and_twenty_thousand_runs_answer_in_under_a_second` |
| CA21 | Las cifras sobreviven al borrado de agente, etapa, pipeline o cuenta | ✅ | `test_skills_stats::test_figures_survive_deleting_what_they_were_about` |

### Pendiente de comprobar a mano con la app instalada
- Importar con el diálogo de carpeta de Tauri y arrastrar y soltar (los tests usan la ruta escrita).
- Ver el explorador con los registros reales desde la ventana: la lectura contra las fuentes reales se probó desde el backend.
- Una propuesta de un agente real (`propose_skill`). Los agentes reales cargaron skills; la propuesta se probó con el CLI falso y el MCP real.

## Code review
`/code-review high` sobre la rama: 10 hallazgos, todos corregidos (`703883a`), cada uno con su test.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Revisar una propuesta de nivel proyecto o general enviaba también el agente y el backend la rechazaba | alta | Solo se envía el dueño del nivel elegido; test de regresión |
| Aprobar en otro nivel con el nombre ocupado daba un 500 (índice único) | alta | `check_name` antes de mover; 409 `name_taken`; test |
| Borrar una skill dejaba su propuesta pendiente en la Inbox para siempre | media | Los elementos se resuelven como «descartado»; test |
| El vector de la tarea se calculaba con la transacción del lanzamiento abierta | media | Se calcula antes de escribir la ejecución (`Ranker.for_query`) y el trabajador se calienta al arrancar |
| Una URL de GitHub con rama instalaba desde la rama por defecto | media | La rama viaja en la referencia (`…@rama`); test |
| Dos versiones nuevas idénticas pendientes se aceptaban | media | Se comparan con las versiones pendientes; test |
| Un error al registrar la carga nativa cortaba el resto del *hook* | media | Envuelto como el de los subagentes nativos |
| Las rutas de ficheros con `#` o `?` no se codificaban, y un *script* así no se podía «abrir» | media | `encodePath` por segmentos; test |
| Los `.zip` de macOS (`__MACOSX/`, `._*`) no se desenvolvían | baja | Se ignoran; test |
| Un lanzamiento fallido dejaba la carpeta de skills en disco | baja | `clean_run` en los dos caminos de fallo; test |

## Retro
- **Cambios respecto a la spec** (aprobados por el usuario):
  - estadísticas de uso (apartado E);
  - explorador de registros públicos;
  - historial completo;
  - modos por etapa;
  - una propuesta por ejecución;
  - skills del repositorio como parte del proyecto;
  - CA5 sin modelo medido en el mismo idioma.
- **Cambios de diseño por las pruebas**:
  - **S4b**: sin modelo, palabras recortadas a su raíz y umbral relativo;
  - **S4c**: con modelo, las skills se calculan como consulta y los umbrales se recalibraron, porque S4 medía en lotes y el producto calcula de uno en uno;
  - **S3**: la API documentada de skills.sh no vale desde una app; se usan las rutas de su CLI y la clasificación abierta.
- **Lo que fue bien**:
  - las pruebas con los CLIs reales confirmaron la vía nativa en los dos, sin tocar la configuración del usuario;
  - el test de calidad con el modelo real destapó el sesgo de idioma de e5 antes del cierre.
- **Lo que costó**:
  - los heredocs de bash se comen las barras invertidas (anotado en la memoria): las ediciones con `\` van por fichero;
  - `tsc --noEmit -p .` no comprueba nada en este repo; la comprobación de tipos buena es `tsc -b`, la del *build*.
- **Impacto en fases futuras**:
  - **Fase 22** (Codex y OpenCode): sus adapters deben pasar `skills_dir` a su mecanismo propio, si lo tienen, y registrar la carga nativa; la vía común ya funciona sin hacer nada.
  - **Fase 23** (instaladores): nada nuevo que firmar; los registros se consultan por HTTPS.
  - **Fase 24** (servidor): la serie diaria agrupa por el día local del backend, como el consumo.
  - **Fuera de la fase**: `SESSION_MARKERS` no incluye `CLAUDE_CODE_BRIDGE_SESSION_ID` (anotado en el plan).
- **Limpieza pendiente del usuario (opcional)**: la prueba real con Claude dejó en `~/.claude.json` la confianza en dos carpetas temporales (`aos-skills-real-*`). Son inofensivas; no se tocaron porque Claude Code reescribe ese fichero mientras está abierto.

## Cierre
- [x] OK del usuario (2026-10-24)
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v1.9`
- [x] `docs/roadmap.md` actualizado
