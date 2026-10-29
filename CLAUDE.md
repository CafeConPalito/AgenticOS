# Agentic OS

App de escritorio (Tauri + FastAPI + Vite/React) para orquestar agentes de IA que trabajan a través de CLIs (Claude Code, Gemini CLI, OpenCode, Codex CLI…). Visión completa en `docs/vision.md` y fases en `docs/roadmap.md`.

## Flujo de desarrollo por fases (obligatorio)
Cada fase sigue el ciclo **Spec → Plan → Desarrollo → Validación**, con tres puertas de aprobación del usuario:

1. `docs/phases/NN-nombre/spec.md` → ⛔ aprobación del usuario antes de planificar.
2. `docs/phases/NN-nombre/plan.md` (+ ADRs en `docs/adr/` si hay decisiones) → ⛔ aprobación antes de programar.
3. Desarrollo en la rama `phase/NN-nombre`, con commits pequeños y tests.
4. `docs/phases/NN-nombre/validacion.md`: tests en verde, checklist de criterios de aceptación con evidencias, `/code-review` resuelto, retro → ⛔ OK del usuario → merge `--no-ff` a `main`, tag de versión (ver abajo) y actualización de `docs/roadmap.md`.

Reglas:
- No empezar una fase sin haber cerrado la anterior. No programar fuera del alcance de la spec aprobada; si surge algo, se anota para una fase futura.
- Mantener al día el estado de la fase en `docs/roadmap.md` (pendiente · spec · plan · dev · validación · cerrada).
- Tags de versión (SemVer `vX.Y.Z`, la versión de cada fase está en `docs/roadmap.md`): las fases 00–20 son pre-1.0 y la 20 es `v0.9.0`; las correcciones previas a la publicación son `v0.9.1`–`v0.9.4`, la publicación en GitHub es `v0.9.5`, los instaladores firmados `v0.9.6` y la `v1.0.0` sale de las correcciones tras probar esa release. Desde ahí, cada fase sube el parche (`v1.0.1`, `v1.0.2`…); la menor (`v1.1.0`…) solo sube cuando el usuario lo decide por un conjunto grande de funcionalidad nueva. La versión de la app (`package.json`, `tauri.conf.json`, `Cargo.toml`, `pyproject.toml`, `__init__.py`) se sube a la de la fase al cerrarla. Nunca se etiqueta por debajo de la última versión existente.
- Las plantillas de los documentos de fase están en `docs/phases/_template/`.

## Convenciones
- Documentación y textos de la UI en español (UI con i18n; claves en `frontend/src/i18n/`).
- Código, identificadores y mensajes de commit en inglés.
- Backend: Python 3.12, gestionado con `uv`; ruff para lint y formato; pytest.
- Frontend: TypeScript estricto, ESLint y Prettier, vitest.
- Mensajes de commit: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`…).
