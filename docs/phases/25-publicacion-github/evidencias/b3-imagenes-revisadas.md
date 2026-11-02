# Fase 25, bloque 3: imágenes revisadas (CA1)

Revisión una a una, el 2026-11-02, de las 81 imágenes del repo que no son iconos ni búhos (`frontend/src/assets` y `desktop/src-tauri/icons` no se revisan). Cada ruta solo ha tenido una versión en el historial.

## Pixeladas (12): mostraban la ruta con el usuario de Windows; `ca2-agy.jpg` también el email
Se pixelan las zonas con bloques de 10 px. La versión anterior de cada una se quita del historial al reescribirlo (`--strip-blobs-with-ids`, con los ids guardados en `.public-strip-blobs.local`, que no se versiona).

- `docs/phases/02-dominio-crud/evidencias/ca6-proyecto-memoria.jpg`
- `docs/phases/02-dominio-crud/evidencias/ca6-proyecto-resumen.jpg`
- `docs/phases/02-dominio-crud/evidencias/ca6-proyectos-lista.jpg`
- `docs/phases/03-terminales/evidencias/ca1-ca3-claude-interviniendo.jpg`
- `docs/phases/03-terminales/evidencias/ca2-agy.jpg`
- `docs/phases/03-terminales/evidencias/ca4-pagina-y-dock.jpg`
- `docs/phases/04-adapters-mcp/evidencias/ca1-ca7-claude-completada.jpg`
- `docs/phases/04-adapters-mcp/evidencias/ca2-ca7-agy-completada.jpg`
- `docs/phases/08-empaquetado/evidencias/ca8-ajustes-1.jpg`
- `docs/phases/08-empaquetado/evidencias/ca8-ajustes-2.jpg`
- `docs/phases/22-temas-apariencia/evidencias/menu-ajustes.png`
- `docs/phases/22-temas-apariencia/evidencias/menu-ajustes-estrecho.png`

## Sin datos personales (69)
Los diseños usan datos ficticios («Marta», `marta@estudio.es`, `D:\proyectos\…`, `C:\Users\marta\…`).

- `backend/tests/fixtures/knowledge/captura_error.png`
- `docs/design/screenshots/01a-dashboard-oscuro.png`
- `docs/design/screenshots/01b-dashboard-claro.png`
- `docs/design/screenshots/02-agentes-lista.png`
- `docs/design/screenshots/03a-agente-general.png`
- `docs/design/screenshots/03b-agente-ejecucion.png`
- `docs/design/screenshots/03c-agente-instrucciones.png`
- `docs/design/screenshots/03d-agente-borrador-arquitecto.png`
- `docs/design/screenshots/04-crear-agente-arquitecto.png`
- `docs/design/screenshots/05-proyectos-lista.png`
- `docs/design/screenshots/06a-proyecto-resumen.png`
- `docs/design/screenshots/06b-proyecto-pipeline.png`
- `docs/design/screenshots/06c-proyecto-memoria.png`
- `docs/design/screenshots/07a-tablero-por-estado.png`
- `docs/design/screenshots/07b-tablero-por-etapa.png`
- `docs/design/screenshots/07c-tablero-colas-por-agente.png`
- `docs/design/screenshots/08-conocimiento-y-skills.png`
- `docs/design/screenshots/09a-detalle-tarea-observando.png`
- `docs/design/screenshots/09b-detalle-tarea-interviniendo.png`
- `docs/design/screenshots/09c-detalle-tarea-claro.png`
- `docs/design/screenshots/10-inbox.png`
- `docs/design/screenshots/11-consumo.png`
- `docs/design/screenshots/12-ajustes.png`
- `docs/design/screenshots/13a-terminal-acoplada.png`
- `docs/design/screenshots/13b-paleta-de-comandos.png`
- `docs/design/v2/screenshots/01a-lateral-cuentas-expandidas-v2.png`
- `docs/design/v2/screenshots/01b-lateral-cuentas-plegadas-v2.png`
- `docs/design/v2/screenshots/03a-inicio-v2.png`
- `docs/design/v2/screenshots/03b-inicio-vacio-v2.png`
- `docs/design/v2/screenshots/03c-inicio-aviso-clis-v2.png`
- `docs/design/v2/screenshots/03d-inicio-claro-v2.png`
- `docs/design/v2/screenshots/04a-nueva-tarea-desde-cabecera-v2.png`
- `docs/design/v2/screenshots/04b-nueva-tarea-desde-agente-v2.png`
- `docs/design/v2/screenshots/05-nuevo-agente-v2.png`
- `docs/design/v2/screenshots/06-nuevo-proyecto-v2.png`
- `docs/design/v2/screenshots/07a-paleta-resultados-v2.png`
- `docs/design/v2/screenshots/07b-paleta-buscar-tarea-v2.png`
- `docs/design/v2/screenshots/08-ayuda-atajos-v2.png`
- `docs/design/v2/screenshots/09-ajustes-v2.png`
- `docs/phases/00-fundaciones/evidencias/ca5-dev-desktop.png`
- `docs/phases/00-fundaciones/evidencias/ca6-release-sidecar.png`
- `docs/phases/02-dominio-crud/evidencias/ca5-agente-ejecucion.jpg`
- `docs/phases/02-dominio-crud/evidencias/ca5-agente-general.jpg`
- `docs/phases/02-dominio-crud/evidencias/ca5-agentes-lista.jpg`
- `docs/phases/02-dominio-crud/evidencias/ca6-proyecto-nuevo.jpg`
- `docs/phases/07-consumo/evidencias/ca8-consumo.jpg`
- `docs/phases/07-consumo/evidencias/ca8-dashboard-limites.jpg`
- `docs/phases/20-personalizacion/evidencias/appearance/apariencia.png`
- `docs/phases/20-personalizacion/evidencias/appearance/editor.png`
- `docs/phases/20-personalizacion/evidencias/avatars/galeria.png`
- `docs/phases/20-personalizacion/evidencias/avatars/inicio.png`
- `docs/phases/20-personalizacion/evidencias/installer/inst-license.png`
- `docs/phases/20-personalizacion/evidencias/installer/inst-welcome.png`
- `docs/phases/20-personalizacion/evidencias/owls/final.png`
- `docs/phases/20-personalizacion/evidencias/owls/preview.png`
- `docs/phases/20-personalizacion/evidencias/themes/contrast.png`
- `docs/phases/20-personalizacion/evidencias/themes/graphite.png`
- `docs/phases/20-personalizacion/evidencias/themes/light.png`
- `docs/phases/20-personalizacion/evidencias/themes/navy.png`
- `docs/phases/20-personalizacion/evidencias/themes/warm.png`
- `docs/phases/22-temas-apariencia/evidencias/galeria-dracula.png`
- `docs/phases/22-temas-apariencia/evidencias/galeria-oscuros.png`
- `docs/phases/22-temas-apariencia/evidencias/galeria-solarized-light.png`
- `spikes/knowledge/corpus/captura_error.png`
- `spikes/knowledge/corpus/images/captura_error.png`
- `spikes/knowledge/corpus/images/diagrama_flujo.png`
- `spikes/knowledge/corpus/images/grafico_barras.png`
- `spikes/knowledge/corpus/images/organigrama.png`
- `spikes/knowledge/corpus/images/tabla_planes.png`
