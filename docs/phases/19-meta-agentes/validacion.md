# Fase 19: Meta-agentes · Validación

> **Estado: cerrada (`v1.11`) con el OK del usuario, que aplazó las suites completas y la prueba manual.** Falta lanzar las suites completas (backend y frontend), la prueba manual con `claude` real y el OK del usuario. Lo marcado ⏳ depende de eso.

## Tests automáticos
```
Backend  (tests de la fase: architect_*, proposals*, propose_agent, agent_io, phase19_review, migración 0021)   en verde
Backend  (test_architect_e2e, test_architect_team_e2e) con el CLI falso                                          en verde
Backend  (los mismos e2e) con el sidecar empaquetado reconstruido (AGENTIC_OS_E2E_BINARY)                        en verde
Frontend (vitest: pages/architect, components/proposals, inbox, home, editor de pipeline)                        68 passed
Typecheck, ESLint, Prettier, ruff (check y format)                                                               limpios
Suite completa del backend                                                                                       ⏳ pendiente (se lanza al cerrar)
Suite completa del frontend                                                                                      ⏳ pendiente (se lanza al cerrar)
```
- **Tests nuevos (backend)**: `test_migration_0021`, `test_architect_sheet`, `test_architect_session` (CLI falso en ConPTY, `claude` y `agy`), `test_architect_api`, `test_proposals`, `test_propose_agent`, `test_proposals_team`, `test_agent_io` (exportar, plantillas e importar), `test_architect_e2e`, `test_architect_team_e2e`, `test_phase19_review`.
- **Tests nuevos (frontend)**: `architect.test`, `architect-team.test`, `changes.test`, `propose-agent.test`.
- Las pruebas del sidecar (`scripts/test-packaged.ps1`) incluyen ya los dos e2e del Arquitecto.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Un «Redactor» sale de una conversación y ejecuta una tarea | ✅ CLI falso · ⏳ `claude` real | `test_architect_e2e` (conversación → ficha → borrador → aprobar → tarea hecha) |
| CA2 | Respuesta por bloques y ficha en vivo; un campo editado a mano no lo cambia el Arquitecto | ✅ | `test_architect_session` (respuesta del transcript, campo fijado rechazado), `architect.test` |
| CA3 | La ficha solo usa CLIs, cuentas, modelos, skills, documentos y conexiones que existen | ✅ | `test_architect_sheet`, `test_propose_agent` (referencia inventada rechazada) |
| CA4 | El Arquitecto no cambia nada fuera de su ficha; los *tokens* de agente y de Arquitecto no abren el servidor del otro | ✅ | `test_architect_session::test_tokens_only_open_their_own_server`, guardián de `agy` |
| CA5 | Un borrador no recibe tareas; aprobar lo activa con sus skills, rechazar lo archiva o borra; avisa en la Inbox | ✅ | `test_proposals`, `test_architect_api`, `architect.test` |
| CA6 | Una conversación se cierra y se retoma con su historial; borrador y conversación enlazados | ✅ | `test_architect_session` (dormir y retomar, reiniciar), `test_architect_api`, `architect.test` |
| CA7 | Cada conversación es una ejecución `architect` con consumo y límite diario | ✅ | `test_architect_session` (ejecución `architect`, límite alcanzado y cuenta sin sesión sin escribir en el CLI) |
| CA8 | Guardar como plantilla, crear desde ella con otra cuenta; las fijas no se tocan | ✅ | `test_agent_io::test_a_template_creates_the_agent_again_with_another_account`, `…renamed_duplicated_and_deleted…` |
| CA9 | Exportar sin secretos; importar en base limpia con faltantes omitidos | ✅ | `test_agent_io` (exportación, importación en otra base), `test_phase19_review` (ficheros locales y ficheros mal formados) |
| CA10 | Dictado en el composer | ✅ | `architect.test` |
| CA11 | Con el binario empaquetado funciona el flujo | ✅ | `test_architect_e2e` y `test_architect_team_e2e` con `AGENTIC_OS_E2E_BINARY` |
| CA12 | Mejorar un agente activo: cambios campo a campo, aplicación parcial, conflictos, ejecuciones intactas, Historial | ✅ | `test_proposals`, `changes.test` |
| CA13 | `propose_agent`: con permiso crea el borrador con origen y motivo; sin él no existe; una por ejecución; ficha inválida rechazada | ✅ | `test_propose_agent` (CLI falso), `propose-agent.test` |
| CA14 | Skills nuevas del Arquitecto: propuestas, aprobadas con el agente (salvo desmarcadas) y descartadas al rechazar | ✅ | `test_proposals` |
| CA15 | Equipo completo: «Aprobar todo» en una operación y una tarea recorre el pipeline | ✅ CLI falso · ⏳ agentes reales | `test_architect_team_e2e`, `test_proposals_team`, `architect-team.test` |
| CA16 | El pipeline propuesto pasa la validación del editor; un agente desmarcado usado por una etapa bloquea; si falla a medias no queda nada | ✅ | `test_proposals_team` |
| CA17 | Mejorar un pipeline o un equipo existente: diff de etapas y ramas, tareas en curso conservadas, conflicto si cambió | ✅ | `test_proposals_team`, `test_phase19_review` (ajustes del pipeline conservados, miembros quitados del equipo) |

## Code review
Revisión `/code-review` de alto nivel sobre el diff de la fase contra `main`: 9 hallazgos, todos resueltos con test (`test_phase19_review`).

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Borrar a mano un borrador de una propuesta de equipo rechazaba toda la propuesta y borraba los demás borradores | Alta | Corregido: devuelve 409 `draft_in_team_proposal`; se rechaza la propuesta o se deja fuera al aprobar |
| `pipeline_write` perdía el nombre, el decisor de las bifurcaciones y el límite de rechazos al aprobar una propuesta de pipeline | Alta | Corregido: la ficha los conserva y `set_pipeline` ya no fuerza `max_rejections=3` |
| Los borradores archivados salían en Inicio y en Cuentas | Media | Corregido: ambos filtran `archived_at` |
| Importar un `.agent` leía rutas locales arbitrarias de `knowledge` | Alta (seguridad) | Corregido: un archivo importado no lee rutas (se listan como faltantes y se avisa); las plantillas del propio usuario sí las conservan |
| Mejorar un agente se bloqueaba por referencias antiguas que la mejora no toca (modelo que el CLI ya no lista…) | Media | Corregido: los problemas heredados sin cambio respecto a la base no bloquean |
| Una conversación propuesta no podía volver a proponer tras seguir hablando | Media | Corregido: la nueva propuesta sustituye a la anterior en todos los modos |
| Una mejora de equipo no sacaba del equipo a los miembros que el Arquitecto quitó | Media | Corregido: al aprobar salen del equipo |
| Dos conversaciones podían arrancar en la misma carpeta de trabajo; un fin de ejecución antiguo podía cerrar el `Live` del nuevo | Media | Corregido: las carpetas se reservan bajo el cerrojo y un fin de ejecución antiguo no toca al nuevo (sin test específico: depende de tiempos) |
| Tras perderse la sesión del CLI, cada mensaje repetía el mismo fallo | Media | Corregido: si el CLI se cierra antes de empezar el turno al retomar, se descarta la sesión, se avisa y el siguiente mensaje arranca una limpia (sin test específico) |

Además, el e2e de equipo destapó que las herramientas MCP del Arquitecto con un argumento `name` fallaban siempre (corregido en `4f3443e`).

## Retro
- **Cambios respecto a la spec**: el Arquitecto es un CLI interactivo por conversación y no una llamada *headless* por turno (spikes S1–S4, ADR 0026); los agentes nuevos de una propuesta de equipo son borradores hasta aprobar.
- **Impacto en fases futuras**: el modelo de propuestas (`Proposal`) y el formato `agentic-os.agent` v1 sirven de base para cualquier propuesta futura; un CLI vivo por conversación obliga a vigilar memoria y procesos.
- **Pendiente anotado (fuera de alcance)**: editar a mano el nombre y la descripción del equipo en la ficha de equipo (hoy solo los rellena el Arquitecto).

## Cierre
- [ ] Suites completas en verde (aplazado)
- [ ] Prueba manual con `claude` real (CA1, CA15) (aplazado)
- [x] OK del usuario (2026-10-27)
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v1.11`
- [x] `docs/roadmap.md` actualizado
