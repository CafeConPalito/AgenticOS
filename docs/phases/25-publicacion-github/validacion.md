# Fase 25: Publicación en GitHub · Validación

> **Estado (2026-11-02)**: OK del usuario y merge a `main` (`v0.9.5`). CA1 está cumplido en la rama. CA2–CA4 están medidos en un ensayo de la reescritura sobre un clon temporal y se repiten sobre el repo real al cerrar. CA5–CA7 se hacen después del merge (bloque 7 del plan), porque necesitan el historial reescrito y publicado.

## Tests automáticos
```
Lint (npm run lint): ruff, ESLint, Prettier, tsc y rustfmt en verde, también ruff sobre los scripts nuevos.
Frontend (npm run test:frontend): 85 ficheros, 839 tests en verde.
Escritorio (npm run test:desktop): 19 tests en verde.
Spikes (npm run test:spikes): 15 tests en verde.
Scripts (npm run test:scripts): 18 tests en verde (check-public y apply-replacements).
Backend (uv run pytest, backend/.test-progress.log): suite completa de una vez, 1728 tests:
         1726 en verde y 2 saltados, código de salida 0. Antes, también en verde los que
         usan las fixtures cambiadas: test_adapters, test_screen, test_subagents,
         test_knowledge_graph_quality y test_support.
Tras subir la versión a 0.9.5 (y regenerar las licencias de terceros): en verde los tests del
         backend que leen la versión o las licencias, frontend (839) y escritorio (19).
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | El árbol no contiene el email real, el usuario de Windows ni secretos, y las imágenes no muestran datos personales | ✅ | `npm run check:public`: 1560 ficheros, 0 hallazgos ([línea base](evidencias/b1-linea-base.txt): 129 hallazgos en 82 ficheros). Las 81 imágenes revisadas una a una; 12 pixeladas ([lista](evidencias/b3-imagenes-revisadas.md)) |
| CA2 | Todo el historial pasa la comprobación y todos los commits tienen el autor noreply | ✅ en el ensayo | Clon temporal tras `git filter-repo`: `check-public.py --history --expect-identity "TerciodeMarte <…noreply…>"` da 4164 blobs y 0 hallazgos. Commits, *committers* y *taggers*: todos `TerciodeMarte <111312600+TerciodeMarte@users.noreply.github.com>`. La cadena del usuario no aparece en ningún contenido, nombre ni mensaje (`git grep -i` sobre los 494 commits: 0). Las 12 imágenes originales ya no están (`git cat-file -e`: 0 de 12) |
| CA3 | Se conservan los commits, los merges y las etiquetas, y los tests pasan | ✅ en el ensayo | Antes y después: 494 commits, 26 merges y 25 etiquetas (con `v0.9.5` serán 26). El árbol de `HEAD` reescrito es idéntico al de la rama (mismo hash `f68c944…`), así que los tests de arriba valen para él |
| CA4 | Copia de seguridad restaurable | ✅ en el ensayo | `git bundle create --all` (17,5 MiB), `git bundle verify` correcto y clon desde el bundle con 494 commits y 25 etiquetas |
| CA5 | Repo con `main`, etiquetas, licencia, README y `SECURITY.md` | pendiente | Tras el merge |
| CA6 | Release `v0.9.5` con el instalador y su SHA-256 | pendiente | Tras el merge |
| CA7 | Instalación desde la release en una máquina limpia | pendiente | Tras publicar, con `clean-machine.ps1 -Url … -Sha256 …` |

## Code review
`/code-review` (medium) sobre `main...phase/25-publicacion-github`: 9 hallazgos.

| Hallazgo | Severidad | Resolución |
|---|---|---|
| `--history` veía una sola ruta por blob (`rev-list --objects`): un renombrado o un blob reutilizado ocultaba el nombre nuevo | alta | Corregido: las rutas salen de los diffs de todos los commits (`log --raw -m --root`); test nuevo |
| La fila de la fase 25 del roadmap tenía una celda de más (`||`) | media | Corregido |
| `clean-machine.ps1` empezaba con dos BOM | media | Corregido (un solo BOM) |
| `apply-replacements.py` no leía las reglas como `filter-repo` (primera `==>` en vez de la última, comentarios, `glob:`) | media | Corregido tras leer el código de `filter-repo`: también aplica antes todos los literales y después las regex, como él. Test nuevo |
| Mayúsculas no ASCII y cadenas UTF-16 en binarios | baja | UTF-16LE añadido y probado. Los patrones no ASCII se avisan (los nuestros son ASCII) |
| Ventana de binarios de 8000 bytes frente a los 8192 de `filter-repo` | baja | Corregido: 8192 en los dos scripts |
| `.public-strip-blobs.local` no estaba entre los ficheros prohibidos | baja | Corregido: se prohíbe cualquier `.public-*.local`; test nuevo |
| Descarga lenta con la barra de progreso de PowerShell 5.1 | baja | Corregido |
| `lint:scripts` repite la lista de rutas | baja | Justificado: los scripts anteriores (`owls.py`, `licenses.py`, `installer_art.py`) no pasan ruff y quedan fuera de esta fase; se lintan solo los nuevos |

## Retro
- **Cambios respecto a la spec**:
  - el usuario pidió quitar su usuario de Windows en cualquier parte, también dentro de otras palabras (una palabra del corpus de pruebas pasó a «la costra»). Esta misma validación la contenía al reescribir y `filter-repo` la sustituyó, así que la reescritura cubre también lo escrito después de la última comprobación del árbol;
  - también se buscan cadenas UTF-16 en los binarios.
- **Lo que no se esperaba**: 12 capturas de evidencias mostraban rutas con el usuario y una el email. Solo se ven revisando las imágenes, porque la comprobación de texto no las detecta.
- **Impacto en fases futuras**: `npm run check:public -- --history` antes de cada *push* al repo público. Los commits ya salen con el autor noreply. La fase 26 (instaladores firmados y GitHub Actions) puede añadir la comprobación del árbol a la CI.

## Cierre
- [x] OK del usuario para cerrar («continúa», 2026-11-02), con la suite del backend en verde
- [x] Versión `0.9.5` en los manifiestos, merge a `main` (`--no-ff`) y tag `v0.9.5`
- [x] Copia de seguridad (`D:\agentic_os-backup-2026-11-02\`: bundle verificado y restaurado, y copia de `.git`), reescritura y comprobaciones CA2–CA4 sobre el repo real: 499 commits, 28 merges y 26 etiquetas, igual que antes; `check-public --history --expect-identity` con 4183 blobs y 0 hallazgos; las 12 imágenes originales eliminadas; un único autor (noreply)
- [ ] Publicación: *push*, metadatos y release (CA5, CA6)
- [ ] Repo público tras la confirmación del usuario y CA7
- [ ] `docs/roadmap.md` actualizado
