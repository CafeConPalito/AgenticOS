# Fase 10: Equipos y cuentas de CLI · Validación

> Estado: **en validación** (borrador: falta el `/code-review`, la prueba manual con una segunda cuenta real y el OK del usuario).

## Tests automáticos
```
backend (pytest):   suite completa en verde (≈ 380 tests), con nuevos
                    test_migration_0008 (2) · test_accounts (28) · test_accounts_api (11) ·
                    test_accounts_e2e (4, backend real + CLI falso en ConPTY) ·
                    test_agy_status (8) · test_usage_stats (+8, límites por cuenta) ·
                    test_trust (+1), test_adapters (+1)
                    Los 2 fallos preexistentes de test_usage_stats.py eran del test (fijaba el
                    día 2026-10-12 y los avisos llevan la hora real): corregidos.
frontend (vitest):  25 archivos · 214 tests en verde, con nuevos
                    clis.test.tsx (17) · agent-links.test.tsx (8) · accounts-surfaces.test.tsx (14) ·
                    home.test.tsx (28, +12)
lint:               npm run lint (ruff, eslint, prettier, tsc, cargo fmt, spikes) en verde
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Tras actualizar, cada CLI tiene su cuenta del sistema predeterminada y todo sigue funcionando | ✅ por tests; ⏳ con la BD real | `test_migration_0008.py` (BD v1.1 con límites, ejecuciones y avisos; subida y bajada) |
| CA2 | Añadir una segunda cuenta de Claude desde «CLIs y cuentas», con login en el terminal de la app | ✅ flujo completo con CLI falso; ⏳ login real | `test_accounts_e2e.py::test_logging_an_account_in_…`, `clis.test.tsx`; la carpeta aislada y `auth status` se comprobaron con el Claude real ([S1](evidencias/s1-s2-captura.md)). **Falta el login OAuth real con una segunda cuenta** |
| CA3 | Dos agentes de Claude con cuentas distintas ejecutan a la vez, cada uno con su cuenta (config, transcript y consumo) | ✅ con CLI falso; ⏳ con dos cuentas reales | `test_accounts_e2e.py::test_a_run_uses_its_accounts_folder_…`, `test_adapters.py`, `test_usage_reader`, `test_trust.py` |
| CA4 | Con una cuenta bloqueada el scheduler no lanza sus tareas y sí las de otra cuenta del mismo CLI; el aviso nombra la cuenta | ✅ | `test_usage_stats.py` (límite, «Cuota agotada», varias cuentas) |
| CA5 | Cuenta con sesión caída: aviso «Reconectar»; al reconectar desaparece y se reanudan sus tareas | ✅ con CLI falso; ⏳ cerrando una sesión real | `test_usage_stats.py`, `test_accounts_api.py`, `home.test.tsx`, `clis.test.tsx` |
| CA6 | La cuenta se ve en Ejecuciones, el detalle de tarea y la ejecución; el consumo se filtra por cuenta | ✅ | `accounts-surfaces.test.tsx`, `test_usage_stats.py`, `test_usage_api.py` |
| CA7 | `/clis`: CLIs, cuentas, plan, uso, agentes y sesiones; añadir, reconectar, predeterminada y quitar; `/ajustes#clis` redirige | ✅ | `clis.test.tsx`, `settings.test.tsx`; revisión visual con los CLIs reales |
| CA8 | Columna de resumen de Inicio: % más alto por CLI y cuentas desplegables | ✅ | `home.test.tsx`; revisión visual |
| CA9 | Crear, editar y borrar equipos; Inicio agrupa por equipo y «Sin equipo» | ✅ | `home.test.tsx`, `test_accounts_api.py` |
| CA10 | Equipo y cuenta en «Nuevo agente», la edición, «Configuración» y las migas; columna y filtro en Agentes | ✅ | `agent-links.test.tsx` |
| CA11 | agy: una sola cuenta (el login está en el almacén de credenciales) y la UI lo explica | ✅ | [S2](evidencias/s1-s2-captura.md), `clis.test.tsx` |
| CA12 | Lint, tipos y tests en verde; `/code-review` resuelto | ✅ salvo el review | arriba |
| CA13 | Claude: «Ventana de 5 h» y «Semanal» con el mismo % y reinicio que `/usage` | ✅ con captura real | [S1](evidencias/s1-s2-captura.md) (11 % / 20:40 y 75–76 % / sáb 17:00), `test_accounts.py` (fixture real) |
| CA14 | agy: sus buckets de `quota`, como `/usage` | ✅ con captura real | [S2/S3](evidencias/s1-s2-captura.md) (98,28 % y 97,56 % frente a 0,982825 y 0,9756), `test_agy_status.py` |
| CA15 | Una ventana ≥ 95 % avisa en «Te necesitan» y se resuelve sola al reiniciarse | ✅ | `home.test.tsx`, `accounts-surfaces.test.tsx` (`lib/quota`) |

## Code review
_Pendiente._

## Retro
- **Cambios respecto a la spec**: ver «Desarrollo: resultado del spike y desviaciones» en el [plan](plan.md). Lo más relevante: la cuota de agy es un interruptor explícito (ADR 0014) y los avisos de cuota se derivan en el cliente.
- **Impacto en fases futuras**:
  - Fase 11 (Conocimiento): sin impacto directo.
  - Fase 16 (Instaladores): el sidecar usa `collect_submodules('agentic_os')` y copia las migraciones, así que no hizo falta tocar el empaquetado; el login de una cuenta abre el navegador del sistema.
  - Fase 17 (Modo servidor): la carpeta de cada cuenta vive en la carpeta de datos del servidor y el login abre un navegador en la máquina donde corre el CLI, no en la del usuario: habrá que resolverlo ahí.
- **Pendiente anotado**:
  - Probar a mano el login real con una segunda cuenta (CA2, CA3, CA5).
  - La cuota solo llega mientras hay una sesión de la cuenta; sin sesión se muestra el último valor con su antigüedad.
  - Medición CA1 de la fase 09 sobre `main` (sigue pendiente).

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v1.2`
- [ ] `docs/roadmap.md` actualizado
