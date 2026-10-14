# Fase 10: Equipos y cuentas de CLI Â· ValidaciÃ³n

> Estado: **en validaciÃ³n** (borrador: falta la prueba manual con una segunda cuenta real y el OK del usuario).

## Tests automÃ¡ticos
```
backend (pytest):   suite completa en verde (â‰ˆ 380 tests), con nuevos
                    test_migration_0008 (2) Â· test_accounts (28) Â· test_accounts_api (11) Â·
                    test_accounts_e2e (4, backend real + CLI falso en ConPTY) Â·
                    test_agy_status (8) Â· test_usage_stats (+8, lÃ­mites por cuenta) Â·
                    test_trust (+1), test_adapters (+1)
                    Los 2 fallos preexistentes de test_usage_stats.py eran del test (fijaba el
                    dÃ­a 2026-10-12 y los avisos llevan la hora real): corregidos.
frontend (vitest):  25 archivos Â· 214 tests en verde, con nuevos
                    clis.test.tsx (17) Â· agent-links.test.tsx (8) Â· accounts-surfaces.test.tsx (14) Â·
                    home.test.tsx (28, +12)
lint:               npm run lint (ruff, eslint, prettier, tsc, cargo fmt, spikes) en verde
```

## Criterios de aceptaciÃ³n
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Tras actualizar, cada CLI tiene su cuenta del sistema predeterminada y todo sigue funcionando | âœ… por tests; â³ con la BD real | `test_migration_0008.py` (BD v1.1 con lÃ­mites, ejecuciones y avisos; subida y bajada) |
| CA2 | AÃ±adir una segunda cuenta de Claude desde Â«CLIs y cuentasÂ», con login en el terminal de la app | âœ… flujo completo con CLI falso; â³ login real | `test_accounts_e2e.py::test_logging_an_account_in_â€¦`, `clis.test.tsx`; la carpeta aislada y `auth status` se comprobaron con el Claude real ([S1](evidencias/s1-s2-captura.md)). **Falta el login OAuth real con una segunda cuenta** |
| CA3 | Dos agentes de Claude con cuentas distintas ejecutan a la vez, cada uno con su cuenta (config, transcript y consumo) | âœ… con CLI falso; â³ con dos cuentas reales | `test_accounts_e2e.py::test_a_run_uses_its_accounts_folder_â€¦`, `test_adapters.py`, `test_usage_reader`, `test_trust.py` |
| CA4 | Con una cuenta bloqueada el scheduler no lanza sus tareas y sÃ­ las de otra cuenta del mismo CLI; el aviso nombra la cuenta | âœ… | `test_usage_stats.py` (lÃ­mite, Â«Cuota agotadaÂ», varias cuentas) |
| CA5 | Cuenta con sesiÃ³n caÃ­da: aviso Â«ReconectarÂ»; al reconectar desaparece y se reanudan sus tareas | âœ… con CLI falso; â³ cerrando una sesiÃ³n real | `test_usage_stats.py`, `test_accounts_api.py`, `home.test.tsx`, `clis.test.tsx` |
| CA6 | La cuenta se ve en Ejecuciones, el detalle de tarea y la ejecuciÃ³n; el consumo se filtra por cuenta | âœ… | `accounts-surfaces.test.tsx`, `test_usage_stats.py`, `test_usage_api.py` |
| CA7 | `/clis`: CLIs, cuentas, plan, uso, agentes y sesiones; aÃ±adir, reconectar, predeterminada y quitar; `/ajustes#clis` redirige | âœ… | `clis.test.tsx`, `settings.test.tsx`; revisiÃ³n visual con los CLIs reales |
| CA8 | Columna de resumen de Inicio: % mÃ¡s alto por CLI y cuentas desplegables | âœ… | `home.test.tsx`; revisiÃ³n visual |
| CA9 | Crear, editar y borrar equipos; Inicio agrupa por equipo y Â«Sin equipoÂ» | âœ… | `home.test.tsx`, `test_accounts_api.py` |
| CA10 | Equipo y cuenta en Â«Nuevo agenteÂ», la ediciÃ³n, Â«ConfiguraciÃ³nÂ» y las migas; columna y filtro en Agentes | âœ… | `agent-links.test.tsx` |
| CA11 | agy: una sola cuenta (el login estÃ¡ en el almacÃ©n de credenciales) y la UI lo explica | âœ… | [S2](evidencias/s1-s2-captura.md), `clis.test.tsx` |
| CA12 | Lint, tipos y tests en verde; `/code-review` resuelto | âœ… salvo el review | arriba |
| CA13 | Claude: Â«Ventana de 5 hÂ» y Â«SemanalÂ» con el mismo % y reinicio que `/usage` | âœ… con captura real | [S1](evidencias/s1-s2-captura.md) (11 % / 20:40 y 75â€“76 % / sÃ¡b 17:00), `test_accounts.py` (fixture real) |
| CA14 | agy: sus buckets de `quota`, como `/usage` | âœ… con captura real | [S2/S3](evidencias/s1-s2-captura.md) (98,28 % y 97,56 % frente a 0,982825 y 0,9756), `test_agy_status.py` |
| CA15 | Una ventana â‰¥ 95 % avisa en Â«Te necesitanÂ» y se resuelve sola al reiniciarse | âœ… | `home.test.tsx`, `accounts-surfaces.test.tsx` (`lib/quota`) |

## Code review
Siete hallazgos, todos corregidos con su test.

| Hallazgo | Severidad | ResoluciÃ³n |
|---|---|---|
| `blocked_by` se rellenaba en toda tarea en cola sin bloqueo (`None == None`) | media | corregido: solo si hay un motivo de la cuenta Â· `test_only_a_held_task_says_by_which_account` |
| En agy, cualquier fallo de `agy models` (sin red, un cuelgue) bloqueaba la cuenta como Â«sesiÃ³n cerradaÂ» | alta | corregido: solo es Â«cerradaÂ» si el CLI lo dice; si no, se conserva lo sabido Â· `test_probe_of_agy_lists_its_models_and_a_failure_is_not_a_logout` |
| Una comprobaciÃ³n que no puede responder (timeout, sin red) pasaba una cuenta de Â«cerradaÂ»/Â«okÂ» a Â«desconocidaÂ» (soltaba una cuenta cerrada o bloqueaba una buena) | alta | corregido: solo se actualiza la hora de la comprobaciÃ³n Â· `test_a_probe_that_cannot_tell_keeps_what_was_known` |
| El scheduler ejecutaba los CLIs (hasta 20â€“45 s por cuenta) en su propio hilo, con la sesiÃ³n de BD abierta | alta | corregido: las comprobaciones corren en un hilo aparte, sin bloquear el tick; un CLI no instalado ya no se reintenta en cada vuelta Â· `test_the_scheduler_asks_the_cli_again_off_its_own_thread` |
| El `exit` del login llegaba antes de comprobar la sesiÃ³n: la UI veÃ­a Â«sin sesiÃ³nÂ» y `logging_in` seguÃ­a activo durante la comprobaciÃ³n | media | corregido: se comprueba primero y se anuncia el fin despuÃ©s Â· `test_accounts_e2e.py` (estado `ok` justo al oÃ­r el `exit`) |
| Un lÃ­mite de agy menor que 1 se truncaba a 0 y bloqueaba la cuenta para siempre | alta | corregido: se redondea y se rechaza lo que da 0 (`invalid_limit`) Â· `test_the_daily_limit_has_one_rule`, `test_a_token_limit_that_rounds_to_zero_â€¦` |
| Dos endpoints fijaban el lÃ­mite con su propia copia de la regla (y con el mismo fallo) | baja | corregido: una sola funciÃ³n, `set_daily_limit` |
| Un fichero de confianza ilegible de una cuenta abortaba la limpieza de las demÃ¡s y se reintentaba para siempre | media | corregido: cada fichero de cuenta va por su cuenta, la principal ya no se deshace Â· `test_a_bad_account_file_does_not_hold_back_the_rest` |

AdemÃ¡s, al repasarlo saliÃ³ un test que dependÃ­a del reloj (los reinicios del fixture de agy son de la tarde de la captura y una ventana pasada se ve reiniciada): ahora fija los reinicios hacia delante.

## Retro
- **Cambios respecto a la spec**: ver Â«Desarrollo: resultado del spike y desviacionesÂ» en el [plan](plan.md). Lo mÃ¡s relevante: la cuota de agy es un interruptor explÃ­cito (ADR 0014) y los avisos de cuota se derivan en el cliente.
- **Impacto en fases futuras**:
  - Fase 11 (Conocimiento): sin impacto directo.
  - Fase 16 (Instaladores): el sidecar usa `collect_submodules('agentic_os')` y copia las migraciones, asÃ­ que no hizo falta tocar el empaquetado; el login de una cuenta abre el navegador del sistema.
  - Fase 17 (Modo servidor): la carpeta de cada cuenta vive en la carpeta de datos del servidor y el login abre un navegador en la mÃ¡quina donde corre el CLI, no en la del usuario: habrÃ¡ que resolverlo ahÃ­.
- **Pendiente anotado**:
  - Probar a mano el login real con una segunda cuenta (CA2, CA3, CA5).
  - La cuota solo llega mientras hay una sesiÃ³n de la cuenta; sin sesiÃ³n se muestra el Ãºltimo valor con su antigÃ¼edad.
  - MediciÃ³n CA1 de la fase 09 sobre `main` (sigue pendiente).

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v1.2`
- [ ] `docs/roadmap.md` actualizado
