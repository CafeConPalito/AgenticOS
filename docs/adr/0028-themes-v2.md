# ADR 0028: Temas v2 (desde cero, fuentes del sistema y temas de terceros)

- **Estado**: propuesto (plan aprobado el 2026-10-31; se acepta al cerrar la fase 22)
- **Fecha**: 2026-10-31
- **Contexto de decisión**: fase 22 ([spec](../phases/22-temas-apariencia/spec.md) · [plan](../phases/22-temas-apariencia/plan.md))

## Contexto
El [ADR 0027](0027-personalization-support.md) dejó los temas como datos (`agentic-os.theme` v1). Ahí un tema propio siempre parte de otro (`extends`) y elige entre cuatro fuentes incluidas. El usuario quiere:
- crear temas desde cero con cualquier fuente instalada;
- tener muchos más temas incluidos, entre ellos los conocidos de VS Code;
- dejar de tener un cambio claro/oscuro y «Seguir al sistema», que no encajan con muchos temas.

Hay ficheros v1 exportados y documentos de apariencia guardados que tienen que seguir funcionando.

## Decisión
1. **Formato v2, compatible con la v1.** Todo v1 es un v2 válido: `version` admite 1 o 2 y se escribe siempre 2. `extends` pasa a ser opcional; un tema sin él parte del juego base de su `base`, y así se representa un tema «desde cero».
2. **`font_family`**: el nombre de una fuente del sistema, que tiene prioridad sobre `font`. Solo admite letras, cifras, espacios y `.-_'&()+`, hasta 80 caracteres. Así puede ir entre comillas en `--app-font` sin abrir la puerta a inyectar CSS. Detrás va siempre la fuente del sistema, de modo que una fuente que falta no rompe nada.
3. **Lista de fuentes desde el *shell***: un comando de Tauri, `system_fonts`, con `fontdb`, que recorre las fuentes del sistema y las del usuario. En el navegador se usa `queryLocalFonts` si está disponible y, si no, se escribe el nombre a mano. El frontend comprueba con un *canvas* que cada familia se pinta por su nombre: así descarta las fuentes variables con instancias con nombre y avisa de las fuentes que faltan.
4. **Adiós a «Seguir al sistema» sin perder datos**: el documento de apariencia queda con `theme` y `custom`. El backend sigue aceptando los documentos antiguos. Si traen `mode: "system"`, los entrega con el campo de solo lectura `legacy_follow`. La interfaz elige entonces el tema que se estaba viendo y guarda el documento nuevo; si no, descarta los campos viejos.
5. **Temas de terceros generados desde su paleta**: los temas incluidos nuevos se escriben como una paleta corta y `fromPalette` deriva todos los *tokens*. Si un color no llega al contraste de la app, `ensureContrast` lo ajusta lo mínimo. Solo entran temas con licencia libre. Su autor, licencia y origen, y el hecho de que es una adaptación, salen en Acerca de (`theme/credits.ts`), y un test exige el crédito.

## Consecuencias
- Un tema exportado ahora no se abre en la `v0.9.1` o anteriores, que solo conocen la v1. Es aceptable, porque la app no se ha publicado.
- Los temas incluidos no copian los temas de VS Code: toman sus colores y los reparten por los *tokens* de la app. El nombre original se mantiene para que se reconozcan.
- Añadir un tema incluido obliga a añadir su id en el backend; un test compara las dos listas a través de `generated/builtin-themes.json`.
