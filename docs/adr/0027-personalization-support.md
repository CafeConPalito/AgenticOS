# ADR 0027: Personalización (temas y avatares) y registros para soporte

- **Estado**: aceptado (plan aprobado el 2026-10-27; aceptado al cerrar la fase 20)
- **Fecha**: 2026-10-27
- **Contexto de decisión**: fase 20 ([spec](../phases/20-personalizacion/spec.md) · [plan](../phases/20-personalizacion/plan.md))

## Contexto
La persona quiere cambiar el aspecto de toda la interfaz (no solo claro u oscuro), dar a cada agente una imagen propia y poder mandar los registros cuando algo falla. Los temas tienen que poder exportarse e importarse y sobrevivir a una reinstalación. Las fotos de los agentes no deben guardarse nunca enteras. Los registros pueden contener secretos de las conexiones y cuentas (fases 10 y 18), y no hay ningún servidor que los reciba.

## Decisión
1. **Los temas son datos**: un JSON (`agentic-os.theme` v1) con los valores de los *tokens* de `tokens.css`, el terminal, la tipografía, la densidad y el radio. Se aplican como variables CSS en `:root`; la clase `.dark` sigue la base del tema. Los temas propios guardan solo lo que cambian respecto al tema del que parten (`extends`). La elección y los temas propios viven en `app_state["appearance"]`; `localStorage` es solo una caché para pintar sin parpadeo.
2. **Ningún color fijo en los componentes**: todo sale de los *tokens*, con una lista corta de excepciones documentadas y un test que lo comprueba.
3. **Avatares**: `Agent.avatar` es nulo (iniciales), `owl:<id>` (galería incluida en la app) o `photo:<hash>`. El recorte se hace en la interfaz; el backend recibe solo el recorte, lo valida y lo reescribe a WebP 256 × 256 sin metadatos. La foto original no sale nunca del navegador ni se escribe en disco.
4. **Registros para soporte en local y en manos de la persona**: la app genera un `.zip` con los registros del backend y del *shell*, los errores recientes de la UI y un resumen del sistema, **sin** salidas de ejecuciones ni contenido del usuario, limpiado de secretos (patrones conocidos y los valores reales del almacén de secretos) antes de escribirlo. La persona lo revisa y lo adjunta a un correo que la app abre con `mailto`. Nada se envía solo; no hay telemetría.

## Consecuencias
- Cambiar un *token* o añadir uno nuevo obliga a darle valor en los temas incluidos; los propios lo heredan por `extends`.
- Los avatares se muestran por `agentId` desde la lista de agentes en caché, así que las entidades que solo llevan el nombre y el color del agente no necesitan cambiar su API.
- La limpieza de secretos es de mejor esfuerzo: por eso la persona ve qué se incluye y puede abrir el zip antes de enviarlo.

## Notas de implementación
- **Temas**: `GET/PUT /api/settings/appearance`; cinco temas incluidos con el contraste comprobado por test; los bloques de color fijos se pasaron a *tokens* y `no-hardcoded-colors.test.ts` lo vigila. Borrar un tema en uso vuelve al Oscuro navy o al Claro. **Contraste**: 4,5:1 para el texto y 3:1 para las etiquetas de botón sobre su color de acción (criterio WCAG de componentes); no se oscurece el rojo destructivo del Oscuro navy (3,9:1).
- **Avatares**: migración `0022_agent_avatar`; el recorte llega como cuerpo binario de `PUT /agents/{id}/avatar` y se sirve en `GET /avatars/<hash>.webp` con caché inmutable. Los 13 búhos son SVG propios generados por `scripts/owls.py`. `AgentAvatar` busca la imagen por `agentId`.
- **Acerca de**: `scripts/licenses.py` (Python puro) genera la lista de terceros y un test la vigila y comprueba la compatibilidad con la GPL; el texto de `LICENSE` y la lista se cargan bajo demanda.
- **Registros**: el filtro de `services/redact.py` actúa en cada manejador del registro; el zip añade los secretos guardados, correos y usuario. Los errores de la interfaz llegan con el *logger* `frontend`. La app de escritorio escribe `desktop.log` y su comando `bundle_logs` genera el zip aunque el backend esté caído (permiso `dialog:allow-save`).
