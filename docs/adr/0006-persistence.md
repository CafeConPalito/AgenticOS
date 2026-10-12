# ADR 0006: Persistencia

- **Estado**: aceptado
- **Fecha**: 2026-10-10
- **Contexto de decisión**: fase 02 ([`plan.md`](../phases/02-dominio-crud/plan.md))

## Contexto
Agentic OS necesita guardar agentes y proyectos (y más adelante tareas, ejecuciones, consumo…) en la máquina del usuario, sin instalar nada aparte. El mismo backend debe poder pasar a modo servidor (fase 14) con varios usuarios.

## Decisión
- **SQLite** en la carpeta de datos (`%APPDATA%\AgenticOS\agentic-os.db`), con `PRAGMA foreign_keys=ON` y modo WAL. `AGENTIC_OS_DATABASE_URL` permite usar otra base de datos (p. ej. Postgres en el modo servidor).
- **SQLAlchemy 2** (modelos tipados con `Mapped`) y **Alembic** para las migraciones, aplicadas de forma programática en el arranque del backend (`upgrade_to_head` en el lifespan). Con SQLite se usa `render_as_batch`.
- Convenciones de nombres fijas para índices y restricciones, para que las migraciones sean deterministas.
- **Ids UUID en texto**, timestamps `created_at` / `updated_at` en UTC y **`workspace_id`** en todas las tablas (hoy siempre `"default"`; será el tenant en el modo servidor).
- Los valores cerrados (CLI, modo de permisos, estado, modo de workspace) se guardan como texto con `CHECK` en la base de datos y enums en los schemas Pydantic.
- **Estado derivado que no se guarda**: el estado git de un proyecto (repo, rama, cambios) se calcula al leerlo, porque cambia fuera de la app.
- **Rutas**: se guarda la ruta resuelta y una clave normalizada (`path_key`, con `normcase` en Windows) con índice único por workspace, para detectar el mismo proyecto escrito de otra forma.
- **Empaquetado**: las migraciones viajan como datos en el ejecutable de PyInstaller (`--add-data`), porque Alembic las carga como archivos.

## Consecuencias
- ✅ Cero instalación, y los datos sobreviven a reinicios y actualizaciones (verificado con la app empaquetada).
- ✅ Cambiar a Postgres es cambiar la URL; las migraciones son las mismas.
- ⚠️ SQLite admite un único escritor a la vez: no es un problema con un solo proceso de backend y sesiones cortas, pero hay que revisarlo si la fase 05 escribe mucho en paralelo (scheduler + eventos).
- ⚠️ Las migraciones nuevas se generan con `alembic revision --autogenerate` y **se revisan a mano** antes de hacer commit.
