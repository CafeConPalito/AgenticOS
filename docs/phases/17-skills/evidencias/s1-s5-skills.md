# Fase 17 · Bloque 0 · Spikes S1–S5 (2026-10-23)

Scripts en `spikes/skills/`. Datos crudos en los JSON de esta carpeta (`s1-claude-*`, `s2-agy-*`, `s3-registries-*`, `s4-selection-*`, `s5-format-*`). Corpus de S4 y S5 en `spikes/out/skills-corpus/` (ignorado por git; se regenera con `s5_format.py`).

Entorno: Windows 11, Claude Code 2.1.309 (`haiku`, ~0,02 USD en total), `agy` 1.4.6 (`gemini-3.8-flash-high`).

## S1 · Claude Code
| Escenario | Skills que ve el modelo | Otros efectos |
|---|---|---|
| Lanzamiento actual (`--setting-sources project,local`, `--settings`, `--mcp-config --strict-mcp-config`) | Solo las **de serie** del CLI (13: `dataviz`, `code-review`, `simplify`, `init`…). **Ninguna** de las 23 de `~/.claude/skills` ni de los plugins del usuario | — |
| + `--plugin-dir <run>/plugin` | Las de serie + `agentic-os-run:aos-probe-plugin` (con el nombre del plugin delante) | — |
| + `--add-dir <dir>` con `.claude/skills/` | Las de serie + `aos-probe-adddir` (sin prefijo) | También da acceso a la carpeta |
| + `--safe-mode` | Solo las de serie: **pierde la del plugin** | **No se ejecutan nuestros *hooks*** (ni `Stop`) |
| + `--disable-slash-commands` | **Ninguna**, ni la nuestra | — |
| Carpeta de trabajo con `.claude/skills/` (el repo) | Las de serie + **la del repo** | — |
| Ídem con `--setting-sources local` o `""` | Sin la del repo | Tampoco carga el **`CLAUDE.md` del proyecto** |

- **Carga y registro**: con `--plugin-dir`, el modelo llama a la herramienta `Skill` con `{"skill": "agentic-os-run:aos-probe-plugin"}`, y el *hook* `PreToolUse` lo recibe con `tool_name = "Skill"`.
- **Scripts**: el modelo ejecuta el script con su ruta absoluta (`Bash`). Con `bypassPermissions` se ejecuta. Con `acceptEdits` pide permiso: en la app iría a la Inbox, como cualquier comando.
- **Configuración del usuario**: sin cambios en ningún escenario (`~/.claude.json`, `~/.claude/settings.json`, `~/.claude/skills`, `installed_plugins.json`).

**Conclusiones**
- Las skills personales ya quedan fuera con el lanzamiento actual: la decisión 1 de la spec se cumple sin tocar nada.
- Las del **repo** (`.claude/skills` del proyecto) entran por la fuente `project`. Quitarla también quita el `CLAUDE.md` del proyecto. **Hay que decidirlo** (ver «Cambios al diseño»).
- Las skills de serie del CLI no se pueden quitar sin quitar también las nuestras.
- Vía nativa: **`--plugin-dir`**, porque el prefijo del plugin evita choques con las de serie (p. ej. `code-review`) y no da acceso a más carpetas. `--safe-mode` queda descartado.

## S2 · Antigravity CLI (`agy`)
- **`skills/<nombre>/SKILL.md` dentro de `.agents/plugins/agentic-os/` se carga**: el modelo ve las 2 de serie (`agy-customizations`, `antigravity-guide`) más la nuestra.
- **Activación**: `agy` no tiene herramienta de skills. El modelo hace `read_file` del `SKILL.md` y luego `run_command` del script, que se ejecuta. El *hook* `PreToolUse` da `toolCall.name = "read_file"` y `args.Path` con la ruta, así que se registra mirando si la ruta es un `SKILL.md` de nuestro plugin. Hoy el *matcher* es `invoke_subagent` y hay que ampliarlo con `read_file`.
- **Aislamiento**: según la documentación de `agy` (skill de serie `agy-customizations`), carga las skills del workspace (`.agents/skills/`, subiendo hasta la raíz del repo), las globales (`~/.gemini/config/`) y las de serie. Los filtros de `skills.json` «nunca filtran lo heredado del entorno del usuario». **No se pueden apagar** sin tocar su configuración. Hoy esta máquina no tiene ninguna global.
- **Límites de `agy`**: el cuerpo del `SKILL.md` no puede pasar de **24 KB** y `name` tiene que coincidir con el nombre de la carpeta.
- **Configuración**: sin cambios.

## S3 · Registros públicos (sin cuenta)
| Fuente | Búsqueda | «Más usadas» | Ficheros | Versión | Seguridad | Límites |
|---|---|---|---|---|---|---|
| **skills.sh** | `GET /api/search?q=` (≥ 2 caracteres; id, `source` = repo, instalaciones; **sin descripción**). La API documentada `/api/v1` exige un *token* OIDC de Vercel, que una app de escritorio no tiene | No hay listado público sin consulta | `GET /api/download/{owner}/{repo}/{slug}`: JSON con todos los ficheros | No da *commit*: *hash* de los ficheros (como su CLI, `computeSnapshotHash`) | `GET /tele/audit?source=&skills=`: riesgo de tres analizadores («Gen», Socket con puntuación, Snyk) | No publicados |
| **`anthropics/skills`** | Filtrar la lista (20 skills) | — | API de GitHub: árbol en 1 petición (541 entradas) + `raw.githubusercontent.com` por fichero | *Commit* de `main` | — | 60 peticiones/hora sin *token*, 5 000 con *token* |
| **SkillsMP** | `GET /api/v1/skills/search?q=&sort=stars` (anónimo) | — | `githubUrl` → GitHub | *Commit* (vía GitHub) | — | **50 al día y 10 por minuto** sin clave. Las «estrellas» son las del **repo entero** (las de openclaw marcan 392 094), no sirven para saber qué skill se usa más |
| **ClawHub** | `GET /api/v1/search?q=` | `GET /api/v1/skills?sort=downloads` | `GET /api/v1/download?slug=&ownerHandle=` (zip) | Versión semántica con su registro de cambios | `isSuspicious` en la búsqueda. Los informes de VirusTotal y ClawScan **exigen iniciar sesión** | No publicados; 2–2,6 s por petición. Muchas skills son de OpenClaw (`hooks/openclaw/…`) |
| **LinklyAI/best-skills** (GitHub, CC BY 4.0, diario) | — | **CSV** `top-installs`, `best-100`, `official-100`, `trending-7d`… con instalaciones de skills.sh, ClawHub y SkillHub, y categoría | Por su `source` (skills.sh) o su repo | — | — | `raw.githubusercontent.com`; exige atribución |

**Conclusiones**
- «Más usadas» por defecto: el **CSV diario de `best-skills`**, con atribución.
- Búsqueda: **skills.sh** (instalaciones, más análisis de seguridad) y **`anthropics/skills`**, activadas por defecto. **SkillsMP** y **ClawHub** apagadas por defecto: la primera por su cuota y porque sus estrellas no dicen nada, la segunda porque su seguridad no es pública y por la campaña de enero.
- Las rutas de skills.sh no están documentadas (son las de su CLI, de código abierto): cada fuente va en su propio módulo, para poder cambiarla o apagarla si dejan de funcionar.

## S4 · Autoselección
- **Corpus**: 82 skills: las 76 de S5 (con familias casi iguales: 14 de Azure, 10 de Prisma y 13 de Remotion) más 6 propias en español.
- **Tareas**: 58: 48 con skill esperada (22 en español contra skills en inglés, 12 en español contra skills en español y 14 en inglés) y 10 sin ninguna adecuada.

| Método | hit@1 | **hit@3** | MRR |
|---|---|---|---|
| BM25 (sin modelo) | 0,729 | 0,812 | 0,795 |
| `multilingual-e5-small` (por defecto) | 0,812 | **0,917** | 0,873 |
| EmbeddingGemma 2 (q4) | 0,958 | **1,000** | 0,979 |
| `bge-m3` | 0,896 | **0,958** | 0,930 |
| centrado en la media / híbrido RRF / con el primer apartado del cuerpo | iguales o **peores** en los tres modelos (p. ej. híbrido con e5: 0,896) | | |

- **Sin modelo**, 7 de los 9 fallos de BM25 son de **idioma cruzado** (tarea en español, skill en inglés). En el mismo idioma acierta **25 de 26 (0,96)**.
- **Umbral** (puntuación mínima para ofrecer una skill):
  - e5 da cosenos muy juntos: las mejores puntuaciones de las tareas sin skill (0,82–0,85) se solapan con las de las tareas con skill (0,835–0,87). Con un mínimo de **0,83** se ofrece la correcta en 44 de 48 (92 %), pero en 8 de las 10 tareas sin skill también se ofrece alguna. Con 0,85 solo se ofrece la correcta en 36 de 48;
  - EmbeddingGemma 2: mínimo **0,62** → 47 de 48;
  - bge-m3: **0,52** → 46 de 48.
  - Como ofrecer una línea de más cuesta poco y perder una skill útil cuesta mucho, se prefiere el umbral bajo.

## S5 · Formato real
- **Muestra**: 76 skills distintas de las tres clasificaciones de `best-skills` (23 filas sin descarga porque no están en GitHub, p. ej. las de Feishu).
- **Cabecera**: todas tienen `name` y `description` y todas se leen con YAML. Hay 27 con dos puntos sin comillas en la descripción y 1 con descripción multilínea.
- **Campos extra**: `license` (35), `metadata` (35), `version` (12), **`disable-model-invocation`** (7), `allowed-tools` (5), `argument-hint`, `compatibility`, `hidden`…
- **Tamaños**:
  - `SKILL.md`: mediana de 1 342 *tokens*, percentil 90 de 2 849 y máximo de 7 026;
  - ficheros por skill: mediana de 6, **percentil 90 de 68** y máximo de 200;
  - bytes por skill: mediana de 20 KB, percentil 90 de 488 KB y máximo de 1,27 MB;
  - 1 skill pasa de los 24 KB de `agy`.
- **Ejecutables**: 15 de 76 (20 %) traen alguno (`.py`, `.sh`, `.ps1`, `.mjs`, `.ts`).

## S4b · Palabras sin modelo, por tamaño de biblioteca (bloque 3)
Script `spikes/skills/s4b_words.py`; datos en `s4b-words.json`. Con el mismo corpus y las mismas tareas, en subconjuntos aleatorios de 5, 10 y 20 skills que contienen la esperada (5 por tarea) y en el corpus entero:

| Variante | 5 | 10 | 20 | 82 |
|---|---|---|---|---|
| S4 (palabras tal cual, umbral absoluto 3,0) | 0,742 | 0,812 | 0,850 | 0,833 |
| Raíz de 5 letras sin tildes, absoluto 3,0 | 0,892 | 0,912 | 0,925 | 0,917 |
| **Raíz + umbral relativo 0,15** | **0,979** | **0,963** | **0,958** | **0,917** |
| Raíz + relativo 0,30 | 0,954 | 0,933 | 0,871 | 0,688 |

(hit@3 en las tareas con skill). El umbral relativo es la puntuación dividida por la mejor que podría sacar la consulta en esa biblioteca. Con 0,15 se filtran las tareas sin skill en el 64, 56, 42 y 10 % de los casos (para 5, 10, 20 y 82 skills): se ofrece alguna de más.

## S4c · Medido como el producto (bloque 11)
El test de calidad (CA5) con el producto daba con e5 un 77,5 % en las 3 primeras (85 % sin umbral), lejos del 91,7 % de S4. Hay dos causas:
1. **Lotes**: S4 calculaba los vectores en lotes, y el producto calcula cada texto solo. El relleno mueve el vector un poco (coseno de 0,9968 entre el mismo texto solo y en lote), y con e5 las puntuaciones de skills distintas están a milésimas.
2. **Idioma**: el corpus del test tiene más skills en español (7 de 20). e5 acerca las tareas en español a las skills en español aunque encaje mejor una en inglés.

`spikes/skills/s4c_single.py` (datos en `s4c-single.json`), con cada texto calculado solo:

| Corpus · modelo | Tal cual | **Consulta en los dos lados** | Centrado | Híbrido RRF |
|---|---|---|---|---|
| S4 (82) · e5 | 0,917 | **0,938** | 0,917 | 0,938 |
| Test (20) · e5 | 0,875 | **0,925** | 0,875 | 0,950 |
| S4 (82) · Gemma | 1,000 | **1,000** | 1,000 | 0,979 |
| Test (20) · Gemma | 1,000 | **1,000** | 1,000 | 0,950 |
| S4 (82) · bge-m3 | 0,958 | **0,958** | 0,958 | 0,958 |
| Test (20) · bge-m3 | 0,975 | **0,975** | 0,975 | 0,950 |

**Decisión**:
- las skills se calculan con el prefijo de **consulta**, igual que las tareas: es la similitud simétrica que recomienda e5. Mejora e5 y no cambia los otros dos modelos;
- el híbrido se descarta porque empeora Gemma;
- **umbrales recalibrados** (mínimo para ofrecer / «muy parecida»): e5 0,83 / 0,945, Gemma 0,60 / 0,87 y bge-m3 0,50 / 0,82. Con el mínimo, el acierto en las 3 primeras no baja en ningún corpus salvo bge-m3 en el de test (de 0,975 a 0,950). «Muy parecida» queda entre el p99,9 de las skills distintas y la paráfrasis más baja (e5 0,942 / 0,949; Gemma 0,854 / 0,883; bge-m3 0,777 / 0,864).
