# ADR 0024: Skills versionadas, autoselección común a todos los CLIs y registros públicos

- **Estado**: aceptado
- **Fecha**: 2026-10-24
- **Contexto de decisión**: fase 17 ([spec](../phases/17-skills/spec.md) · [plan](../phases/17-skills/plan.md) · [evidencias](../phases/17-skills/evidencias/s1-s5-skills.md))

## Contexto
Los agentes tienen que usar skills (carpetas con `SKILL.md`):
- de una biblioteca local en tres niveles;
- elegidas solas según la tarea;
- con modos por agente y por etapa;
- con historial de cambios;
- con propuestas de los agentes;
- instalables desde registros públicos;
- y con estadísticas de uso.

Claude Code y Antigravity tienen cada uno su mecanismo de skills. Los CLIs que vienen después (Codex y OpenCode, fase 29) tendrán el suyo o ninguno. Y la configuración del usuario no se puede tocar (ADR 0004).

## Decisión
1. **Almacén propio y versionado**:
   - cada skill es una lista de versiones;
   - cada versión es un *manifest* `{ruta: sha256}` sobre un almacén por contenido (`<datos>/skills/blobs`);
   - las versiones aceptadas no se borran y restaurar crea una versión nueva;
   - los diffs se calculan con `difflib`, en el formato del visor de la fase 11.

   No se usa git.
2. **Autoselección propia, igual para todos los CLIs**:
   - al lanzar una ejecución se eligen sus skills una sola vez y se guardan en `run_skills`, de donde se pinta la sección «Skills» en cada `get_context`;
   - candidatas por el coseno de «nombre + descripción», con skills y tareas calculadas como **consulta** (similitud simétrica, S4c) y un mínimo por modelo en el catálogo (e5 0,83 · Gemma 0,60 · bge-m3 0,50);
   - sin modelo, BM25 con palabras sin tildes recortadas a 5 letras y un mínimo relativo (0,15) que vale para 5 skills y para 80 (S4b);
   - el agente carga las demás con `use_skill` y `read_skill_file`;
   - los ficheros se copian a la carpeta de la ejecución para que los scripts tengan ruta.
3. **El mecanismo nativo es un añadido** (S1, S2):
   - Claude recibe esa carpeta como plugin de la sesión (`--plugin-dir`, nombre `aos`);
   - `agy` recibe una copia dentro de su plugin de workspace (sin los `SKILL.md` de más de 24 KB);
   - el *hook* `PreToolUse` registra la carga como nativa (la herramienta `Skill` de Claude; un `read_file` del `SKILL.md` en `agy`).
4. **Modos**: Automática, Siempre y Nunca, por agente y por etapa. **Manda la etapa**; si no fija nada, el agente; por defecto, Automática. `disable-model-invocation: true` hace que una skill solo se cargue si se pide.
5. **Propuestas como versiones `proposed`**:
   - pueden ser una skill nueva o una versión nueva de una que ya existe;
   - nada cambia hasta aprobarlas, y no se aprueba ni se instala si hay ejecutables sin abrir;
   - la huella de las rechazadas avisa al agente que insiste;
   - «muy parecida» se detecta con un umbral por modelo (e5 0,945 · Gemma 0,87 · bge-m3 0,82).
6. **Registros detrás de un protocolo** (`popular` · `search` · `fetch` · `latest`):
   - fuentes: la clasificación abierta de `LinklyAI/best-skills` (CC BY 4.0) para «más usadas», las rutas públicas de la CLI de skills.sh, `anthropics/skills` por GitHub, SkillsMP y ClawHub (las dos últimas apagadas por defecto), y cualquier URL de GitHub;
   - la vista previa se descarga en una revisión fija y es exactamente lo que se instala;
   - las actualizaciones se avisan y nunca se aplican solas.
7. **Estadísticas**: una consulta agregada sobre `run_skills` ⋈ `runs`, con las copias de nombres de etapa, pipeline y equipo (y las de agente, proyecto y cuenta de `runs`), para que sobrevivan a los borrados.

## Consecuencias
- ✅ El mismo comportamiento con Claude, `agy` y los CLIs futuros. Lo que se ofreció, lo que se cargó, por qué vía y en qué versión queda registrado.
- ✅ Las skills personales del usuario en Claude (`~/.claude/skills`) ya quedan fuera con `--setting-sources project,local`. Las del repositorio entran por la fuente `project`, junto al `CLAUDE.md`, y se tratan como código del proyecto (decisión del usuario).
- ⚠️ `agy` carga además las skills globales del usuario (`~/.gemini/config/`) y no se pueden apagar sin tocar su configuración: la ficha del agente lo avisa.
- ⚠️ Con e5 las puntuaciones de skills distintas están a milésimas: el relleno de un lote basta para cambiar el orden. Por eso todo se calcula de uno en uno y como consulta. EmbeddingGemma 2 y bge-m3 separan mucho mejor.
- ⚠️ Las rutas de skills.sh son las de su CLI, no una API documentada (la documentada exige OIDC de Vercel). Están en un módulo aparte que se puede cambiar o apagar.
- ⚠️ Las skills de terceros pueden traer código malicioso. La revisión de los ejecutables es obligatoria y las skills no cambian los permisos del agente, pero el riesgo no desaparece.

## Alternativas descartadas
- **Solo el mecanismo nativo de cada CLI**: no sirve para los CLIs sin skills y no deja controlar la selección ni registrarla igual en todos.
- **Git como historial**: añade una dependencia y muchos repos pequeños sin aportar nada que no den `difflib` y el almacén por contenido.
- **Meter todas las skills en el contexto**: no escala y gasta tokens en skills que la tarea no necesita.
- **Búsqueda híbrida (vector + palabras) con modelo**: mejora e5 en un corpus pero empeora Gemma (S4c).
- **`--safe-mode` de Claude para aislar**: apaga también los *hooks* de Agentic OS y la skill del plugin (S1).
