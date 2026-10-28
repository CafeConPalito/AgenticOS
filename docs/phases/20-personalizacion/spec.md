# Fase 20: Personalización y Acerca de · Spec

- **Estado**: aprobada (2026-10-27); enmienda 1 aprobada (2026-10-28)
- **Rama**: `phase/20-personalizacion`

## Objetivo
Hacer la app más sencilla de recorrer y más **propia** del usuario. La navegación se revisa para que cualquier sección se alcance sin conocer atajos ni rutas; cada agente se distingue de un vistazo por su **imagen y su color**; y el aspecto de toda la interfaz se puede personalizar con **temas** más allá de claro y oscuro. Además, una página **Acerca de** dice quién ha hecho la app, con qué licencia se distribuye (GNU GPLv3) y cómo informar de un error, con un botón que prepara los **últimos registros** del sistema para enviarlos.

## Punto de partida (fases 08, 09, 10 y 19)
- La barra superior (fase 09, ADR 0013) tiene solo Tablero, Ejecuciones y Ajustes; Inicio es el logo. Agentes, Proyectos, Inbox, Consumo, CLIs, Conocimiento y Conexiones son **páginas de segundo nivel** a las que solo se llega por ruta, `Ctrl+K`, la miga de pan o enlaces dentro de otras pantallas (`components/layout/nav.ts`).
- El agente ya tiene un **color** (`Agent.color`, hex) que se elige en el editor; no tiene imagen: se representa con sus iniciales sobre ese color.
- El tema es **claro u oscuro** (`theme/ThemeProvider.tsx`), guardado en `localStorage` y aplicado con la clase `.dark` sobre los *tokens* de `styles/tokens.css` (shadcn/ui + Tailwind v4). Hay colores derivados de los tokens (diffs, grafo de git) y otros fijos (barra lateral navy en los dos modos, terminal).
- «Acerca de» es hoy una **sección de Ajustes** (`pages/settings/AboutSection.tsx`, fase 08): versión, carpeta de datos, URL del backend y, en la app de escritorio, «Abrir registros».
- El backend escribe su registro en un fichero rotativo (5 MB × 4, `logging_setup.py`) dentro de la carpeta de datos.
- La exportación de agentes (fase 19) produce un fichero con su ficha completa.
- El repositorio **no tiene fichero `LICENSE`** ni la licencia declarada en `package.json`, `pyproject.toml` o `Cargo.toml`.

## Alcance
### Dentro
**A. Navegación más simple**
- **Pestañas agrupadas como hasta ahora**: se mantiene la estructura de la fase 09 (ADR 0013): pestañas Tablero, Ejecuciones y Ajustes en la barra superior, Inicio en el logo, y las demás secciones como páginas de segundo nivel agrupadas bajo ellas. No se añaden pestañas, menús ni cajón lateral.
- **Miga de pan con atrás y adelante**: debajo de las pestañas, la ruta de la pantalla actual (p. ej. Proyectos › Web corporativa › Tarea T-12 › Ejecución) con cada nivel enlazable, y botones **Atrás** y **Adelante** que recorren el historial de navegación de la app (también con `Alt+←` / `Alt+→` y los botones laterales del ratón). Funciona igual en la app de escritorio, donde no hay botones del navegador.
- La **Inbox** muestra su contador de pendientes en la barra superior.
- Revisión de las pantallas con más elementos (Inicio, editor de agente, Ajustes) para quitar ruido: menos botones a la vista, acciones secundarias en menús, títulos y espaciado coherentes. El inventario concreto de cambios va en el plan.
- Los atajos y la paleta de comandos siguen funcionando igual (y la paleta incluye las páginas nuevas: Apariencia y Acerca de).

**B. Personalización visual de los agentes** (solo visual: no cambia nada de cómo se ejecutan)
- **Imagen del agente**, a elegir entre:
  - una **galería de búhos**: ilustraciones de uso libre (CC0 o licencia compatible con GPLv3, con su atribución en Acerca de) de búhos distintos: con sombrero, sin él, con gafas, con auriculares, con libro, etc. Al menos 12 variantes. Si no existe un set libre con suficientes búhos coherentes entre sí, se dibuja uno propio en SVG por capas (búho base + accesorios), publicado con la licencia del proyecto;
  - una **foto propia** (PNG, JPG o WebP de **2048 px como mucho** en cada lado; si es mayor, se rechaza con el motivo). El usuario **encuadra** la foto en la propia app (arrastrar para mover y zoom) dentro del recorte cuadrado. Solo se guarda el **recorte comprimido** (p. ej. WebP de 256 × 256); la **foto original no se guarda nunca**, ni en la carpeta de datos ni en temporales: el recorte se hace en la interfaz y al backend solo llega el resultado, que vuelve a validar tamaño y formato;
  - o, como ahora, sus **iniciales** sobre su color (por defecto).
- **Color principal**: selector con una paleta sugerida (colores que se distinguen entre sí en claro y oscuro) y valor hex libre. Se avisa si el color apenas contrasta con el tema actual.
- La imagen y el color se ven en **todas** las pantallas donde aparece el agente: Inicio, Agentes, Tablero, Ejecuciones y su árbol, terminal y dock, Inbox, Consumo, equipos y editor de pipelines. Un componente `AgentAvatar` único para todos.
- La personalización entra en la **exportación/importación** de agentes (fase 19), con la imagen incluida.
- El **Arquitecto** puede proponer el color y un búho de la galería; no genera ni sube imágenes.

**C. Temas de la interfaz**
- **Temas incluidos** además de los actuales (Oscuro navy y Claro): al menos **Alto contraste**, uno cálido y uno neutro (grafito); la lista exacta se cierra en el plan.
- **Seguir al sistema**: el tema claro u oscuro elegido según la preferencia de Windows, y cambia en vivo.
- **Editor de temas** (nueva página Ajustes › Apariencia): se parte de un tema existente y se cambian, con **vista previa en vivo**:
  - base clara u oscura;
  - colores de fondo, superficies, texto, primario/acción, acento, bordes y barra superior/lateral;
  - colores de estado (en curso, hecho, fallido, en espera…), de los que se derivan diffs y grafo;
  - colores del **terminal** (fondo, texto y los 16 ANSI);
  - **tipografía** (entre las fuentes incluidas en la app), tamaño de texto (escala) y densidad (compacta / normal / amplia);
  - **radio** de las esquinas.
- **Comprobación de contraste** (WCAG AA) de los pares texto/fondo principales, con aviso y sin bloquear.
- Temas propios: crear, duplicar, renombrar, borrar, **exportar e importar** (JSON validado; un fichero mal formado o con valores no válidos se rechaza con el motivo).
- El tema y los temas propios se guardan en los **ajustes del backend** (sobreviven a reinstalar o a limpiar el almacenamiento del navegador); `localStorage` solo como caché para pintar sin parpadeo al arrancar.
- Todos los colores fijos que hoy no salen de los *tokens* pasan a salir de ellos (inventario en el plan).

**D. Página Acerca de**
- **Página propia** (`/acerca-de`), accesible desde la navegación (apartado A), la paleta de comandos y Ajustes (que deja de tener la sección y enlaza a la página).
- Contenido:
  - logo, nombre y **versión** (con la del backend y el *sidecar* si difieren);
  - **autoría**: el logo de Café con Palito (`logo-simple-rb.png`, copiado al repositorio como recurso de la app) y debajo dos líneas: «Made By Café Con Palito with ❤️» y «Albano Díez de Paulino»;
  - **licencia GNU GPLv3**: nombre, aviso breve («software libre, sin garantía…») y el **texto completo** visible dentro de la app, sin conexión;
  - **licencias de terceros**: lista generada en el *build* de las dependencias de frontend, backend y Tauri con su licencia;
  - lo que hoy tiene la sección de Ajustes: carpeta de datos, URL del backend y «Abrir registros».
- **Informar de un error**: enlace `mailto:contacto@cafeconpalito.com` con el asunto y el cuerpo rellenos (versión, sistema operativo y una plantilla: qué hacías, qué esperabas, qué pasó).
- Fichero `LICENSE` en la raíz del repositorio con el **texto de la GNU GPLv3 tal como lo da GitHub** (el oficial de la FSF, sin cambios, para que GitHub la reconozca), aviso `Copyright (C) 2026 Albano Díez de Paulino` en el README, y la licencia declarada en `package.json`, `pyproject.toml`, `Cargo.toml` y los metadatos del instalador (identificador SPDX `GPL-3.0-or-later`, que es lo que indica el aviso estándar de la propia GPLv3).

**E. Enviar los últimos registros**
- Botón **«Preparar registros para enviar»** en Acerca de (y en el aviso de backend caído / sin conexión, donde ya está «Abrir registros»).
- Genera un **`.zip`** con:
  - los registros del backend (fichero actual y rotados, recortados a los últimos N MB, con un valor por defecto razonable);
  - el registro del *shell* de Tauri / arranque del *sidecar*, si existe;
  - los **errores recientes del frontend** (nuevo: búfer circular de errores y avisos de la UI que se envía al registro del backend);
  - un `info.txt` con versión, sistema operativo, CLIs instalados y sus versiones, y número de agentes, proyectos y ejecuciones (sin nombres ni contenido).
- **No incluye** salidas de terminal de las ejecuciones, contenido de tareas, conocimiento ni conversaciones.
- **Limpieza de datos sensibles** antes de empaquetar: tokens y claves (patrones conocidos, cabeceras `Authorization`, valores del almacén de secretos, *tokens* de ejecución del MCP), correos y la ruta del usuario (`C:\Users\<nombre>` → `C:\Users\<usuario>`).
- Antes de generar, el usuario ve **qué se incluye** (lista de ficheros y tamaño) y puede abrir el `.zip` para revisarlo.
- Después: se guarda en Descargas (o donde elija el usuario), se muestra en el explorador y se abre el correo con el `mailto` del apartado D indicando que **adjunte el fichero** (un `mailto` no puede adjuntar ficheros por sí solo).

### Fuera
- Personalización que cambie el **comportamiento** de los agentes (eso es el editor de agentes y el Arquitecto).
- Imágenes generadas con IA para los avatares, y emojis como avatar.
- Cambiar la estructura de pestañas de la fase 09, o añadir menús desplegables o cajón lateral para navegar.
- Pestañas de «documentos» abiertos a la vez (varias pantallas abiertas como en un navegador).
- Personalización de equipos y proyectos (color e icono propios); se anota para una fase futura si se quiere.
- Envío automático de registros a un servidor (no hay servidor que los reciba) y telemetría de cualquier tipo.
- Galería pública o compartida de temas.
- Traducción a otros idiomas además del español (la i18n ya existe; los textos nuevos van en `frontend/src/i18n/`).

## Historias de usuario
- Como usuario, quiero llegar a Conocimiento o a Conexiones con el ratón sin acordarme del atajo, para no perderme en la app.
- Como usuario, quiero ponerle una imagen y un color a cada agente, para reconocerlo al instante en el tablero y en las ejecuciones.
- Como usuario, quiero un tema con mis colores y mi tamaño de letra, para trabajar a gusto muchas horas.
- Como usuario con baja visión, quiero un tema de alto contraste, para leer la interfaz sin esfuerzo.
- Como usuario, quiero saber quién hizo la app y con qué licencia, para saber qué puedo hacer con ella.
- Como usuario que ha visto un fallo, quiero mandar los registros con un par de clics y sin exponer mis claves, para que puedan arreglarlo.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | Las pestañas y su agrupación siguen como en la fase 09; las pantallas revisadas tienen menos elementos a la vista (inventario del plan) y Apariencia y Acerca de se abren desde Ajustes y la paleta | tests de componente + revisión con el usuario |
| CA2 | La miga de pan muestra la ruta con cada nivel enlazable, y Atrás/Adelante (botones, `Alt+←/→` y botones del ratón) recorren el historial, también en la app de escritorio; la Inbox muestra los pendientes en vivo en la barra superior | tests de componente + prueba manual en Tauri |
| CA3 | Un agente con búho de la galería, foto propia o iniciales se ve igual en todas las pantallas listadas en B | tests de `AgentAvatar` y de las pantallas + revisión visual |
| CA4 | Una foto de más de 2048 px en algún lado o de formato no admitido se rechaza con el motivo; una válida se encuadra, se guarda solo el recorte comprimido, la original no aparece en la carpeta de datos ni en temporales, y el recorte sobrevive a reiniciar la app | tests de componente y de la API (la API rechaza también un recorte que no cumpla) |
| CA5 | Exportar e importar un agente conserva su imagen y su color | test de la API (ida y vuelta) |
| CA6 | Cambiar de tema (incluidos los nuevos y «Seguir al sistema») se aplica en vivo a toda la UI, terminal incluido, sin recargar | tests de `ThemeProvider` + revisión visual |
| CA7 | Un tema propio se crea, se edita con vista previa, se exporta, se importa en otra instalación y se aplica; un JSON no válido se rechaza con el motivo | tests de componente y de la API |
| CA8 | El editor avisa de los pares texto/fondo por debajo de WCAG AA; los temas incluidos los cumplen todos | test unitario del cálculo de contraste sobre cada tema incluido |
| CA9 | No queda ningún color fijo fuera de los *tokens* en los componentes (salvo los documentados en el plan) | búsqueda en el código (script o lint) |
| CA10 | La página Acerca de muestra versión, el logo con «Made By Café Con Palito with ❤️» y «Albano Díez de Paulino», la licencia GPLv3 con su texto completo sin conexión y las licencias de terceros (incluida la atribución de los búhos) | test de componente + comprobación sin red |
| CA11 | «Informar de un error» abre el correo a `contacto@cafeconpalito.com` con asunto y cuerpo rellenos | test del `href` generado + prueba manual |
| CA12 | El `.zip` de registros contiene lo listado en E, no contiene salidas de terminal ni contenido de tareas, y ningún secreto sembrado en los registros de prueba sobrevive a la limpieza | test de la API con secretos de prueba |
| CA13 | Tras preparar los registros, el fichero queda en la carpeta elegida, se muestra en el explorador y se abre el correo | e2e con el binario empaquetado + prueba manual |
| CA14 | El repo tiene `LICENSE` (GPLv3) y la licencia declarada en los tres manifiestos y en el instalador | revisión |
| CA15 | Suites de backend y frontend en verde, lint y tipos sin errores | `uv run pytest`, `npm test`, ruff, ESLint, `tsc` |

## Prerrequisitos
- Fase 19 cerrada (`v1.11`). ✔
- Confirmar que todas las dependencias son compatibles con distribuir la app bajo GPLv3 (MIT, BSD, Apache-2.0, MPL-2.0 y LGPL lo son; revisar cualquier licencia propietaria o «sin licencia»).

## Riesgos y preguntas abiertas
Decisiones del usuario (2026-10-27): licencia GNU GPLv3 con el texto que da GitHub; autoría con el logo de Café con Palito y las dos líneas indicadas; registros como en E (zip + explorador + correo pidiendo adjuntarlo); pestañas agrupadas como hasta ahora, con miga de pan y atrás/adelante, sin menús; galería de búhos de uso libre y foto propia encuadrada y comprimida, sin guardar la original y de 2048 px como mucho.

1. **Logo en temas oscuros** (decidido): en los temas de base oscura se usa `logo-simple-negative-rb.png`, de la misma carpeta.
2. **Set de búhos** (decidido): se busca un set libre de búhos coherente y con suficientes variantes; si no lo hay, se dibuja uno propio en SVG por capas (búho base + accesorios). Lo resuelve el bloque de spikes del plan.
3. **Colores fijos repartidos** por los componentes: si son muchos, el apartado C crece. El plan arranca con un inventario y, si hace falta, se recorta (p. ej. dejando el terminal para el final).
4. **Limpieza de secretos**: nunca es perfecta; por eso el usuario ve y puede revisar el zip antes de enviarlo.

## Enmienda 1 (2026-10-28, aprobada por el usuario): instalador y barra de la ventana
Pedida tras cerrar el desarrollo (la fase se reabre en su rama y se vuelve a validar y fusionar).

### Dentro
**F. Instalador con la imagen de la app** (NSIS, `tauri.conf.json` y `windows/`)
- Imagen de cabecera (150×57) y lateral (164×314) en el navy del tema principal con el logo de Café con Palito en negativo, y los colores del asistente (fondo, texto, cabecera) tomados de los *tokens* de `tokens.css`.
- Se mantiene la página de **aceptación de la licencia GPLv3** (ya existe por `licenseFile`), con el texto de cabecera en español.
- **Autoría** como en Acerca de («Made By Café Con Palito with ❤️» y «Albano Díez de Paulino») en las páginas de bienvenida y final.
- Límite conocido: NSIS no admite temas arbitrarios; los botones y casillas conservan el aspecto de Windows.

**G. Barra de la ventana con el color del tema, con los rasgos de cada sistema**
- **Windows 11**: barra nativa (botones arriba a la derecha, menú de ajuste de ventanas) con el color y el texto del tema activo, aplicados desde Rust (DWM) y actualizados en vivo al cambiar de tema o seguir al sistema. **Windows 10**: barra clara u oscura del sistema según la base del tema, sin el color exacto.
- **macOS** (preparado, sin poder probarse en esta fase): `titleBarStyle: Overlay` con el título oculto; los botones siguen a la izquierda, nativos, y la cabecera de la app deja su hueco y sirve para arrastrar la ventana.
- **Linux**: barra del sistema, sin cambios.
- Sin botones dibujados por la app.

### Fuera
- Probar el estilo de macOS (se anota para cuando haya un Mac) e instaladores de otros sistemas.
- Instalador que cambie con el tema elegido por la persona: usa siempre el principal.

### Criterios de aceptación añadidos
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA16 | El instalador usa las imágenes y colores navy, muestra la aceptación de la licencia y la autoría | test de la configuración y de las imágenes (existen, medidas) + capturas del instalador construido |
| CA17 | En Windows 11 la barra toma el color del tema y cambia en vivo; en Windows 10 es clara u oscura según la base; los botones siguen nativos | tests del comando de Rust y de la lógica de color + prueba manual |
| CA18 | La configuración de macOS (Overlay, título oculto, hueco para los botones y zona de arrastre) está en su sitio y no afecta a Windows | test de configuración y de la cabecera por plataforma; sin prueba en un Mac |
