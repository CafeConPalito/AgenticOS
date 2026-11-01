# Fase 23: Inicio, CLIs y voz · Validación

> **Estado (2026-11-01)**: el usuario probó el instalador: terminal propio y dictado en vivo bien. Pidió llevar los accesos directos a la barra superior, junto al Inbox, y unir Contexto y Skills (hecho). Falta su OK para cerrar: merge, versión `0.9.3` y tag `v0.9.3`. CA7 queda cubierto por los tests (no hay una máquina sin los CLIs a mano).

## Tests automáticos
```
Frontend (npm run test:frontend): 81 ficheros, 809 tests en verde; tras el code-review, los
         ficheros de dictado y CLIs (67 tests) otra vez en verde.
Lint     (npm run lint): en verde.
Desktop  (cargo test): 19 en verde.
Backend  (uv run pytest, backend/.test-progress.log): la suite completa no cabía en memoria de una
         vez (16 GB de RAM y 1,2 GB de archivo de paginación: el sistema cortó dos intentos). Se
         pasó por partes: el primer cuarto (sesión del 31) y el resto en tres tandas (2026-11-01).
         - 16 tests de test_launcher.py, test_resume.py, test_clis.py y test_runs.py no
           arrancaban: aún sustituían `launcher.shutil.which`, que pasó a `cli_paths`. Corregidos
           (7368fb0) y en verde.
         - test_switching.py::test_alert_at_the_threshold_once_per_agent falló una vez (dos
           avisos en lugar de uno) y pasa 3 de 3 al repetirlo: dos comprobaciones de cuota en
           paralelo. Es código de la fase 10, que esta fase no toca: se anota para una fase futura.
         Todo lo demás, en verde.
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Accesos directos (cambiados en la validación: Conocimiento y Conexiones en la barra superior, junto al Inbox) | ✅ | `AppHeader.test.tsx`; el usuario pidió el cambio al probar el instalador |
| CA2 | Terminal propio con CLI, cuenta y carpeta | ✅ probado por el usuario en la app instalada (2026-11-01) | `test_terminals.py`, `TerminalDock.test.tsx` |
| CA3 | Varios terminales en pestañas | ✅ | `TerminalDock.test.tsx` |
| CA4 | Fuera del panel y de Ejecuciones; gasto en Consumo, no en el límite | ✅ | `test_terminals.py`, `TerminalDock.test.tsx` |
| CA5 | Iconos propios de los CLIs | ✅ | `cli-icon.test.tsx` |
| CA6 | «Añadir CLI» solo con CLIs que faltan | ✅ | `clis.test.tsx` |
| CA7 | Instalación desde la app | ⏳ falta la prueba en una máquina sin el CLI | `test_cli_install.py`, `test_cli_paths.py`, `clis.test.tsx` |
| CA8 | Dictado en vivo y «Probar micrófono» | ✅ probado por el usuario en la app instalada (2026-11-01) | `dictation-live.test.ts`, `dictation.test.tsx`, `dictation-settings.test.tsx`, `test_dictation_api.py`, `test_dictation_real.py` |
| CA9 | Suites, lint y `/code-review` | ✅ | arriba y en la tabla siguiente |

## Code review
`/code-review medium` sobre la rama frente a `main` (2026-11-01): 10 hallazgos, todos corregidos (`4ca7d4b`, `6a8539e`).

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Un terminal de agy reescribía el *plugin* de un agente agy que trabajaba en la misma carpeta | alta | El terminal reserva la carpeta como las ejecuciones de agy: un segundo agy ahí da 409; test |
| El dictado en vivo seguía grabando tras parar, hasta que se procesaba su trabajo | alta | La grabación termina al parar (`end`) y su audio se lee después; test |
| Un error de red en una conjetura dejaba el micrófono abierto | alta | Una conjetura fallida nunca rompe el dictado; test |
| `resetDictation` no soltaba los dictados en vivo en cola | media | También se paran |
| Si fallaba el último trozo, se borraba el texto ya fijado | media | Se queda lo fijado y solo se pierde el último trozo (`keep`); test |
| En vivo, «no se ha oído nada» no se avisaba (y podía copiar un texto vacío) | media | Se avisa y no se escribe nada; test |
| El silencio se volvía a enviar en cada turno | baja | Un trozo sin palabras se deja atrás; test |
| Un CLI que no arranca respondía 201 sin pestaña ni aviso | media | Error 500 `terminal_failed`; test |
| La construcción de los *hooks* del terminal duplicaba la de los agentes | baja | Funciones compartidas (`write_hook_settings`, `write_hooks`) |
| Al acabar una instalación se comprobaban los CLIs dos veces | baja | La interfaz lee lo que el backend ya comprobó |
