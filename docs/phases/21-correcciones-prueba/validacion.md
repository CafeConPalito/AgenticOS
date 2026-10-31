# Fase 21: Correcciones de la prueba · Validación

## Tests automáticos
```
Backend  (uv run pytest, backend/.test-progress.log): suite completa en dos tandas, porque la
         primera se cortó al 78 % por falta de memoria del sistema; la segunda pasó los 83
         ficheros restantes (678 tests). Cuatro fallos, ninguno de esta fase, todos corregidos
         y vueltos a pasar:
  - test_connections_adapters.py (2): de la fase 19 (propose_agent desactivado sin permiso);
    ya anotados en la validación de la fase 20. Los tests usan ahora un agente con permiso.
  - test_memory_notes.py::test_notes_crud: intermitente. Dos notas en el mismo «tic» del
    reloj (15 ms en Windows) salían en orden aleatorio; ahora se ordenan por orden de
    inserción (rowid). 5/5 en verde.
  - test_third_party_licenses.py: la lista no se regeneró tras renumerar las versiones
    (069c37a). Regenerada con scripts/licenses.py.
Frontend (npm run test:frontend): 76 ficheros, 723 tests en verde; tras el code-review,
         los 25 ficheros afectados (192 tests) otra vez en verde.
Lint     (npm run lint): backend, frontend (ESLint, Prettier, tsc), desktop (cargo fmt) y
         spikes en verde (en spikes se ordenó un import que ya fallaba antes).
Desktop  (cargo test): 18 en verde, entre ellos bundle_checks (plantilla NSIS, icono, CSP)
         y export (nombre sin carpetas).
Dictado  : test_dictation_real y test_dictation_e2e con el motor real de whisper.cpp, en verde.
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Icono de la app en el `.exe` del instalador y en sus ventanas | ✅ (pendiente de que el usuario lo vea con el instalador nuevo) | `bundle_checks`; los recursos del `.exe` (`pefile`) llevan el icono de la app en los seis tamaños, de 16 a 256 px. El icono de NSIS que vio el usuario era la caché de iconos de Windows. El desinstalador también lleva el icono de la app |
| CA2 | Textos de la última pantalla legibles | ✅ | Comprobado por el usuario en el instalador (2026-10-29) |
| CA3 | El Arquitecto en el listado de Ejecuciones; el contador coincide | ✅ | `test_phase21_fixes.py`, `runs.test.tsx`; comprobado por el usuario |
| CA4 | Exportar agente, tema y CSV en la app de escritorio y en el navegador | ✅ | `save-file.test.ts`, `export.rs`; comprobado por el usuario en los tres sitios |
| CA5 | Limpieza no desplaza la app | ✅ | `settings.test.tsx`; comprobado por el usuario |
| CA6 | Modelos sin descargar como «Aconsejado» | ✅ | `knowledge-settings.test.tsx` |
| CA7 | Micrófonos de Windows en la lista | ✅ | `dictation-settings.test.tsx`; comprobado por el usuario (WebView2 pidió el permiso: no hizo falta tocar Rust) |
| CA8 | Sin hueco en Conocimiento, Skills y Conexiones | ✅ | `agents.test.tsx`; comprobado por el usuario |
| CA9 | Foto del agente encuadrada y guardada | ✅ | `bundle_checks` (CSP con `blob:`); comprobado por el usuario |
| CA10 | Equipo sin agentes | ✅ | `home.test.tsx`; comprobado por el usuario |
| CA11 | Rama sin condición: se guarda y se toma siempre | ✅ | `test_lanes.py`, `test_pipeline_graph.py`, `test_migration_0023.py`, `pipeline-editor.test.tsx`; comprobado por el usuario |
| CA12 | Suites, lint y `/code-review` en verde | ✅ | arriba y en la tabla siguiente |
| CA13 | El motor de voz descargado cuenta como instalado | ✅ (pendiente de que el usuario lo pruebe) | `test_local_models.py::test_the_whisper_engine_counts_as_installed_once_unpacked`; tests de dictado con el motor real |
| CA14 | Editar equipo sin scroll horizontal | ✅ (pendiente de que el usuario lo pruebe) | Pie del diálogo con `flex-wrap` |

## Code review
`/code-review medium` sobre la rama frente a `main`: 10 hallazgos, todos corregidos (`4a7c253`).

| Hallazgo | Severidad | Resolución |
|---|---|---|
| El CSV perdía el BOM UTF-8 y Excel no leía las tildes | media | Se decodifica con `ignoreBOM` y el fichero guardado lo conserva |
| Una rama `always` con condición se volvía condicional al guardar desde el editor | media | El backend guarda «siempre» de una sola forma: sin condición |
| `always` y condición podían volver a convivir en los datos tras la migración | media | Igual que el anterior, normalizado al guardar; test nuevo |
| La ayuda de la rama decía «solo si…» en las ramas siempre tomadas | baja | La condición de la ayuda pasa a `condition && !always` |
| La etiqueta «siempre» faltaba en las ramas sin condición al elegir a mano | media | `DecisionBlock` trata la condición vacía como siempre |
| El dock de terminales mostraba el CLI del Arquitecto | media | El dock lo deja fuera; test |
| «Aconsejado» también en un modelo elegido que no es el aconsejado | baja | Solo el modelo por defecto |
| Una consulta por cada fila del Arquitecto en el listado de ejecuciones (N+1) | baja | Una sola consulta para todo el listado |
| Etiquetas del filtro de «Guardar como» sin i18n | baja | Claves `saveFilters.*` |
| `labelled: true` sobrante en `task-path.ts` | baja | Quitado |

## Retro
- **Cambios respecto a la spec**:
  - Dos fallos encontrados al probar el instalador de la fase entran como apartado G (CA13 motor de voz, CA14 diálogo de equipo).
  - Consumo › Exportar CSV entra porque compartía la causa con exportar agente y tema.
  - El guardado al exportar lo hace entero el *shell* de Rust: abre el diálogo y escribe el fichero, así que la página nunca le pasa una ruta. El aviso dice dónde quedó el fichero, sin botón de abrir carpeta.
  - El micrófono no necesitó cambios en Rust: WebView2 pide el permiso él solo.
- **Lo aprendido**:
  - Dos fallos (exportar y foto) solo se veían en la app instalada, por la CSP y por WebView2: la prueba en la app instalada debe seguir en el cierre de cada fase.
  - El motor de voz falló porque los *fakes* de los tests copiaban la estructura equivocada en vez de la del zip real. El test nuevo descomprime un zip con la estructura real.
  - La suite completa no cabe en memoria con otra compilación a la vez: hay que lanzarlas de una en una.
- **Impacto en fases futuras**:
  - La plantilla NSIS (`desktop/src-tauri/windows/installer.nsi`) hay que copiarla de nuevo al actualizar `@tauri-apps/cli`; un test lo recuerda.
  - La regla «sin condición = siempre» está anotada en el ADR 0020.
  - El orden por `rowid` de las notas es propio de SQLite: el modo servidor (fase 30, Postgres) necesitará otro desempate.

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v0.9.1` y versión `0.9.1` en los manifiestos
- [ ] `docs/roadmap.md` actualizado
