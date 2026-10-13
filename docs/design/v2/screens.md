# Agentic OS v7 · Pantallas

Marcas: **[NUEVO]** no existía · **[CAMBIA]** existía y se modifica · sin marca = igual que en v4/v1.1.
Ventana de escritorio de 1280–1920px (mínimo 1100px). Capturas de 1440×900 en `screenshots/`.

## Esqueleto [CAMBIA]
- Ya no hay barra lateral de navegación. Columna única:
  - `AppHeader` de 56px, `position:absolute`, translúcido, por encima del contenido;
  - el **contenido** (scroll propio, `padding-top:56px`);
  - el `TerminalDock` opcional abajo (280px).
- Detrás de todo, una capa de fondo `bg-atmos` (`position:absolute; inset:0; pointer-events:none`) y el contenido en `z-index:1`.
- Todas las pantallas de detalle usan: padding `32px 32px 56px`, max-width 1240 (tarea 1400, ajustes 820), gap 24, y entran con `animate-rise-in`.

---

## 1. Inicio [CAMBIA]
Capturas: `03a`, `03b`, `03c`, `03d`, `01a`, `01b`.

**Layout:** rejilla `minmax(0,1fr) 300px`, gap 48, padding `28px 32px 56px`, max-width 1520, `align-items:start`.

### Columna principal (flex column, gap 32)
1. **Saludo** [CAMBIA] (`rise-in`, 0 s):
   - Línea superior (eyebrow): Ubuntu Mono 11.5, tracking .14em, mayúsculas, muted. Texto: «martes, 13 de octubre · 5 sesiones en vivo».
   - H1 «Buenos días, Marta»: 40/700, tracking -.035em, line-height 1.05.
   - Tres chips de 30px (píldora, borde `--sep`, fondo `card` al 65 % con blur 10px):
     - punto running pulsante + «**2** trabajando»;
     - punto ámbar + «**7** esperan respuesta»;
     - «**6,51 €** gastados hoy» (cifra en mono).
2. **Te necesitan** [CAMBIA] (`rise-in`, .08 s). Ver `NeedsYouPanel` en components.md.
   - Muestra 3 peticiones apiladas y luego los avisos de CLI. «Ver todas · n» / «Ver menos» alterna entre las 3 primeras y todas.
   - Orden de las peticiones: aprobación → pregunta → bloqueo → interrumpida → completada.
   - Sin peticiones ni avisos: la sección desaparece y queda una línea sin caja: ✓ (done) «Nada pendiente. Tus agentes no necesitan nada de ti ahora mismo.» (`03b`).
3. **Agentes** [CAMBIA] (`rise-in`, .16 s):
   - Cabecera: H2 18/700 «Agentes» · «3 equipos · 5 agentes» (12, muted) · botón ghost «Nuevo equipo».
   - Por cada equipo:
     - fila: nombre 13/700 · meta «3 agentes · 3 activos» (12, muted) · una línea de 1px que se desvanece (`linear-gradient(90deg,var(--sep),transparent)`) · ghost «+ Agente» · lápiz;
     - debajo, una rejilla `repeat(auto-fill,minmax(250px,1fr))` de `AgentCard` con gap 12.

### Columna lateral de resumen [NUEVO] (`rise-in`, .24 s)
- `position:sticky; top:84px`, `border-left:1px solid var(--sep)`, padding `20px 0 0 28px`, gap 30.
- **Sin tarjetas ni sombras.** Los títulos son eyebrow (mono 11/700, mayúsculas, muted).
- **Proyectos** · «3 activos» · «Ver todos» · «+»:
  - cada fila: cuadradito de color · nombre · «4 abiertas» a la derecha;
  - segunda línea (12, muted): actividad «Ana · Requisitos del checkout y 1 más», con los mini-avatares de 16px de quien trabaja.
- **Gasto de hoy**:
  - «**6,51 €** / 25 €» (cifra 20/700 mono);
  - barra de 6px: relleno `--muted-foreground`, ámbar desde el 80 %; marca de 1px en el 80 %;
  - «26% del límite diario» (12, muted).
- **CLIs** · «3 cuentas · 5 sesiones» · «Gestionar» · «+»:
  - fila por CLI: tag (CC, AG) · nombre · barra de 4px con la cuota más alta (gris; ámbar desde el 80 %) · % en mono · chevron;
  - segunda línea: «2 cuentas · 3 sesiones»;
  - clic → despliega las cuentas: email · barra · % · «Max 20× · 2 sesiones» (`01a`).
- **Conocimiento y skills** · «Abrir»: «6 fuentes · 5 skills activos · 2 memorias nuevas hoy» (12, muted).

### Estados
- Normal (`03a`).
- Vacío: sin peticiones (`03b`).
- Aviso de CLI (`03c`).
- Tema claro (`03d`).
- Cuentas desplegadas (`01a`) / plegadas (`01b`).

---

## 2. CLIs y cuentas
Sin cambios de contenido. Hereda el acabado v7 (radios, `--sep`, `bg-card-grad`).

## 3. Proyectos
Sin cambios de contenido. Hereda el acabado v7.

## 4. Conocimiento y skills [CAMBIA]
- Se entra desde la navegación superior; ya no hay tarjeta en Inicio.
- La lateral de Inicio muestra un resumen de una línea.

## 5. Ficha de agente [CAMBIA]
- Cabecera:
  - avatar de 52;
  - nombre: H1 30/700, tracking -.028em;
  - rol;
  - badge de estado;
  - acciones: «Asignar tarea» (primario, píldora), «Activar» (si es borrador) y «Editar».
- Arriba: peticiones de este agente (tarjetas con borde ámbar al 50 %) y **Tareas**, a la izquierda (1.3fr); **Consumo**, a la derecha (1fr).
- **[NUEVO] Configuración plegada al final**:
  - `<details>` con borde superior `--sep`;
  - resumen: chevron (gira 90° al abrir) · «Configuración» (foreground 500) · «Equipo, CLI, cuenta, modelo y permisos» (12, muted);
  - contenido: 5 columnas sin caja, etiqueta de 12 muted y valor de 13. Equipo · CLI · Cuenta · Modelo · Permisos · concurrencia.

## 6. Detalle de tarea [CAMBIA]
- Columna izquierda (380px): Descripción y Subtareas. **Los datos de sesión ya no están aquí.**
- Columna derecha: peticiones y la **Salida en directo** (terminal de 420px).
  - **[NUEVO]** Debajo, una línea sin caja (12, muted, `flex-wrap`, gap `4px 20px`): «Sesión `cc-7f3a91` · Cuenta `CC · marta@estudio.es` · Duración `41 min` · Coste `2,84 €`», con los valores en mono.

## 7. Tablero
Sin cambios de contenido. Hereda el acabado v7.

## 8. Ejecuciones [CAMBIA]
- Tabla `100px 120px minmax(0,1fr) 150px 90px 80px 120px`.
- La columna **Cuenta** pasa a 12px y muted (información terciaria).

## 9. Ajustes
Captura: `09-ajustes-v2`.
- Max-width 820.
- Una sección con 3 filas:
  - Límite de gasto diario `25,00 €`;
  - Aviso de cuota `80 %`;
  - Atajos de una tecla (Switch).
- **No tiene índice** (la v1.1 sí lo tenía).

## Diálogos
- **Nueva tarea** [CAMBIA] (`04a`, `04b`): ver `NewTaskDialog`.
  - Se abre con N, desde Ctrl+K «Nueva tarea» o desde «+» en una tarjeta de agente (agente preseleccionado).
- **Nuevo agente** (`05`):
  - Plantillas en una rejilla de 4 columnas: Analista, Desarrollador, QA, Redactor, Comercial, Investigador y En blanco.
  - Nombre · Rol · Equipo · Cuenta de CLI · Modelo (depende de la cuenta) · Permisos (segmented Restringido / Preguntar / Autónomo) · Instrucciones.
  - Nota: «Se crea como borrador. Actívalo desde su ficha cuando las instrucciones te encajen.» Botón «Crear borrador».
- **Nuevo proyecto** (`06`):
  - Nombre · Carpeta (mono) · Pipeline (Desarrollo web / Contenidos / Sin pipeline) · Color (6 muestras de 24px).
  - Botón «Crear proyecto».
- **Ctrl+K** (`07a`, `07b`) y **Ayuda de atajos** (`08`): ver components.md.
- Todos los diálogos:
  - `glass-pop`, radio 20, `--shadow-pop`, entrada `sheet-in`;
  - overlay `rgba(3,10,22,.4)` + `backdrop-filter: blur(6px)`, entrada `fade-in`.
