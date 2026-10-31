# Fase 22: Temas y apariencia · Validación

## Tests automáticos
```
Frontend (npm run test:frontend): 79 ficheros, 791 tests en verde, también tras el code-review.
Backend  (uv run pytest, backend/.test-progress.log): la primera pasada se cortó al 52 % por
         falta de memoria del sistema, con un fallo hacia el 8 %. La suite se repitió en dos
         tandas (el 48 % restante y el primer 52 % con -rf): todo en verde, sin repetirse el
         fallo, que fue intermitente. Tras el code-review, test_settings_appearance.py y
         test_builtin_themes.py otra vez en verde.
Lint     (npm run lint): backend, frontend (ESLint, Prettier, tsc), desktop (cargo fmt) y
         spikes en verde. Lista de licencias al día (scripts/licenses.py --check).
Desktop  (cargo test): 19 en verde, entre ellos fonts (familias únicas, sin ocultas).
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | La cabecera y la paleta de comandos ya no tienen el cambio claro/oscuro | ✅ | `ThemeProvider.test.tsx`, `palette.test.tsx`; capturas en [`evidencias/`](evidencias/) sin el botón |
| CA2 | El filtro de la galería muestra solo los temas claros u oscuros, propios incluidos, y se recuerda | ✅ | `appearance.test.tsx`; [`galeria-oscuros.png`](evidencias/galeria-oscuros.png) |
| CA3 | «Seguir al sistema» ya no existe; quien lo tenía conserva el tema que veía; el filtro arranca según Windows | ✅ | `test_settings_appearance.py` (documentos de la fase 20 con `mode: system` y `fixed`), `ThemeProvider.test.tsx` (sistema claro y oscuro, copia local), `appearance.test.tsx` |
| CA4 | «Nuevo tema» crea un tema claro u oscuro sin partir de otro, y se edita, guarda, exporta e importa | ✅ | `appearance.test.tsx`, `test_settings_appearance.py` |
| CA5 | Un tema con una fuente del sistema la aplica en toda la app instalada | ⏳ pendiente de la prueba del usuario | `font-picker.test.tsx`, `ThemeProvider.test.tsx`; spike S1 (WebView2 pinta 114 de 116 familias por su nombre) |
| CA6 | Una fuente que falta usa la del sistema y el editor avisa | ✅ | `font-picker.test.tsx`, `system-fonts.test.ts` |
| CA7 | Los temas exportados en la fase 20 se siguen importando | ✅ | `appearance.test.tsx` (fichero v1), `test_settings_appearance.py` |
| CA8 | Al menos 25 temas, claros y oscuros, con los de VS Code; contraste comprobado y licencia en Acerca de | ✅ | 28 temas (12 claros, 16 oscuros): `derive.test.ts`, `contrast.test.ts` (los 28), `about.test.tsx`, `test_builtin_themes.py`; licencias MIT comprobadas en GitHub (2026-10-31) |
| CA9 | En el menú de Ajustes los títulos de grupo se distinguen, también en pantallas estrechas, con teclado | ✅ | `settings.test.tsx`; [`menu-ajustes.png`](evidencias/menu-ajustes.png), [`menu-ajustes-estrecho.png`](evidencias/menu-ajustes-estrecho.png) |
| CA10 | Suites, lint y `/code-review` en verde | ✅ | arriba y en la tabla siguiente |

## Code review
`/code-review medium` sobre la rama frente a `main`: 8 hallazgos, todos corregidos (`bb40df3`).

| Hallazgo | Severidad | Resolución |
|---|---|---|
| Un tema propio de la fase 20 llamado como uno de los nuevos (`dracula`, `nord`…) invalidaba el documento entero y se perdían todos los temas | alta | Al leer, el tema propio pasa a un id libre (`dracula-2`…) junto con lo que lo usaba; test |
| La migración de «Seguir al sistema» guardaba dentro de la lectura: si fallaba, la app usaba una copia local quizá vieja | media | Se guarda después de leer; si falla, se vuelve a leer y se reintenta |
| Borrar un tema padre daba su fuente del sistema a un hijo con fuente propia | media | No se copia `font_family` si el hijo tiene `font`; test |
| «Inter» incluida e «Inter» instalada compartían valor en el buscador | media | Valores con prefijo por grupo; test |
| Fuentes que solo difieren en mayúsculas no ASCII salían dos veces | baja | Una por nombre en minúsculas; el orden alfabético en español lo hace la página |
| La medición de fuentes creaba un *canvas* por familia y se repetía en cada render | baja | Un *canvas* compartido, anchos genéricos una vez y comprobación memorizada |
| La galería resolvía los 28 temas solo para saber su base | baja | La base sale de la definición |
| Ids de los temas propios en español (`bosque`…) | baja | En inglés: `forest`, `ocean`, `wine`, `sand`, `lavender`, `mint` |

## Retro
- **Cambios respecto a la spec y el plan**:
  - El modo lectura nocturno salió de la fase antes de aprobar la spec: el sistema operativo ya lo ofrece.
  - Salen 17 temas de VS Code y no 16, porque Tokyo Night Day entra con Tokyo Night. Con los 6 propios suman 28.
  - Los temas propios guardados con un id que ahora es de un tema incluido se renombran al leerlos (hallazgo del code-review).
- **Lo aprendido**:
  - WebView2 no pinta por su nombre tipográfico las fuentes variables con instancias con nombre (Segoe UI Variable, Sitka). Medir con un *canvas* lo detecta sin depender de listas.
  - Ampliar la lista de ids reservados rompe datos guardados: hay que migrar al leer.
- **Impacto en fases futuras**:
  - Importar temas de VS Code (`.json`) queda anotado: `fromPalette` ya hace casi todo el trabajo.
  - Un tema incluido nuevo exige su id en el backend; `test_builtin_themes.py` lo vigila.

## Cierre
- [ ] OK del usuario (prueba en la app instalada: CA5)
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v0.9.2` y versión `0.9.2` en los manifiestos
- [ ] `docs/roadmap.md` actualizado
