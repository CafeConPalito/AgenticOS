# ADR 0031: Repositorio público con el historial reescrito

- **Estado**: propuesto
- **Fecha**: 2026-11-02
- **Fase**: 25

## Contexto
Agentic OS se publica en `CafeConPalito/AgenticOS`. El historial local (484 commits y 25 etiquetas) incluye datos personales:
- el email real del autor y su usuario de Windows en rutas, en evidencias de fases y en fixtures de tests;
- un email de relleno (`you@example.com`) como autor de todos los commits.

No incluye secretos reales. Los commits y las etiquetas sirven como registro de las fases, y los documentos de fase los citan.

## Decisión
1. Se publica el **historial completo, reescrito** con `git filter-repo`:
   - `--replace-text` sustituye el email y la ruta del usuario en todo el contenido de texto de todas las versiones;
   - `--mailmap` pone como autor y *committer* (y *tagger* de las etiquetas anotadas) `TerciodeMarte <111312600+TerciodeMarte@users.noreply.github.com>`.
2. **Sustituciones con contexto**: el usuario de Windows solo se cambia cuando forma parte de una ruta (`Users\…`, `Users/…`, `Users\\…`, `-Users-…`). Así no se tocan palabras que lo contienen, como «costra» en un corpus de pruebas.
3. **Comprobación** (`scripts/check-public.py`):
   - Los patrones personales se leen de un fichero local no versionado (`.public-check.local`). El repo no publica lo que busca.
   - Los patrones genéricos (tokens de API, claves privadas, ficheros prohibidos) sí están versionados.
   - Las excepciones (`scripts/public-allowlist.txt`) llevan cada una su motivo.
   - Se puede ejecutar sobre el árbol y sobre todo el historial antes de cualquier *push*.
4. **Al remoto se suben `main` y las etiquetas**, no las ramas `phase/NN-*`, porque `main` ya las contiene gracias a los merges `--no-ff`.
5. **Copia de seguridad** antes de reescribir: un `git bundle --all` y una copia de `.git`, fuera del repo. Es la única referencia a los hashes antiguos.

## Consecuencias
- Cambian todos los hashes. Los citados en los documentos de fase anteriores a la 25 no existen en el repo público; quedan solo en la copia de seguridad.
- `filter-repo` no modifica binarios. Una imagen con datos personales se edita en el árbol y su versión antigua se borra del historial con `--strip-blobs-with-ids`.
- Un clon o una rama con el historial antiguo no se debe volver a empujar. `filter-repo` quita el remoto `origin` y se vuelve a añadir después de reescribir.
- Los commits futuros usan el autor noreply, configurado en el `.git/config` del repo.
