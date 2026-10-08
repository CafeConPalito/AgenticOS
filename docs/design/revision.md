# Revisión del diseño (Claude Design) · 2026-10-08

## Valoración
Entrega muy completa y de alta fidelidad:
- tokens en formato shadcn + Tailwind 4 (`tokens.css`);
- design system, componentes y las 10 pantallas documentadas;
- 26 capturas;
- prototipo HTML navegable;
- unas 1.300 líneas de código React de referencia (shell, primitivas, tarjetas, terminal xterm, Dashboard, Tablero, Detalle de tarea e Inbox).

Respeta la identidad pedida: navy, textos blancos y Ubuntu / Ubuntu Mono. **Se adopta como referencia visual del proyecto.**

## Cómo se usa
| Pieza | Uso |
|---|---|
| `tokens.css` | Se copia a `frontend/src/styles/tokens.css` con los ajustes de abajo. Es la fuente de verdad de colores, radios y animaciones |
| `design-system.md`, `components.md` y `screens.md` | Especificación de cada pantalla; cada fase que construya una pantalla la enlaza en su spec |
| `code/` | Punto de partida, **no se copia tal cual**: hay que pasar los textos a i18n, sustituir el estado local por React Router y TanStack Query, y cambiar los hex en línea por tokens |
| `prototype/` y `screenshots/` | Referencia visual y de comportamiento, y criterio de aceptación visual en cada fase |

## Ajustes técnicos al integrarlo
1. **Fuentes en local**: se quita el `@import` de Google Fonts de `tokens.css` y se usa `@fontsource/ubuntu` y `@fontsource/ubuntu-mono` (la app tiene que funcionar sin internet).
2. **Tema**: el oscuro navy usa la clase `.dark` en `<html>` (convención de shadcn), y es el tema por defecto.
3. **Puerto del backend**: el diseño muestra `ws://127.0.0.1:4317` fijo. Se ignora y se usa el puerto dinámico del sidecar (ADR 0002); el banner de desconexión mostrará la URL real.
4. **Colores en línea**: el código de referencia tiene hex sueltos (`bg-[#2E5BD6]`, `text-[#0A1A33]`…). Se sustituyen por los tokens (`bg-primary-action`, etc.).
5. **Textos**: todos los literales del código de referencia van a `es.json`.
6. **Navegación**: la referencia usa un `useState` como router; nosotros usamos React Router con rutas reales (`/tablero/tareas/:id`…).

## Detalles a corregir del diseño (los arreglamos al implementar cada pantalla)
- **Ajustes**: el título «Conocimiento y skills» aparece duplicado.
- **Tablero › Colas por agente**: el texto vacío sale como «Cola vacía ·Ritaestá disponible» (faltan espacios). En la tarjeta "Esperando humano" el estado y el nombre del proyecto se parten en dos líneas.
- **Datos de ejemplo de los CLIs**: Antigravity aparece como `gemini.exe`; el real es `agy.exe` (`%LOCALAPPDATA%\agy\bin`). Las versiones son inventadas.
- **«Buenos días, Marta»**: hace falta un ajuste "Tu nombre" (mono-usuario). Se añade a Ajustes en la fase 02.
- **Logos de CLI**: los marcadores «CC/AG/CX» se mantienen hasta comprobar las guías de marca de cada proveedor.

## Implicaciones para fases futuras
- **«Tomar control» pausa al agente** (fase 03): en un PTY el CLI sigue vivo, así que hay que decidir qué significa "pausar" (enviar Esc o interrumpir el turno en Claude Code y en `agy`, o solo bloquear el envío de prompts nuevos del scheduler). Se investiga en el spike de la fase 01.
- **Pausar / Reintentar / Cancelar** en la cabecera de la tarea, el **dock de terminal global (Ctrl+`)** y la **paleta Ctrl+K**: se reparten entre las fases 03, 05 y 08.
- **Límite diario de coste** (Dashboard: «Límite diario 25 €»): nuevo requisito → fase 07.
- Las pantallas Agentes, Proyectos, Consumo, Conocimiento, Ajustes y Arquitecto **no tienen código**; se construyen a partir de `screens.md` y del prototipo.
