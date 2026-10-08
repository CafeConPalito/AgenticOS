# Fase 00: Fundaciones · Validación

- **Rama**: `phase/00-fundaciones`
- **Fecha**: 2026-10-08

## Tests automáticos
`scripts/check.ps1` (lint + todos los tests):

```
Paso                            Resultado
----                            ---------
Lint backend (ruff)             OK
Lint frontend (eslint+prettier) OK
Lint desktop (rustfmt)          OK
Tests backend (pytest)          OK   8 passed
Tests frontend (vitest)         OK   12 passed (4 files)
Tests desktop (cargo test)      OK   2 passed
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | `npm run dev` levanta el backend (`:8765`) y la UI (Vite), y la UI muestra "Backend conectado" | ✅ | Arrancado con `npm run dev`: `GET http://127.0.0.1:8765/api/health` → `{"status":"ok",…}` y Vite → `200` en `localhost:5173`. "Conectado · v0.1.0" visible (misma UI que en la captura de CA5). Tests de `BackendStatus.test.tsx` (conectado / conectando / desconectado + banner) |
| CA2 | `GET /api/health` → 200 con `status` y `version` | ✅ | `test_health.py` |
| CA3 | Barra lateral con 7 secciones, navegación y textos desde `es.json` | ✅ | `AppSidebar.test.tsx` (7 enlaces con textos de `es.json`, navegación, ítem activo, ruta desconocida → Dashboard). ESLint `i18next/no-literal-string` (texto JSX) en verde |
| CA4 | Tema claro/oscuro (navy por defecto), se recuerda; fuente Ubuntu en local | ✅ | `ThemeProvider.test.tsx` (navy por defecto, cambio a claro, persistencia, restauración). Fuentes con `@fontsource`, sin peticiones a Google Fonts. Comparada con la captura `01a` del diseño. El tema claro está cubierto por tests; falta la revisión visual |
| CA5 | `npm run dev:desktop` abre la ventana Tauri conectada | ✅ | [`evidencias/ca5-dev-desktop.png`](evidencias/ca5-dev-desktop.png): ventana «Agentic OS» con «Conectado · v0.1.0» |
| CA6 | `npm run build:desktop` → el ejecutable arranca el sidecar en un puerto libre, conecta, y lo para al cerrar sin huérfanos | ✅ | Instalador NSIS `Agentic OS_0.1.0_x64-setup.exe` (17,3 MB); sidecar de 14,4 MB, listo en 1,12 s. [`evidencias/ca6-release-sidecar.png`](evidencias/ca6-release-sidecar.png): «Conectado» con puerto dinámico (61868). Cierre normal → 0 procesos del backend en 1,6 s; Tauri matado a la fuerza → 0 en 1,9 s. Tests `test_main.py` (handshake, watchdog, pipes rotos) y `cargo test` (`parse_ready`) |
| CA7 | `check` ejecuta ruff, ESLint, Prettier, pytest y vitest en verde | ✅ | Salida de arriba; también incluye rustfmt y cargo test |
| CA8 | README con requisitos y comandos; roadmap actualizado | ✅ | [`README.md`](../../../README.md), [`roadmap.md`](../../roadmap.md) |

## Code review
`/code-review high` sobre `main...phase/00-fundaciones`:

| Hallazgo | Severidad | Resolución |
|---|---|---|
| _(pendiente del resultado)_ | | |

## Incidencias encontradas durante el desarrollo
- **Backend huérfano tras cerrar la app (corregido)**: con PyInstaller `--onefile`, el intérprete de Python es un nieto de Tauri. Al morir Tauri, los pipes de stdout/stderr se rompen y el watchdog fallaba al escribir un log *antes* de pedir el apagado, así que el proceso quedaba vivo. Corrección: primero se pide el apagado, el log va dentro de un `suppress` y, si el proceso sigue vivo tras 5 s de gracia, se fuerza `os._exit`. Test de regresión: `test_exits_when_parent_dies_and_its_pipes_are_closed`.
- **Configuración de pytest ignorada desde la raíz (corregido)**: `npm run test:backend` pasa ahora `backend` como ruta para que pytest lea `backend/pyproject.toml`.

## Retro
### Cambios respecto a la spec y al plan
- **ESLint 9** en lugar de 10: los plugins (`react-hooks`, `jsx-a11y`, `i18next`) todavía piden ESLint 9 como peer.
- **Regla i18n** en modo `jsx-text-only`: el modo `jsx-only` marcaba también props técnicas (`section="agents"`).
- **Sin permisos `shell:*` para la UI**: el plan preveía `shell:allow-spawn` limitado al sidecar, pero como el sidecar se lanza desde Rust no hace falta. Capability `core:default` únicamente (más seguro).
- **`externalBin` solo en release** (`tauri.release.conf.json`): Tauri exige que el binario exista al compilar, y así `dev:desktop` no depende de construir el sidecar.
- **Rust en el `check`**: se añadieron `rustfmt --check` y `cargo test`.
- **`logging.py` → `logging_setup.py`**, para no confundirlo con el módulo estándar.
- **`httpx` se mantiene** para el `TestClient`. Starlette recomienda `httpx2`, pero su instalación quedó bloqueada por la política de permisos de la sesión; se filtra el aviso de deprecación y queda pendiente de decisión del usuario.

### Impacto en fases futuras
- **Rutas del navegador en Tauri**: la navegación dentro de la app funciona. Falta comprobar a mano que recargar (F5) en una subruta como `/agentes` no da 404 en la build de release (Tauri debería devolver `index.html`). Si falla, se cambia a hash router.
- **Tamaño del bundle del frontend**: 590 kB, con aviso de Vite. Se resolverá con code-splitting por ruta cuando haya pantallas reales (fase 02 o siguientes).
- **Ventana de consola del sidecar**: no se ha visto ninguna durante las pruebas (tauri-plugin-shell lanza con `CREATE_NO_WINDOW`); conviene confirmarlo instalando el NSIS en la fase 08.
- **Antivirus y firma de código**: pendiente para la fase 08.

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v0.1`
- [ ] `docs/roadmap.md` actualizado
