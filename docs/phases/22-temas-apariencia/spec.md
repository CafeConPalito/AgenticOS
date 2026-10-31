# Fase 22: Temas y apariencia · Spec

- **Estado**: aprobada (2026-10-31)
- **Rama**: `phase/22-temas-apariencia`

## Objetivo
Que elegir el aspecto de la app sea sencillo con cualquier tema, no solo con el Claro y el Oscuro navy. Para ello se quitan el botón claro/oscuro, que se lía con los temas propios, y «Seguir al sistema»; la galería se filtra por temas claros y oscuros. Se añaden:
- temas creados desde cero con cualquier fuente instalada en el sistema;
- muchos más temas incluidos, entre ellos los más conocidos de VS Code.

También se mejora el menú lateral de Ajustes, para que los títulos de grupo se distingan de las opciones.

## Punto de partida
- Fase 20 ([ADR 0027](../../adr/0027-personalization-support.md)):
  - Los temas son datos (`agentic-os.theme` v1) que se aplican como variables CSS.
  - Vienen cinco temas incluidos: Oscuro navy, Claro, Alto contraste, Cálido y Grafito.
  - Un tema propio se crea solo duplicando otro (`extends`) y guarda únicamente lo que cambia.
  - La fuente se elige entre cuatro: Ubuntu, Inter, Atkinson Hyperlegible y la del sistema.
- La cabecera y la paleta de comandos tienen un botón claro/oscuro. Ese botón cambia entre los dos temas que Apariencia tiene asignados a claro y a oscuro. Con temas propios no hace lo que el usuario espera: es el fallo que reportó.
- En Apariencia se elige entre un tema fijo y «Seguir al sistema» (un tema para cuando Windows está en claro y otro para oscuro).
- El menú lateral de Ajustes agrupa las secciones bajo títulos en letra pequeña, mayúsculas y gris, el mismo gris de las opciones: cuesta distinguir los títulos de las opciones. En pantallas estrechas los títulos no se muestran.
- La elección se guarda en `app_state["appearance"]` (`GET/PUT /api/settings/appearance`).

## Alcance
### Dentro
**A. Sin selector claro/oscuro**
1. Se quitan el botón claro/oscuro de la cabecera y la acción «Cambiar tema» de la paleta de comandos. El tema solo se elige en Ajustes › Apariencia.
2. Se quita **«Seguir al sistema»**: siempre hay un único tema elegido. Quien lo tenía activo se queda con el tema que estaba viendo.
3. La galería de Apariencia tiene un **filtro**: Todos · Claros · Oscuros. Un tema cuenta como claro u oscuro según su base, y eso vale también para los temas propios.
4. El filtro arranca en Claros u Oscuros según el modo de Windows. Si el usuario cambia el filtro, la app lo recuerda.

**B. Temas desde cero y fuentes del sistema**
5. Un botón **«Nuevo tema»** crea un tema sin partir de otro. Se elige si es claro u oscuro y se parte de los colores básicos de esa base. El editor de siempre permite cambiar cualquier color, con su comprobación de contraste.
6. Además de las cuatro fuentes incluidas, el editor lista las **fuentes instaladas en el sistema** con un buscador. Cada nombre se muestra con su propia fuente.
7. El tema guarda el nombre de la fuente elegida. Si se importa en un equipo que no la tiene, la app usa la fuente del sistema y el editor avisa de que falta.
8. Un tema creado de cero se exporta e importa igual que los demás. Los temas exportados con la fase 20 se siguen importando.

**C. Más temas incluidos**
9. Se incluyen **al menos 20 temas nuevos**, unos 25 en total, repartidos entre claros y oscuros.
10. Entre ellos están los **temas conocidos de VS Code** con licencia libre, adaptados a los colores de la app: por ejemplo Dracula, One Dark, Nord, Solarized claro y oscuro, Gruvbox, Tokyo Night, Catppuccin, GitHub claro y oscuro, Night Owl y Ayu. Conservan su nombre original, y su autoría y licencia salen en Ajustes › Acerca de, junto a las demás dependencias de terceros. El resto son paletas propias con nombre en español.
11. Cada tema incluido pasa la comprobación de contraste de la fase 20: 4,5:1 para el texto y 3:1 para las etiquetas de los botones sobre su color de acción. Si el color original de un tema no llega, se ajusta lo mínimo. Un test lo vigila.

**D. Menú de Ajustes**
12. Los **títulos de grupo** del menú lateral se distinguen a simple vista de las opciones: más contraste y peso, con un separador entre grupos. Las opciones van debajo de su título, sangradas.
13. En pantallas estrechas el menú también muestra a qué grupo pertenece cada opción.
14. Se mantienen la navegación con teclado y el resaltado de la sección visible.

### Fuera
- Modo lectura nocturno: se quita de la fase y del roadmap, porque el sistema operativo ya lo ofrece (luz nocturna de Windows). Decidido con el usuario (2026-10-31).
- Accesos directos en Inicio, terminal con un CLI independiente, logos de los CLIs, «Añadir CLI» y la transcripción de «Probar micrófono» (fase 23).
- Foto del proyecto, plantilla de pipeline «Desarrollo», plantillas de agentes nuevas, y el Arquitecto creando equipos y pipelines (fase 24).
- Descargar fuentes de internet: solo se usan las fuentes incluidas y las instaladas en el sistema.
- Temas de VS Code con licencia comercial o sin licencia clara (por ejemplo Monokai Pro): no se incluyen.
- Importar un tema de VS Code (`.json` de VS Code) desde la app: se anota para una fase futura.
- Reordenar o renombrar las secciones de Ajustes: solo cambia cómo se ven los títulos.

## Historias de usuario
- Como usuario con temas propios, quiero elegir el tema en un solo sitio y filtrar entre claros y oscuros, sin un botón que me cambie a otro tema que no esperaba.
- Como usuario, quiero crear mi tema desde cero con mi fuente favorita del sistema.
- Como usuario, quiero muchos temas entre los que elegir, también los que ya uso en VS Code, sin tener que crearlos.
- Como usuario, quiero ver de un vistazo los grupos del menú de Ajustes para encontrar antes cada opción.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | La cabecera y la paleta de comandos ya no tienen el cambio claro/oscuro | Test de la interfaz |
| CA2 | El filtro de la galería muestra solo los temas claros u oscuros, propios incluidos, y se recuerda al volver | Test de la interfaz |
| CA3 | «Seguir al sistema» ya no existe; quien lo tenía activo conserva el tema que estaba viendo; el filtro arranca según el modo de Windows | Tests de la interfaz y del backend |
| CA4 | «Nuevo tema» crea un tema claro u oscuro sin partir de otro, y se edita, guarda, exporta e importa | Tests de la interfaz y del backend |
| CA5 | Un tema con una fuente instalada en el sistema la aplica en toda la app instalada | Prueba en la app instalada en Windows |
| CA6 | Importar un tema con una fuente que falta usa la fuente del sistema y avisa en el editor | Test de la interfaz |
| CA7 | Los temas exportados en la fase 20 se siguen importando | Test con un fichero de la fase 20 |
| CA8 | Hay al menos 25 temas incluidos, claros y oscuros, entre ellos los de VS Code del punto 10; todos pasan la comprobación de contraste y su licencia sale en Acerca de | Tests |
| CA9 | En el menú de Ajustes los títulos de grupo se distinguen de las opciones, también en pantallas estrechas, y la navegación con teclado sigue funcionando | Test de la interfaz + captura |
| CA10 | Suites completas, lint y `/code-review` en verde | Comandos de `package.json` |

## Prerrequisitos
- Fase 21 cerrada (`v0.9.1`).
- La app instalada en Windows para CA5.

## Riesgos y preguntas abiertas
- **«Seguir al sistema»**: decidido con el usuario (2026-10-31). Se quita, y el modo de Windows solo decide con qué filtro arranca la galería.
- **Temas de VS Code**: solo los que tienen licencia libre (MIT o similar), con su autoría en Acerca de. Algunos colores originales pueden no pasar el contraste de la app; se ajustan lo mínimo y se dice en Acerca de que es una adaptación. La lista definitiva, con la licencia de cada uno, va en el plan.
- **Lista de fuentes del sistema**: el navegador no da la lista de fuentes sin un permiso (*Local Font Access*), y en WebView2 puede no estar disponible. En la app de escritorio se pedirá la lista al *shell* de Rust; en el navegador, si no se puede leer, se escribe el nombre a mano. Se concreta en el plan.
- **Formato del tema**: guardar una fuente del sistema y temas sin `extends` cambia el formato `agentic-os.theme`. Hay que decidir si es una v2 o una ampliación compatible de la v1. Las dos opciones deben seguir leyendo los ficheros de la fase 20; va en un ADR con el plan.
