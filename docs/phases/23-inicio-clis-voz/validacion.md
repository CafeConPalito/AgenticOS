# Fase 23: Inicio, CLIs y voz · Validación

> **Estado (2026-10-31, noche)**: desarrollo terminado y en commits en `phase/23-inicio-clis-voz`. Validación a medias.
>
> **Hecho**: frontend completo (81 ficheros, 809 tests), lint y `cargo test` (19), todo en verde. Los tests nuevos del backend y los de cada parte que se tocó, también en verde, incluido el dictado con el motor real.
>
> **En curso**: suite completa del backend en dos tandas (`backend/.test-progress.log`). Dos intentos anteriores se cortaron por falta de memoria del sistema (12 % y 52 %), sin fallos hasta ahí. Causa: 16 GB de RAM con un archivo de paginación de 1,2 GB (límite de memoria comprometida de 17,1 GB) y ~13 GB ya en uso con las apps de fondo. Se recomendó al usuario ampliar el archivo de paginación.
>
> **Falta, en orden**:
> 1. Resultado de la suite del backend; corregir lo que falle.
> 2. ~~`/code-review medium` de la rama y sus correcciones~~ ✅ (2026-11-01, 10 hallazgos corregidos).
> 3. Instalador en el escritorio (`npm run build:desktop`, sin nada más corriendo a la vez).
> 4. Prueba del usuario en la app instalada:
>    - terminal propio con una cuenta y una carpeta cualquiera (CA2);
>    - dictado en vivo y «Probar micrófono» (CA8);
>    - si puede, «Añadir CLI» en una cuenta de Windows sin el CLI (CA7).
> 5. Completar este documento (criterios con evidencias, code review, retro) y cerrar con el OK del usuario: merge, versión `0.9.3` y tag `v0.9.3`.

## Tests automáticos
```
Frontend (npm run test:frontend): 81 ficheros, 809 tests en verde.
Lint     (npm run lint): en verde.
Desktop  (cargo test): 19 en verde.
Backend  : pendiente de la suite completa (ver arriba).
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Seis accesos con emoji y *tooltip* | ✅ | `home.test.tsx` |
| CA2 | Terminal propio con CLI, cuenta y carpeta | ⏳ falta la prueba en la app | `test_terminals.py`, `TerminalDock.test.tsx` |
| CA3 | Varios terminales en pestañas | ✅ | `TerminalDock.test.tsx` |
| CA4 | Fuera del panel y de Ejecuciones; gasto en Consumo, no en el límite | ✅ | `test_terminals.py`, `TerminalDock.test.tsx` |
| CA5 | Iconos propios de los CLIs | ✅ | `cli-icon.test.tsx` |
| CA6 | «Añadir CLI» solo con CLIs que faltan | ✅ | `clis.test.tsx` |
| CA7 | Instalación desde la app | ⏳ falta la prueba en una máquina sin el CLI | `test_cli_install.py`, `test_cli_paths.py`, `clis.test.tsx` |
| CA8 | Dictado en vivo y «Probar micrófono» | ⏳ falta la prueba en la app | `dictation-live.test.ts`, `dictation.test.tsx`, `dictation-settings.test.tsx`, `test_dictation_api.py`, `test_dictation_real.py` |
| CA9 | Suites, lint y `/code-review` | ⏳ | arriba |

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
