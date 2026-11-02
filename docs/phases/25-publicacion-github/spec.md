# Fase 25: Publicación en GitHub · Spec

- **Estado**: aprobada (2026-11-02)
- **Rama**: `phase/25-publicacion-github`

## Objetivo
Publicar Agentic OS en un repositorio público de GitHub, [CafeConPalito/AgenticOS](https://github.com/CafeConPalito/AgenticOS):
- con su historial completo y sus etiquetas;
- sin datos personales ni secretos;
- con un README que explique cómo descargarlo e instalarlo;
- con una release `v0.9.5` de la que cualquiera pueda descargar el instalador de Windows.

## Punto de partida
- **Repositorio local**: 484 commits y 25 etiquetas (`v0.1.0`…`v0.9.4`), 17 MiB empaquetados. Sin remoto configurado.
  - Las ramas `phase/NN-*` ya están fusionadas en `main` con `--no-ff`.
- **Repositorio remoto**: `CafeConPalito/AgenticOS` existe, está vacío y no es público (la API devuelve 404 sin sesión).
- **Licencia**: `LICENSE` es la GNU GPLv3, que GitHub detecta sola.
- **Secretos**: no hay ninguno real en el árbol ni en el historial. Solo hay tokens falsos en los tests del filtrado de logs (`test_support.py`, `desklog.rs`).
- **Datos personales**: hay unos 35 ficheros con datos reales, todos en evidencias de fases (`docs/phases/*/evidencias/`), en fixtures de tests (`backend/tests/fixtures/`) y en `spikes/knowledge-graph`. Contienen:
  - el email real del usuario, también con la secuencia de color ANSI delante (`166m<email>`);
  - el usuario de Windows en rutas (`C:\Users\<usuario>\…`, `/c/Users/<usuario>/…`) y, como subcadena, dentro de una palabra del corpus de pruebas.

  Las demás direcciones (`marta.personal@…`, `marta@estudio.es`, `trabajo@empresa.com`…) son datos de ejemplo, y `contacto@cafeconpalito.com` es el contacto público del proyecto.
- **Autor de los commits**: `terciodemarte <you@example.com>`, un email de relleno que GitHub no asocia a ninguna cuenta.
- **Imágenes**: hay capturas en `docs/design/` y en las evidencias, y no se han revisado. Las de cuentas y CLIs (fases 07, 10, 20…) pueden mostrar un email o una ruta.
- **README**: explica la instalación con un `.exe` suelto de la `0.9.0`. No dice de dónde se descarga.
- **Herramientas**: en esta máquina no están `gh` (el CLI de GitHub) ni `git-filter-repo`.
- **Instalador**: `npm run build:desktop` genera el instalador NSIS, sin firmar (la firma es la fase 26). `scripts/clean-machine.ps1` lo prueba en Windows Sandbox.

## Alcance
### Dentro
1. **Limpieza del árbol actual**:
   - En las evidencias, las fixtures y los spikes, el email real pasa a `usuario@example.com` y el usuario de Windows a `usuario`. Así, `C:\Users\usuario\…` sigue siendo una ruta válida y los tests que la usan siguen pasando.
   - Revisión de todas las imágenes del repo. Las que muestren datos personales se recortan, se pixelan o se quitan.
   - Se conservan las evidencias, los spikes y las capturas de diseño, que están enlazados desde las fases y los ADRs. Ocupan poco (unos 18 MiB `docs/` y menos de 1 MiB los spikes versionados).
2. **Comprobación automática** (`scripts/check-public.py`, para usarla también en el futuro): busca en el árbol y en todo el historial patrones de datos personales y de secretos. Los patrones de datos personales salen de una lista local no versionada, para no publicar los datos que se buscan. También busca ficheros prohibidos (`.env`, `*.db`, `spikes/out/`…). Falla si encuentra algo, salvo lo que esté en una lista de excepciones con su motivo (los tokens falsos de los tests).
3. **Autor**: `TerciodeMarte <111312600+TerciodeMarte@users.noreply.github.com>`, que liga los commits a la cuenta sin publicar el email. Se configura en el repo para los commits futuros.
4. **README**:
   - instalación descargando el instalador de la última release (enlace a *Releases*, sin una versión fija);
   - aviso de SmartScreen mientras el instalador no esté firmado;
   - requisitos de los CLIs;
   - compilación desde el código fuente;
   - un párrafo inicial en inglés que diga qué es la app y que la interfaz está en español.

   Se añade también un `SECURITY.md` mínimo que explica cómo avisar de una vulnerabilidad (por email al contacto del proyecto, no en un issue público).
5. **Cierre de la fase y reescritura del historial**. Tras el OK de la validación se hace el merge a `main` y el tag `v0.9.5`, y la versión de la app sube a `0.9.5`. Después:
   - copia de seguridad completa (`git bundle --all` y una copia de la carpeta `.git`), fuera del repo;
   - `git filter-repo` sobre todo el historial: sustituye el email y la ruta en todo el contenido y cambia el autor con un *mailmap*. Se conservan los commits, los merges y las 26 etiquetas, aunque con hashes nuevos;
   - `check-public.py` en verde sobre el resultado y la suite de tests en verde.
6. **Publicación**:
   - se instala `gh` y el usuario inicia sesión con `gh auth login`;
   - *push* de `main` y de todas las etiquetas. Las ramas `phase/NN-*` se quedan en local, porque ya están dentro de `main`;
   - metadatos del repo: descripción, *topics*, web, e *issues* activados;
   - release `v0.9.5`, marcada como *pre-release*, con el instalador `Agentic OS_0.9.5_x64-setup.exe`, su SHA-256 y las notas de las fases 21–25;
   - el repo pasa a público solo cuando el usuario lo confirme, después de ver el resultado en privado.
7. **Prueba en una máquina limpia**: en Windows Sandbox se descarga el instalador desde la release pública, se comprueba su SHA-256, se instala y la app arranca con su backend.

### Fuera
- Firma de código, instaladores de macOS y Linux, GitHub Actions y winget (fase 26).
- Traducir al inglés la documentación o la interfaz.
- Plantillas de *issues* y de *pull requests*, `CONTRIBUTING.md`, código de conducta y GitHub Pages.
- Cambios en la app, salvo la subida de versión.

## Historias de usuario
- Como autor, quiero publicar el código con su historial sin exponer mi email ni mi usuario de Windows.
- Como usuario nuevo, quiero entrar en el repo, entender qué es la app y descargar el instalador de la última versión sin compilar nada.
- Como usuario, quiero comprobar que el instalador que descargo es el publicado (SHA-256).

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | El árbol de `main` no contiene el email real, el usuario de Windows ni secretos, y las imágenes revisadas no muestran datos personales | `check-public.py` en verde sobre el árbol; lista de imágenes revisadas en la validación |
| CA2 | Todo el historial publicado (todos los commits y etiquetas) pasa la misma comprobación, y todos los commits tienen el autor noreply | `check-public.py --history` en verde; `git log --format='%an <%ae>' \| sort -u` |
| CA3 | El historial reescrito conserva los commits, los merges de fase y las 26 etiquetas, y la suite de tests pasa sobre él | recuento de commits y etiquetas antes y después; suite del backend y del frontend en verde |
| CA4 | Existe una copia de seguridad del repo previa a la reescritura que se puede restaurar | `git bundle verify` y clon de prueba desde el bundle |
| CA5 | El repo `CafeConPalito/AgenticOS` tiene `main` y las etiquetas, licencia GPLv3 detectada, README con la instalación y `SECURITY.md` | revisión en github.com y `gh repo view` |
| CA6 | La release `v0.9.5` tiene el instalador descargable, su SHA-256 y las notas | `gh release view v0.9.5`; SHA-256 del fichero descargado igual al publicado |
| CA7 | En una máquina limpia se descarga el instalador de la release, se instala y la app arranca con su backend | Windows Sandbox (`clean-machine.ps1` adaptado a descargar de la release) con capturas |

## Prerrequisitos
- Fase 24 cerrada (`v0.9.4`).
- Permiso de escritura del usuario en `CafeConPalito/AgenticOS` e inicio de sesión con `gh auth login`, que hace el usuario.
- `git-filter-repo` (con `uv tool install git-filter-repo`) y `gh` (con `winget install GitHub.cli`).

## Riesgos y preguntas abiertas
- **La reescritura cambia todos los hashes.** Los hashes citados en los documentos de fase y en el roadmap dejarán de existir. Propuesta: no se tocan; la copia de seguridad conserva el historial original.
- **Las rutas y el email sustituidos en fixtures de tests** pueden romper algún test que los compare con su valor literal. Se corrigen en el bloque de limpieza, antes de reescribir.
- **Datos en binarios**: `filter-repo` solo sustituye texto. En las imágenes, y en las versiones antiguas de las que se cambien, el dato sigue en el historial. Si alguna lo muestra, hay que quitar el blob del historial (`--strip-blobs-with-ids`).
- **Otras ramas o clones** con el historial antiguo (otras máquinas, worktrees) no deben empujarse después al remoto.
- **Pre-release**: se marca `v0.9.5` como *pre-release* porque es anterior a la 1.0. ¿Prefieres que salga como release normal («Latest»)?
