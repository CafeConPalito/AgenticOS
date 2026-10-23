# ADR 0024: Skills versionadas, autoselección común a todos los CLIs y registros públicos

- **Estado**: propuesto (borrador; se completa con los spikes de la fase 17)
- **Fecha**: 2026-10-23
- **Contexto de decisión**: fase 17 ([spec](../phases/17-skills/spec.md) · [plan](../phases/17-skills/plan.md))

## Contexto
Los agentes tienen que usar skills (carpetas con `SKILL.md`):
- de una biblioteca local en tres niveles;
- elegidas solas según la tarea;
- con modos por agente y por etapa;
- con historial de cambios;
- con propuestas de los agentes;
- e instalables desde registros públicos.

Claude Code y Antigravity tienen su propio mecanismo de skills, pero cada uno a su manera. Los CLIs que vienen después (Codex y OpenCode, fase 21) tendrán el suyo o ninguno. Y la configuración del usuario no se puede tocar (ADR 0004).

## Decisión
1. **Almacén propio y versionado**:
   - cada skill es una lista de versiones;
   - cada versión es un *manifest* `{ruta: sha256}` sobre un almacén de ficheros por contenido en la carpeta de datos;
   - las versiones aceptadas no se borran;
   - restaurar crea una versión nueva;
   - los diffs se calculan con `difflib` en el formato del visor de la fase 11.

   No se usa git.
2. **Autoselección propia, igual para todos los CLIs**:
   - Agentic OS elige las candidatas comparando la tarea con «nombre + descripción» (vectores del modelo de la fase 14 o palabras clave);
   - las pone en una sección «Skills» del contexto, junto con las fijadas;
   - el agente carga las demás con las herramientas MCP `use_skill` y `read_skill_file`;
   - los ficheros se materializan por ejecución en su carpeta de datos.
3. **El mecanismo nativo es un añadido**: donde el spike lo confirme, las skills de la ejecución también se pasan al CLI por su propio mecanismo, por ejecución y sin tocar su configuración. Si un CLI no lo permite, la vía común basta.
4. **Modos**: Automática, Siempre y Nunca, por agente y por etapa. **Manda la etapa**; si no fija nada, el agente; por defecto, Automática.
5. **Propuestas como versiones `proposed`**: una skill nueva o una versión nueva de una que ya existe. Nada cambia hasta aprobarlas, y no se aprueba si hay *scripts* sin abrir.
6. **Registros detrás de un protocolo** (`popular` · `search` · `detail` · `fetch`):
   - la ficha enseña los ficheros de un *commit* fijo, y se instala exactamente eso;
   - las actualizaciones se avisan y nunca se aplican solas.

## Consecuencias
- ✅ El mismo comportamiento con Claude, `agy` y los CLIs futuros. Lo que se ofreció, lo que se cargó y la versión quedan registrados.
- ✅ El historial no depende de git y comparte ficheros entre versiones.
- ⚠️ El aislamiento de las skills personales del usuario depende de lo que permita cada CLI (spike S1/S2). Si un CLI las carga de todos modos, se avisa y no se toca su configuración.
- ⚠️ Las skills de terceros pueden traer código malicioso. La revisión de los *scripts* es obligatoria y las skills no cambian los permisos del agente, pero el riesgo no desaparece.
- ⚠️ Los registros cambian rápido. Cada fuente es un módulo aparte que se puede apagar.

## Alternativas descartadas
- **Solo el mecanismo nativo de cada CLI**: no sirve para los CLIs sin skills y no deja controlar la selección ni registrarla igual en todos.
- **Git como historial**: añade una dependencia y muchos repos pequeños sin aportar nada que no den `difflib` y el almacén por contenido.
- **Meter todas las skills en el contexto**: no escala y gasta tokens en skills que la tarea no necesita.
