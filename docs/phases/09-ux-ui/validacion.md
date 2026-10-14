# Fase 09: Mejora de UX/UI · Validación

> Estado: **pendiente de revisión con el usuario** (CA11) y de `/code-review`.

## Tests automáticos
```
frontend (vitest):  22 archivos · 160 tests en verde
frontend:           eslint, prettier --check y tsc en verde
backend (pytest):   nuevos test_home_api.py (5) y test_tasks_api.py (+1) en verde
                    2 fallos en tests/test_usage_stats.py (límites diarios) que no tocan código
                    de esta fase: también fallaban con los cambios del frontend revertidos.
                    Pendiente de investigar y de confirmar sobre main.
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Menos pasos (ver tabla) | ✅ por tests; ⏳ medición manual | tabla abajo; `new-task.test.tsx`, `home.test.tsx`, `palette.test.tsx` |
| CA2 | Cabecera v7 con navegación y contadores; sin sidebar; páginas de segundo nivel por ruta | ✅ | `AppHeader.test.tsx`, `new-agent.test.tsx` (redirecciones) |
| CA3 | Inicio: saludo, «Te necesitan», agentes, resumen; estados normal, vacío, cargando | ✅ (desconectado y tema claro: ⏳ captura) | `home.test.tsx`; revisión visual con backend real (Inicio y Ctrl+K) |
| CA4 | Aprobar, rechazar, responder y reanudar desde Inicio | ✅ | `home.test.tsx` (mismos endpoints que Inbox); `test_hitl_e2e.py` sin cambios |
| CA5 | Avisos de CLI (cuota, sesión, ≥ 95 %) y «Posponer» | ✅ | `home.test.tsx` |
| CA6 | Nueva tarea con `N`, Ctrl+K y «+»; recuerda la última elección; «Crear y encolar» | ✅ | `new-task.test.tsx`, `palette.test.tsx` |
| CA7 | Nuevo agente como borrador + «Activar»; Nuevo proyecto con carpeta, pipeline y color | ✅ | `new-agent.test.tsx`, `new-project.test.tsx`, `agent-summary.test.tsx` |
| CA8 | Ctrl+K, `?`, guardas de foco/terminal/diálogo y preferencia | ✅ (prueba manual con ejecución en vivo: ⏳) | `shortcuts.test.ts`, `palette.test.tsx`, `settings.test.tsx` |
| CA9 | Ajustes con índice lateral y «Atajos de una tecla» | ✅ | `settings.test.tsx` |
| CA10 | Acabado v7 en los dos temas, AA, sin animaciones con `prefers-reduced-motion` | ⏳ | tokens y primitivas aplicados; falta revisión con el usuario y medida de rendimiento con terminal en vivo en WebView2 |
| CA11 | Revisión con el usuario | ⏳ | — |
| CA12 | Lint, typecheck y tests en verde | ✅ salvo los 2 fallos previos de `test_usage_stats.py` | arriba |

### Tabla de pasos de CA1 (antes: contados sobre el código de la v1.0 · después: tests)
| Flujo | Antes | Después |
|---|---|---|
| (a) Crear y encolar una tarea | «Nueva tarea» → elegir proyecto → escribir título → elegir agente → «Crear tarea» (≈ 7 interacciones) | `N` → escribir → Enter (3) |
| (b) Aprobar una petición al abrir la app | Inbox en la barra lateral → «Aprobar» (2) | «Aprobar» en «Te necesitan» (1) |
| (c) Ir a la tarea de un agente | Tablero → localizar la tarea → clic (≥ 3) | clic en la sesión de su tarjeta (1) |
| (d) Encontrar una tarea por `T-n` | no había búsqueda: Tablero y buscar a ojo (≥ 3) | Ctrl+K → `T-n` → Enter (3) |

La medición «antes» no se hizo ejecutando la v1.0; si se quiere, se repite en `main`.

## Code review
Pendiente (`/code-review`).

## Retro
- **Cambios respecto a la spec**: el plan se dio por aprobado con la orden «ejecuta el plan». La etapa del pipeline en «Nueva tarea» no es seleccionable: la tarea siempre empieza en la primera etapa (lo que ya hacía el backend), así que el campo muestra «Empieza en <etapa> con <agente>». Se retiraron `TodayUsageCard` y `CliReadinessBanner` (sustituidos por el resumen y los avisos de Inicio) y los componentes `sidebar` y `use-mobile`.
- **Impacto en fases futuras**: la fase 10 (equipos y cuentas) añade la cuota por cuenta a la columna de CLIs y los equipos a la rejilla; `/api/home` y `CliAlertItem` ya están preparados para ello.

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v0.9`
- [ ] `docs/roadmap.md` actualizado
