# Agentic OS v7 · Design system (cambios)

Base: `../design-system.md`. Aquí solo va lo que es **[NUEVO]** o **[CAMBIA]**. Tokens: `tokens.css` (los cambios van marcados con «v7»).
**No cambian:** la paleta corporativa, los colores de estado, los de identidad de agentes y proyectos, la fuente (Ubuntu / Ubuntu Mono) ni el tema navy como principal.

---

## 1. Jerarquía de información [NUEVO]
| Nivel | Tratamiento | Ejemplos |
|---|---|---|
| Primario | En tarjeta (`bg-card-grad` + `--shadow-card`) | Te necesitan, tarjetas de agente, Tareas |
| Secundario | Sin caja, directamente sobre el fondo | Columna de resumen, cabeceras de equipo, Configuración plegada |
| Terciario | `--muted-foreground` a 12px | Rol · CLI · cola, cuentas en Ejecuciones, datos de sesión |

**Regla del ámbar:**
- Con peticiones, `--status-waiting` (`#F5B547`) es el **único color fuerte** de Inicio:
  - el panel «Te necesitan»;
  - los contadores;
  - los badges de petición;
  - las cuotas y el gasto desde el 80 %.
- El tipo de petición ya no se colorea, y las barras de cuota y gasto son grises por debajo del 80 %.
- Los colores de identidad (avatares) y los puntos de estado se mantienen.

## 2. Tipografía [CAMBIA]
| Nivel | Antes | v7 |
|---|---|---|
| Saludo (H1 de Inicio) | 22/500 | **40/700**, tracking -.035em, line-height 1.05 |
| H1 de pantalla | 22/500 | **30/700**, tracking -.028em, line-height 1.15 |
| H2 de sección principal | 14–15/500 | **18/700**, tracking -.02em («Te necesitan», «Agentes») |
| H2 de panel | 13/500 | **15/700**, tracking -.01em |
| Eyebrow [NUEVO] | — | Ubuntu Mono 11/700, tracking .14em, mayúsculas, muted (títulos de la lateral) · 11.5/400 en la fecha |
| Título de petición | 15/500 | 14/500 |
| Nombre en tarjeta de agente | 13/500 | 14/500 |
| Cifra de gasto en la lateral | — | Ubuntu Mono 20/700, tracking -.02em |

Se añade `-webkit-font-smoothing: antialiased`.

## 3. Superficies, radios y sombras [CAMBIA]
**Radios:**

| Token | Antes | v7 | Uso |
|---|---|---|---|
| `rounded-sm` | 6 | 8 | Chips pequeños, kbd |
| `rounded-md` | 8 | 10 | Botones, inputs, avatar de 28 |
| `rounded-lg` | 12 | 14 | Filas de lista, tarjetas de tarea |
| `rounded-xl` | 14 | 18 | Secciones y cards |
| `rounded-2xl` | — | 20 | «Te necesitan», diálogos, Ctrl+K |
| `rounded-full` | | | Botones primarios (**ahora píldora**), botones de icono de la cabecera, chips de resumen |

La tarjeta de agente usa radio 16.

**Superficies:**
- `--sep`: separadores y bordes de tarjeta. Es `--border` al 65 % (oscuro) o al 80 % (claro) y sustituye a `--border` en las tarjetas y las filas.
- `bg-card-grad`: tarjetas con un degradado vertical sutil. Oscuro `#13294B → #0F2242`; claro `#FFFFFF → #FBFCFE`.
- `glass`: cabecera.
- `glass-pop`: diálogo, Ctrl+K, toast y menús.

**Sombras:**

| Nivel | Valor |
|---|---|
| Tarjeta (`--shadow-card`) | oscuro: `inset 0 1px 0 rgba(255,255,255,.04), 0 1px 2px rgba(0,0,0,.25), 0 8px 24px rgba(0,0,0,.18)` · claro: `0 1px 2px rgba(10,26,51,.05), 0 6px 20px rgba(10,26,51,.06)` |
| Pop (`--shadow-pop`) | oscuro: `0 0 0 .5px rgba(255,255,255,.08), 0 24px 64px rgba(0,0,0,.5)` |
| Botón primario | `inset 0 1px 0 rgba(255,255,255,.18), 0 8px 18px -8px var(--primary-action)` + `background-image: linear-gradient(180deg,rgba(255,255,255,.16),transparent)` |
| Avatar con brillo | `background: linear-gradient(150deg,rgba(255,255,255,.34),transparent 58%), <color>` · `box-shadow: inset 0 0 0 1px rgba(255,255,255,.2), 0 6px 14px -6px <color>` |
| Te necesitan | halo ámbar (ver components.md) |
| Overlay | `rgba(3,10,22,.4)` + `blur(6px)` (antes `.55` sin blur) |

## 4. Fondo atmosférico [NUEVO]
`--atmos`: tres halos radiales con colores de marca (azul `#2E5BD6` al 42 %, cian `#4CC9F0` al 13 % y violeta `#B39CFF` al 9 %; en claro, más tenues) y una trama de puntos de 1px cada 22px. Va en una capa fija detrás del contenido.

## 5. Movimiento [NUEVO]
| Animación | Valor | Dónde |
|---|---|---|
| `rise-in` | .55s `cubic-bezier(.2,.8,.2,1)`, `translateY(14px)` → 0 + fade | Entrada de pantallas. Escalonada en Inicio: saludo 0 · Te necesitan .08 · Agentes .16 · lateral .24 |
| `sheet-in` | .28s (paleta .24), `translateY(10px) scale(.985)` → 0 | Diálogos, Ctrl+K |
| `fade-in` | .2s | Overlays |
| `sweep` | 2.6s lineal infinita | Línea de ejecución de la tarjeta de agente |
| Pulsar | `scale(.97)`, .18s | Todos los `button` |
| Hover de tarjeta | `translateY(-1px)` | Tarjetas `role="link"` |
| Revelado al hover | opacidad, 150ms | Fila de consumo de la tarjeta de agente |

Con `prefers-reduced-motion` se desactivan todas.

## 6. Iconografía [CAMBIA]
Se añade `Gauge` (aviso de cuota de CLI). Todo lo demás sigue igual (lucide).
