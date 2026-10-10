# Fase 02: Dominio y CRUD · Validación

- **Rama**: `phase/02-dominio-crud`
- **Fecha**: 2026-10-10

## Tests automáticos
`scripts/check.ps1`:

```
Step                            Result
----                            ------
Lint backend (ruff)             OK
Lint frontend (eslint+prettier) OK
Lint desktop (rustfmt)          OK
Lint spikes (ruff)              OK
Tests backend (pytest)          OK   55 passed  (+45 en esta fase)
Tests frontend (vitest)         OK   34 passed  (+20 en esta fase)
Tests desktop (cargo test)      OK    3 passed
Tests spikes (pytest)           OK   15 passed
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | La BD se crea y migra sola; los datos sobreviven a reinicios del backend y de la app empaquetada | ✅ | `test_migrations.py` (BD nueva, idempotencia, datos tras reinicio). App empaquetada: [`evidencias/ca1-persistencia.log`](evidencias/ca1-persistencia.log). El primer lanzamiento crea la BD y aplica las migraciones (Alembic en el log); el agente y el proyecto creados siguen ahí en el segundo lanzamiento; 0 procesos huérfanos. Además, `new_migration.py` genera una revisión vacía: modelos y migraciones están sincronizados |
| CA2 | API de agentes: CRUD, plantillas, duplicar y validaciones con 404/422 coherentes | ✅ | `test_agents_api.py` (15 tests: CRUD, plantillas y sobrescritura, plantilla desconocida, duplicar, 9 casos de validación, 404) |
| CA3 | API de proyectos: validación de ruta (inexistente / crear / duplicada), worktree sin git, detección git | ✅ | `test_projects_api.py` (9 tests, incluidos duplicados con otra capitalización y separadores, repo git temporal con rama `develop` y cambios, carpeta borrada tras el registro, «abrir carpeta») |
| CA4 | `GET /api/clis` informa de instalación, versión y modelos, y no falla si falta un CLI | ✅ | `test_clis.py` (instalados, ausente, error de modelos, caché/refresh). Con los CLIs reales: Claude Code 2.1.296 (3 alias) y agy 1.3.2 (14 modelos) |
| CA5 | Pantallas de Agentes funcionales y fieles al diseño | ✅ | `agents.test.tsx` (9 tests). Capturas: [`ca5-agentes-lista.jpg`](evidencias/ca5-agentes-lista.jpg), [`ca5-agente-general.jpg`](evidencias/ca5-agente-general.jpg), [`ca5-agente-ejecucion.jpg`](evidencias/ca5-agente-ejecucion.jpg), comparadas con `02`, `03a` y `03b` del diseño |
| CA6 | Pantallas de Proyectos funcionales y fieles al diseño; selector de carpeta nativo | ✅ / ⚠️ | `projects.test.tsx` (9 tests). Capturas: [`ca6-proyectos-lista.jpg`](evidencias/ca6-proyectos-lista.jpg), [`ca6-proyecto-resumen.jpg`](evidencias/ca6-proyecto-resumen.jpg), [`ca6-proyecto-memoria.jpg`](evidencias/ca6-proyecto-memoria.jpg), [`ca6-proyecto-nuevo.jpg`](evidencias/ca6-proyecto-nuevo.jpg), comparadas con `05` y `06a` del diseño. El plugin de diálogo nativo está integrado y con su permiso (`dialog:allow-open`), pero **abrir el diálogo en la app de escritorio no se ha probado a mano**: queda para la comprobación del usuario |
| CA7 | Aviso de cambios sin guardar | ✅ | Test «asks before leaving with unsaved changes» y «switching tabs keeps the edits» |
| CA8 | `check` en verde; README, roadmap y ADRs actualizados | ✅ | Salida de arriba; README (datos, migraciones, API), [ADR 0006](../../adr/0006-persistence.md), roadmap |

## Code review
`/code-review high` sobre `main...phase/02-dominio-crud`:

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Las fechas leídas de SQLite perdían la zona horaria («hace 2 h» en algo recién editado, en UTC+2) | Alta | **Corregido** (reproducido con un test): tipo `UTCDateTime` que devuelve siempre UTC con zona; las respuestas de lectura y escritura tienen el mismo formato (`Z`) |
| `PATCH` con `null` explícito → `IntegrityError` → 500 | Alta | **Corregido** (reproducido): los schemas rechazan `null` con 422 (omitir el campo = no cambiarlo); tests para agentes y proyectos |
| `--version` con salida vacía → `IndexError` → `/api/clis` 500 | Media | **Corregido**: `parse_version()` comprueba el código de salida y las líneas vacías; test |
| Rutas relativas resueltas contra la carpeta del sidecar (y «Crear carpeta» la creaba allí) | Media | **Corregido**: 422 `path_not_absolute`, con texto en `es.json`; 3 tests |
| «Volver a detectar» sin `catch`: rechazo de promesa sin aviso | Media | **Corregido**: `toast.error` como en el resto de acciones |
| 404 reintentado 3 veces (~7 s de skeleton para un agente borrado) | Media | **Corregido**: sin reintentos ante errores 4xx (`QueryClient`); test que comprueba una sola petición |
| Sondas de CLIs en serie, con el lock tomado (hasta ~2 min en frío) | Media | **Corregido**: se sondean en paralelo; el lock solo evita sondeos duplicados simultáneos; test de paralelismo |
| `list_projects` lanzaba git en serie por proyecto; parámetro `with_git` muerto | Media | **Corregido**: detección en paralelo (hasta 8), `which git` cacheado, parámetro eliminado |
| Carrera en la ruta única → `IntegrityError` → 500 | Baja | **Corregido**: `_commit()` traduce el error a 409 `project_exists`; test que simula la carrera |
| Textos visibles en español dentro del backend («(copia)», «Sonnet (último)») | Baja | **Corregido**: el duplicado recibe el nombre localizado desde la UI (`agents.copyName`) y los alias de modelo se nombran en `es.json` (`cli.alias.*`); test del duplicado |

## Incidencias durante el desarrollo
- **El CLI de shadcn volvió a generar `import { cn } from "cn"`** y a añadir el paquete `cn`, igual que en la fase 00. Se corrigieron los imports y se añadió la regla ESLint `no-restricted-imports` para que no vuelva a colarse.
- **Aviso de cambios sin guardar al cambiar de pestaña** en el editor de agentes (cada pestaña es una ruta). Lo detectaron los tests; se corrigió con `scope` en `UnsavedChangesGuard`. En Memoria y Ajustes del proyecto el aviso al cambiar de pestaña es correcto, porque cada pestaña es un formulario independiente.
- **El editor markdown ignoraba su altura**: el `Textarea` de shadcn usa `field-sizing: content`. Se vio en la revisión visual y se corrigió con `field-sizing-fixed`.
- **Los tests que lanzan el backend como subproceso** habrían creado la BD en el `%APPDATA%` real; ahora usan una carpeta de datos temporal.
- **El hook pre-commit** frenó un commit con variables sin usar en el backend falso de los tests.
- **Tras el code review**, `new_migration.py` vuelve a generar una revisión vacía: el nuevo tipo `UTCDateTime` no cambia el esquema.

## Retro
### Cambios respecto a la spec y al plan
- **`database_url` configurable** (no estaba en el plan): prepara el modo servidor y facilita los tests.
- **Backend falso en memoria para los tests del frontend** (`src/test/fake-backend.ts`): permite probar las pantallas de extremo a extremo sin backend real.
- **«Abrir carpeta»** se hace desde el backend (`os.startfile`); en el modo servidor habrá que desactivarlo.
- **Script `backend/scripts/new_migration.py`** para generar migraciones de forma fiable.
- **Agentes de Claude con alias de modelo** (`sonnet`, `opus`, `haiku`); en `agy`, «Predeterminado del CLI» o un id concreto de `agy models`.
- Las plantillas mencionan `request_human`, que llegará en la fase 06.

### Impacto en fases futuras
- **Fase 04**: traducir `permission_mode` y `allowed_tools` a los flags de cada CLI (ADR 0004); usar `instructions` en el context builder.
- **Fase 05**: modelos de Pipeline/Stage/Task (con su migración `0002`) y editor de pipeline; las columnas «En cola», «Pipeline» y «Abiertas» dejarán de mostrar «—».
- **Fase 07**: la columna «Consumo del mes» y los KPI del Resumen.
- **Ajustes** (CLIs detectados): la API ya existe (`/api/clis`); falta la pantalla.

## Cierre
- [x] OK del usuario (2026-10-10)
- [x] Merge a `main` (`--no-ff`)
- [x] Tag `v0.3`
- [x] `docs/roadmap.md` actualizado
