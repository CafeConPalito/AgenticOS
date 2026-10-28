# Fase 20: Personalización y Acerca de · Validación

## Tests automáticos
```
Backend  (uv run pytest, suite completa, backend/.test-progress.log): 3 fallos, ninguno de esta fase
  - test_connections_adapters.py::test_without_connections_the_claude_flags_do_not_change   (falla igual en main)
  - test_connections_adapters.py::test_agy_gets_the_servers_in_its_plugin_with_the_values_in_clear (falla igual en main)
  - test_knowledge_docs.py::test_the_three_levels   (intermitente: falla bajo carga, pasa solo 3/3 y en main 3/3)
Frontend (vitest): 705 tests en verde; ESLint, tsc, Prettier y build sin errores
Desktop  : cargo test (10), cargo fmt --check, cargo check --release
e2e empaquetado (npm run test:packaged): 19 passed, 3 skipped
Tras el code-review: test_support.py, avatares/plantillas, vitest src/lib, cargo test y ruff en verde
```
Los dos fallos de `test_connections_adapters.py` (`--disallowedTools` / `disabledTools: propose_agent`) vienen de fases anteriores: se anotan para una fase futura, fuera del alcance de la spec.

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Pestañas como en la fase 09, menos ruido, Apariencia y Acerca de en Ajustes y paleta | ✅ | tests de componente; revisión con el usuario sobre capturas (plan, nota 8) |
| CA2 | Miga, Atrás/Adelante e Inbox en vivo | ✅ (manual en Tauri: S3 comprobado con el usuario) | `use-history-stack` y tests de cabecera |
| CA3 | `AgentAvatar` igual en todas las pantallas | ✅ | tests de `AgentAvatar`; `evidencias/avatars/` |
| CA4 | Foto >2048 px o formato no admitido rechazada; solo se guarda el recorte | ✅ (el recorte con una foto real, pendiente de la prueba manual) | tests de API y componente; `evidencias/s6-crop.txt`; tras el review, 413 por `Content-Length` y lectura de 1 MB de cabecera |
| CA5 | Exportar/importar conserva imagen y color | ✅ | test de ida y vuelta; tras el review, la plantilla propia también valida el avatar |
| CA6 | Cambio de tema en vivo, terminal incluido | ✅ | tests de `ThemeProvider`; `evidencias/themes/` |
| CA7 | Tema propio: crear, editar, exportar, importar; JSON inválido rechazado | ✅ | tests de API y componente; `evidencias/appearance/` |
| CA8 | Aviso de contraste; los temas incluidos cumplen | ✅ con matiz | test de contraste: 4,5:1 para el texto y **3:1 para las etiquetas de botón** (decisión del usuario, 2026-10-28; el rojo destructivo del Oscuro navy queda en 3,9:1) |
| CA9 | Sin colores fijos fuera de los *tokens* | ✅ | `no-hardcoded-colors.test.ts` |
| CA10 | Acerca de completa, GPLv3 sin conexión, terceros | ✅ | tests de componente; `evidencias/` (captura sin guardar: mostraba la ruta del usuario); `test_third_party_licenses.py` |
| CA11 | `mailto` a `contacto@cafeconpalito.com` | ✅ | test del `href` |
| CA12 | Zip con lo listado, sin salidas ni contenido, secretos sembrados limpios | ✅ | `test_support.py`; tras el review, claves con prefijo y cookies múltiples cubiertas |
| CA13 | Fichero guardado, explorador y correo | ✅ | e2e empaquetado en verde; prueba manual en la app de escritorio hecha por el usuario |
| CA14 | `LICENSE` y licencia en manifiestos e instalador | ✅ | revisión (bloque 1) |
| CA15 | Suites en verde, lint y tipos | ⚠️ | lint, tipos, frontend y e2e en verde; backend con los 3 fallos de arriba, ajenos a la fase |

## Code review
| Hallazgo | Severidad | Resolución |
|---|---|---|
| Claves con prefijo (`GITHUB_TOKEN=`) y solo la primera cookie ocultas | alta | corregido (`redact.py` y `desklog.rs`) + tests |
| `state`, `code`, `session`… ocultaban diagnósticos normales | media | corregido: fuera de las asignaciones (siguen en las *queries*) |
| Plantilla propia sin validar `avatar` | media | corregido (`avatars.check`) |
| `upload_avatar` leía el cuerpo entero antes del límite | media | corregido (413 por `Content-Length`) |
| `describe()` devolvía `undefined` | media | corregido |
| JPEG con EXIF grande rechazado | media | corregido (1 MB de cabecera) |
| `.ZIP` rechazado en Tauri | baja | corregido |
| `desktop.log` con la ruta del usuario en el `stderr` | baja | corregido |
| Secretos como argumento `%s` o por clave en structlog no se detectan | media | justificado: límite de «mejor esfuerzo» del ADR 0027; la persona revisa el zip |
| `POST /support/logs/bundle` escribe en cualquier `.zip` | baja | justificado: API solo en loopback y «Guardar como» ya confirma el sobrescrito |

## Retro
- **Cambios respecto a la spec**: búhos propios en SVG; «Adelante» sin registrar `Alt+←/→` ni el ratón (ya lo hace el WebView); contraste de botones a 3:1; la imagen del agente se aplica al momento, sin «Guardar cambios». Detalle en el plan (notas 1–14) y en el ADR 0027.
- **Impacto en fases futuras / pendiente**:
  - elegir imagen y color al crear un agente, y cambiar el búho a mano en la ficha del Arquitecto;
  - personalización de equipos y proyectos;
  - subir el zip de registros a un servidor;
  - arreglar los dos tests de conexiones y el orden inestable de `test_the_three_levels`;
  - la versión de los manifiestos sigue en 1.0.0 (el usuario la arreglará desde git).

## Cierre
- [x] Pruebas manuales en la app de escritorio (escala de texto, Guardar como y correo, `desktop.log`, recorte de una foto real)
- [x] OK del usuario
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v1.12`
- [x] `docs/roadmap.md` actualizado
