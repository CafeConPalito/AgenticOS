# Fase 21: Correcciones de la prueba · Spec

- **Estado**: aprobada (2026-10-29)
- **Rama**: `phase/21-correcciones-prueba`

## Objetivo
Corregir los fallos que encontró el usuario al instalar y probar la `v0.9.0` (2026-10-29), antes de seguir con las mejoras de las fases 22–24 y la publicación en GitHub. Es una fase **solo de fallos**: cada punto es algo que hoy no funciona como se espera. Las peticiones de funcionalidad nueva de la misma lista van en las fases 22–24.

## Punto de partida
- El instalador NSIS (fase 20, enmienda 1) usa la imagen de la app (`desktop/src-tauri/windows/header.bmp`, `sidebar.bmp`, `hooks.nsh`) con fondo navy.
- El Arquitecto (fase 19) conversa en un CLI interactivo que cuenta como ejecución.
- Exportar agente (fase 19) y exportar tema (fase 20) generan un fichero desde la interfaz.
- Ajustes está agrupado en secciones con menú lateral (fase 20); los modelos locales se gestionan en Ajustes › Modelos locales (fases 14 y 16) y el micrófono en Ajustes de dictado (fase 16).
- El avatar del agente se elige entre búhos o una foto encuadrada (fase 20).
- Los pipelines con ramas (fase 13) exigen en cada rama de una bifurcación una condición o «Siempre se toma».

## Alcance
### Dentro
**A. Instalador**
1. El instalador muestra el **icono de la app**, tanto en el propio `.exe` del instalador como en sus ventanas.
2. Los textos de la **última pantalla** («Ejecutar Agentic OS», «Crear acceso directo en el escritorio») se leen bien sobre el fondo del instalador; hoy salen en negro.

**B. Ejecuciones del Arquitecto**
3. Las ejecuciones del Arquitecto aparecen en el **listado de Ejecuciones**, igual que en el contador, y se distinguen como del Arquitecto.

**C. Exportar**
4. **Exportar agente** guarda el fichero. Hoy no hace nada.
5. **Exportar tema** guarda el fichero. Hoy tampoco hace nada.

En la app de escritorio se abre «Guardar como» y se avisa de dónde quedó el fichero; en el navegador se descarga.

**D. Ajustes**
6. Pulsar **Limpieza** en el menú lateral de Ajustes ya no desplaza toda la página. La sección se muestra dentro de su zona, y la cabecera y la navegación siguen a la vista y funcionan.
7. **Modelos locales**: un modelo solo sale «En uso» si está descargado y elegido. Si no está descargado, el que la app recomienda para cada uso sale como **«Aconsejado»**, con el botón para descargarlo. Hoy salen «En uso» multilingual-e5-small, Gemma 4 E2B y Whisper small sin haberlos descargado.
8. **Micrófonos**: Ajustes lista los micrófonos de Windows y deja elegir uno, también en la app instalada. Si falta el permiso, se dice cómo darlo.

**E. Agentes y equipos**
9. En la ficha del agente, las ventanas de **Conocimiento, Skills y Conexiones** ocupan lo que necesitan. Ya no quedan muy abajo ni obligan a hacer scroll cuando están vacías.
10. El **selector de foto** del agente carga la imagen, la muestra para encuadrarla y la guarda. Hoy se pone todo verde y no funciona.
11. Se puede **crear un equipo** aunque no haya ningún agente; los agentes se añaden después.

**F. Pipelines**
12. Las **ramas sin condición** de una bifurcación se toman siempre por defecto: guardar un pipeline ya no exige marcar «Siempre se toma». El editor explica en la propia rama qué significa: sin condición, la rama se hace siempre, en paralelo con las demás.

### Fuera
- Selector claro/oscuro, filtro de temas, modo lectura, temas de cero con fuentes del sistema y temas nuevos (fase 22).
- Accesos directos en Inicio, terminal con un CLI independiente, logos y «Añadir CLI» con instalación desde la app, y transcripción en «Probar micrófono» (fase 23).
- Foto del proyecto, plantilla de pipeline «Desarrollo», plantillas de agentes nuevas, y el Arquitecto creando equipos y pipelines (fase 24).
- Fallos nuevos que aparezcan durante la fase: se anotan y se decide con el usuario si entran.

## Historias de usuario
- Como usuario que instala la app, quiero un instalador con su icono y textos legibles para confiar en lo que instalo.
- Como usuario, quiero exportar mis agentes y temas a un fichero para guardarlos o pasarlos a otra máquina.
- Como usuario, quiero que Ajustes me diga la verdad sobre qué modelos tengo y qué micrófono uso.
- Como usuario, quiero ver todas las ejecuciones, también las del Arquitecto, en un solo listado.
- Como usuario que empieza de cero, quiero crear un equipo antes de tener agentes.
- Como usuario que diseña un pipeline, quiero que una bifurcación sin condiciones funcione sin pasos extra.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | El `.exe` del instalador y sus ventanas muestran el icono de la app | Captura del instalador compilado |
| CA2 | Los textos de la última pantalla del instalador se leen con contraste suficiente | Captura del instalador compilado |
| CA3 | Una conversación con el Arquitecto aparece en el listado de Ejecuciones, marcada como suya, y el contador coincide con el listado | Test de la API o la interfaz + prueba en la app |
| CA4 | Exportar agente y exportar tema guardan un fichero válido, que se vuelve a importar sin errores, en la app de escritorio y en el navegador | Tests + prueba en la app instalada |
| CA5 | Ir a Limpieza desde el menú lateral de Ajustes mantiene la cabecera y la navegación usables | Test de la interfaz + prueba en la app |
| CA6 | Con la carpeta de datos vacía, ningún modelo sin descargar sale «En uso» y los recomendados salen «Aconsejado»; al descargarlo y elegirlo, sale «En uso» | Test del backend o la interfaz + prueba en la app |
| CA7 | En la app instalada en Windows, Ajustes lista los micrófonos del sistema y la prueba usa el elegido | Prueba manual en la app instalada |
| CA8 | Las ventanas vacías de Conocimiento, Skills y Conexiones del agente no dejan hueco ni scroll | Test de la interfaz + captura |
| CA9 | Una foto PNG, JPG o WebP se carga, se encuadra y se guarda como avatar sin verse en verde | Test de la interfaz + prueba en la app |
| CA10 | Se crea un equipo sin agentes y después se le añade uno | Test de la API y la interfaz |
| CA11 | Un pipeline con una bifurcación sin condiciones se guarda y la tarea pasa por todas las ramas | Tests del validador y del motor |
| CA12 | Suites completas, lint y `/code-review` en verde | Comandos de `package.json` |

## Prerrequisitos
- Fase 20 cerrada (`v0.9.0`).
- Una máquina Windows con micrófono para CA7, y el instalador compilado para CA1, CA2, CA4 y CA7.

## Riesgos y preguntas abiertas
- **Exportar** (CA4): los dos fallos apuntan a una misma causa, la descarga desde la interfaz dentro del WebView de Tauri. Se confirma en el plan.
- **Micrófonos** (CA7): la fase 16 dejó pendiente comprobar el permiso del micrófono en la app instalada. Puede depender de la configuración de WebView2 o de los permisos de Windows, y no de nuestro código.
- **Modelos «En uso»** (CA6): seguramente son los modelos elegidos por defecto. Decidido con el usuario: mientras no estén descargados salen como «Aconsejado».
- **Ramas sin condición** (CA11): cambia la regla de la fase 13. Decidido con el usuario: una rama sin condición se hace siempre. La condición sigue disponible para las ramas que deban saltarse a veces, y el modelo que decide solo se consulta si alguna rama de la bifurcación la tiene.
