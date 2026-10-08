# ADR 0001: Stack tecnológico

- **Estado**: aceptado
- **Fecha**: 2026-10-08

## Contexto
Necesitamos una app de escritorio para Windows que lance y controle procesos de CLI en terminales reales, con una UI rica (tablero, terminales en vivo, paneles) y que en el futuro se pueda desplegar como servidor. El usuario está familiarizado con Vite para las interfaces y con FastAPI para el backend.

## Decisión
- **Backend**: Python 3.12 + FastAPI + SQLAlchemy 2 + Alembic. SQLite en local y Postgres en servidor. Dependencias gestionadas con `uv`.
- **Frontend**: Vite + React + TypeScript + shadcn/ui (Tailwind), TanStack Query, Zustand, xterm.js, dnd-kit, i18next.
- **Escritorio**: Tauri v2. El backend se empaqueta con PyInstaller y Tauri lo arranca como *sidecar*; la UI habla con él por HTTP/WS en localhost.
- **Terminales**: pywinpty (Windows) / ptyprocess (Unix) detrás de una abstracción común.

## Consecuencias
- ✅ El mismo backend sirve para escritorio y para servidor; solo cambia cómo se sirve el frontend y se añade autenticación.
- ✅ Tauri es ligero y tiene notificaciones nativas, bandeja y auto-update.
- ⚠️ Hace falta la toolchain de Rust (rustup + MSVC build tools) para compilar Tauri.
- ⚠️ Empaquetar Python con PyInstaller añade un paso de build y un binario más pesado; se valida en la fase 00 y se pule en la 08.

## Alternativas consideradas
- Electron + sidecar Python: más pesado y sin ventajas claras.
- pywebview: más simple, pero menos pulido (notificaciones, empaquetado, auto-update).
