# Fase 25: Publicación en GitHub · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: borrador

## Lo que ya se sabe (revisado al escribir el plan)
- **Datos personales en texto**: 16 ficheros fuera de las evidencias (14 fixtures de `backend/tests/fixtures/`, `test_adapters.py` y `spikes/knowledge-graph/corpus.py`) y los de las evidencias de las fases 00, 01, 04, 05–08, 10, 12, 13, 17–19.
  - El usuario de Windows aparece como `C:\Users\…`, `C:\\Users\\…`, `/c/Users/…` y `C--Users-…`, que es la forma de las carpetas de proyecto de Claude Code.
  - Esa misma cadena forma parte de «costra» en el corpus del grafo de conocimiento, así que **no se puede sustituir sin contexto**.
- **Imágenes**: 88 en el árbol, y las mismas 88 rutas son todas las que ha habido en el historial:
  - 24 en `docs/design/screenshots`, 14 en `docs/design/v2` y 26 en las evidencias de la fase 20, más las de las fases 00, 02–04, 07, 08 y 22;
  - iconos y búhos (`frontend/src/assets`, `desktop/src-tauri/icons`), que no tienen riesgo;
  - las 6 del corpus de conocimiento de los spikes.
- **Etiquetas**: las 25 son anotadas, así que `filter-repo` reescribe también al *tagger*.
- **Herramientas**: `uv` y `winget` están disponibles; `gh` y `git-filter-repo` no.
- **Prueba en limpio**: `scripts/clean-machine.ps1` abre Windows Sandbox con el instalador local mapeado en modo de solo lectura.

## Diseño
Las decisiones están en el [ADR 0031](../../adr/0031-public-repository-history-rewrite.md).

### `scripts/check-public.py`
Es Python de la biblioteca estándar y se ejecuta con `uv run --project backend python scripts/check-public.py [--history]`.
- **Patrones**:
  - genéricos, versionados: tokens `sk-ant-`, `ghp_`/`github_pat_`, `AKIA…`, `xox[bp]-`, cabeceras `BEGIN … PRIVATE KEY`;
  - personales, leídos de `.public-check.local` (un patrón por línea; ignorado por git). Si ese fichero no existe, el script avisa y solo usa los genéricos.
- **Ficheros prohibidos**: `.env*`, `*.db`, `*.sqlite`, `spikes/out/`, `*.pfx`/`*.p12`, `*.pem`/`*.key`.
- **Árbol**: recorre `git ls-files` y lee cada fichero de texto. Los binarios se saltan y se listan aparte.
- **Historial** (`--history`): recorre todos los *blobs* de todas las referencias (`git rev-list --objects --all` y `git cat-file --batch`). Comprueba además los autores, los *committers* y los *taggers*, y los mensajes de commit y de etiqueta.
- **Excepciones**: `scripts/public-allowlist.txt`, con líneas `ruta<TAB>patrón<TAB>motivo`. Ahí van los tokens falsos de `test_support.py` y `desklog.rs`.
- **Salida**: un hallazgo por línea (`ruta:línea` o `blob <ruta> en <commit>`) y código de salida 1 si hay alguno.

### Sustituciones
Se usan las mismas en el árbol (bloque 2) y en el historial (bloque 6). El fichero `.public-replacements.local` (ignorado por git) tiene el formato de `--replace-text`, con reglas `regex:`:
- el email real (cubre también `166m<email>`) → `usuario@example.com`;
- `(Users[\\/]{1,2})<usuario>` → `\1usuario`;
- `(Users-)<usuario>` → `\1usuario`;
- `(/c/Users/)<usuario>` → `\1usuario`.

`scripts/apply-replacements.py` aplica ese fichero al árbol de trabajo en el bloque 2, para que el árbol y el historial queden igual.

### Prueba en limpio desde la release
`clean-machine.ps1` recibe `-Url`:
- descarga el instalador a una carpeta temporal y comprueba el SHA-256 con el valor publicado en la release;
- lo mapea en el Sandbox igual que ahora.

## Archivos
| Archivo | Cambio |
|---|---|
| `scripts/check-public.py` | nuevo |
| `scripts/apply-replacements.py` | nuevo |
| `scripts/public-allowlist.txt` | nuevo |
| `scripts/tests/test_check_public.py` | nuevo |
| `.gitignore` | `.public-check.local`, `.public-replacements.local` |
| `package.json` | `check:public`, `test:scripts` (dentro de `test`) |
| `backend/tests/fixtures/**`, `backend/tests/test_adapters.py`, `spikes/knowledge-graph/corpus.py`, `docs/phases/*/evidencias/**` | datos sustituidos |
| imágenes con datos personales (si las hay) | recortadas o pixeladas |
| `README.md` | instalación desde la release, párrafo en inglés, versión no fija |
| `SECURITY.md` | nuevo |
| `scripts/clean-machine.ps1` | `-Url` y comprobación de SHA-256 |
| `docs/adr/0031-public-repository-history-rewrite.md` | nuevo |
| `package.json`, `tauri.conf.json`, `Cargo.toml`, `pyproject.toml`, `__init__.py` | versión `0.9.5` al cerrar |

## Tareas (en orden)
**Bloque 0: herramientas**
1. [ ] Instalar `git-filter-repo` (`uv tool install git-filter-repo`) y `gh` (`winget install GitHub.cli`).
2. [ ] Configurar en el repo el autor noreply (`git config user.email`) para todos los commits de esta fase en adelante.

**Bloque 1: comprobación**
3. [ ] `check-public.py` con sus tests (patrones, excepciones, ficheros prohibidos, binarios, modo historial sobre un repo temporal), `public-allowlist.txt` y los dos ficheros locales.
4. [ ] Ejecutarlo sobre el árbol y el historial actuales y guardar la lista de hallazgos de partida (sin los datos) en las evidencias.

**Bloque 2: limpieza del árbol**
5. [ ] `apply-replacements.py` y su ejecución sobre el árbol.
6. [ ] Suite del backend (por tandas, con el progreso en `backend/.test-progress.log`) y de los spikes. Corregir los tests que comparen rutas o emails literales.
7. [ ] `check-public.py` en verde sobre el árbol.

**Bloque 3: imágenes**
8. [ ] Revisar una a una las imágenes de `docs/` y de los spikes (no hace falta con los iconos ni los búhos). Recortar o pixelar las que tengan datos personales y anotar sus *blob ids* antiguos para quitarlos del historial.
9. [ ] Lista de imágenes revisadas en las evidencias (CA1).

**Bloque 4: documentación del repo**
10. [ ] README: párrafo en inglés, instalación desde *Releases* con la comprobación del SHA-256, SmartScreen, CLIs, compilación desde el código.
11. [ ] `SECURITY.md`.
12. [ ] `clean-machine.ps1 -Url`.

**Bloque 5: validación** (antes del merge)
13. [ ] Lint y suites completas en verde, `/code-review` resuelto, `validacion.md` con CA1 y un ensayo de la reescritura (bloque 6) sobre un clon temporal, con CA2–CA4 medidos en ese clon. → ⛔ OK del usuario.

**Bloque 6: cierre y reescritura** (después del OK)
14. [ ] Versión `0.9.5` en los manifiestos, merge `--no-ff` a `main` y tag `v0.9.5`.
15. [ ] Copia de seguridad (`git bundle create … --all`, `git bundle verify` y copia de `.git`) en `D:\agentic_os-backup-<fecha>\`.
16. [ ] `git filter-repo --replace-text .public-replacements.local --mailmap <mailmap> [--strip-blobs-with-ids …]`.
17. [ ] `check-public.py --history` en verde; mismos commits y etiquetas que antes; lint y suite sobre el resultado (CA2–CA4).

**Bloque 7: publicación**
18. [ ] `gh auth login` (lo hace el usuario), `git remote add origin`, *push* de `main` y `--tags` al repo privado.
19. [ ] Metadatos del repo con `gh repo edit` (descripción, *topics*, web).
20. [ ] `npm run build:desktop`, SHA-256 del instalador y `gh release create v0.9.5 --prerelease` con el instalador, el fichero `.sha256` y las notas de las fases 21–25.
21. [ ] Revisión del usuario en privado → ⛔ confirmación → `gh repo edit --visibility public`.
22. [ ] CA7 en Windows Sandbox con `clean-machine.ps1 -Url` desde la release pública.
23. [ ] Completar `validacion.md` (CA5–CA7) y actualizar el roadmap. Esos commits se hacen ya sobre el historial reescrito, con el autor noreply, y se empujan.

## Tests previstos
| Test | Cubre |
|---|---|
| `test_check_public.py`: detecta los patrones genéricos y los locales, respeta las excepciones, marca los ficheros prohibidos, salta los binarios | CA1 |
| `test_check_public.py`: modo historial en un repo temporal con un secreto en un commit antiguo, en un autor y en un mensaje de etiqueta | CA2 |
| ensayo de `filter-repo` en un clon: `check-public --history`, recuento de commits y etiquetas, suite en verde | CA2, CA3 |
| `git bundle verify` y clon desde el bundle | CA4 |
| `gh repo view`, `gh release view`, SHA-256 descargado | CA5, CA6 |
| Windows Sandbox desde la release pública | CA7 |

## Decisiones (ADR)
- [ADR 0031](../../adr/0031-public-repository-history-rewrite.md): historial completo reescrito con `filter-repo`, sustituciones con contexto, comprobación con patrones locales no versionados y publicación solo de `main` y de las etiquetas.
- La release `v0.9.5` sale como *pre-release* porque es anterior a la 1.0. No respondiste a la pregunta abierta de la spec, así que se queda la propuesta.
