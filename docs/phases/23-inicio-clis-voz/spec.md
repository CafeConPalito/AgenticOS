# Fase 23: Inicio, CLIs y voz · Spec

- **Estado**: aprobada (2026-10-31)
- **Rama**: `phase/23-inicio-clis-voz`

## Objetivo
Llegar antes a lo que más se usa y quitar pasos fuera de la app:
- accesos directos en Inicio;
- un terminal propio con el CLI y la cuenta que se elija;
- los CLIs reconocibles por su logo;
- instalar desde la app los CLIs que faltan;
- ver el texto del dictado según se habla, también al probar el micrófono.

## Punto de partida
- **Inicio** (`pages/home/`) tiene el saludo, «Te necesitan», la cuadrícula de agentes y la columna de resumen, pero ningún acceso directo a otras secciones.
  - La biblioteca de Conocimiento (`/conocimiento`) tiene las vistas de documentos, skills, explorar y uso; las conexiones MCP están en `/conexiones`.
- **El icono de terminal de la cabecera** (y `Ctrl+º`) abre el panel de terminales, con una pestaña por ejecución activa de los agentes. Es lo mismo que ya muestra Ejecuciones.
- **CLIs y cuentas** (`/clis`):
  - Cada CLI (Claude Code y Antigravity CLI) se identifica con una etiqueta de dos letras (`CliTag`), no con su logo.
  - Hay dos botones «Añadir cuenta»: el general de la cabecera, que abre el de Claude Code, y el de la sección de Claude Code.
  - Un CLI que no está instalado sale como «No detectado», sin forma de instalarlo desde la app.
- **Probar micrófono** (Ajustes › Dictado) graba unos segundos y solo dice si oyó sonido.
- **El dictado** transcribe en local con whisper.cpp (fase 16), y desde la fase 21 el motor se instala bien. El texto no aparece hasta que se deja de grabar.
- Ya existe un terminal interactivo con el CLI en un pseudo-terminal: el de iniciar sesión en una cuenta (fase 10, ADR 0014), con el mismo protocolo que el terminal de una ejecución.

## Alcance
### Dentro
**A. Accesos directos en Inicio**

> **Cambio en la validación (2026-11-01, a petición del usuario):** los accesos pasan a la barra superior, junto al Inbox y con sus mismos iconos. Tablero, Ejecuciones y Ajustes ya son pestañas de esa barra, y Contexto y Skills llevan a la misma página, así que quedan dos iconos: Conocimiento (documentos y skills) y Conexiones (MCPs). Inicio ya no tiene la fila de emojis. Tablero, Ejecuciones y Ajustes pasan también a iconos; el contador de Tablero y Ejecuciones va dentro de la misma píldora que su icono.

1. Inicio tiene una fila de accesos directos con un emoji cada uno: Contexto (la biblioteca de Conocimiento), Skills, MCPs (Conexiones), Tablero, Ejecuciones y Ajustes.
2. El nombre de cada acceso sale en un *tooltip* al pasar el ratón o al llegar con el teclado. Cada botón tiene además su nombre accesible para lectores de pantalla.

**B. Terminal independiente**
3. El icono de terminal de la cabecera, y `Ctrl+º`, abren un **terminal propio**. Se eligen:
   - el CLI y la cuenta (las de Claude Code, o la sesión de Antigravity);
   - la carpeta donde abrirlo: un proyecto, la carpeta personal o **cualquier carpeta del sistema**, con el selector de carpetas.

   Después se abre el CLI interactivo, sin agente, sin tarea y sin instrucciones.
4. Se pueden tener varios terminales a la vez, cada uno en su pestaña del panel. Siguen abiertos al cambiar de página y se cierran al cerrar su pestaña o la app.
5. El panel deja de mostrar las ejecuciones de los agentes, que siguen en Ejecuciones con su terminal.
6. Un terminal propio no es una ejecución: no sale en Ejecuciones ni cuenta en los límites diarios de los agentes.
7. Lo que se gasta en un terminal propio **sí sale en Consumo**, como uso de su cuenta sin agente («Terminal»). Es gasto real de la cuenta.

**C. CLIs y cuentas**
8. Cada CLI se muestra con un **icono propio y neutro** que lo hace reconocible (su color y un símbolo simple, sin usar los logos registrados), en CLIs y cuentas y en los demás sitios donde hoy sale la etiqueta del CLI. Decidido con el usuario al planificar (2026-10-31).
9. El botón general de la cabecera pasa a llamarse **«Añadir CLI»** y solo ofrece los CLIs que admite la app y no están instalados. Si están todos, no se muestra.
10. Desde «Añadir CLI» se **instala** el CLI elegido con su instalador oficial:
   - Antes de empezar, la app enseña qué va a ejecutar y pide confirmación.
   - La instalación se ve en un terminal.
   - Al acabar, la app vuelve a detectar el CLI y ofrece iniciar sesión.
   - Si falla, se dice por qué y se enlaza la guía oficial.
11. El botón «Añadir cuenta» de la sección de Claude Code se queda como está.

**D. Voz**
12. **Transcripción en vivo**: al dictar, el texto **va apareciendo mientras se habla**, con un pequeño retraso, en vez de esperar a que se deje de grabar. Vale para todos los sitios donde hay dictado. Al parar, el texto se completa con la transcripción final.
13. «Probar micrófono» graba con el micrófono elegido y **muestra lo que va entendiendo** de la misma forma, en local, con el motor y el modelo del dictado.
14. Si el motor o el modelo de voz no están instalados, la prueba muestra el nivel como hasta ahora y dice cómo instalarlos.

### Fuera
- Temas y apariencia (fase 22, cerrada).
- Foto del proyecto, plantilla de pipeline «Desarrollo», plantillas de agentes nuevas, y el Arquitecto creando equipos y pipelines (fase 24).
- CLIs nuevos (Codex, OpenCode…): llegan en su propia fase (29). «Añadir CLI» queda preparado para que aparezcan solos cuando la app los admita.
- Desinstalar o actualizar un CLI desde la app.
- Ordenar o personalizar los accesos directos de Inicio.
- Guardar o reabrir la conversación de un terminal propio después de cerrarlo.

## Historias de usuario
- Como usuario, quiero ir desde Inicio a mis secciones más usadas con un clic.
- Como usuario, quiero abrir Claude Code o Antigravity con la cuenta que elija, para trabajar a mano sin crear un agente.
- Como usuario nuevo, quiero instalar un CLI que me falta sin salir de la app.
- Como usuario, quiero reconocer cada CLI por su logo.
- Como usuario, quiero ver lo que dicto mientras hablo, y comprobar que el dictado me entiende antes de usarlo.

## Criterios de aceptación
| # | Criterio | Cómo se verifica |
|---|---|---|
| CA1 | (Cambiado en la validación: Conocimiento y Conexiones en la barra superior, junto al Inbox, con nombre en el *tooltip*.) Inicio tiene los seis accesos con emoji; cada uno lleva a su sitio y muestra su nombre en un *tooltip*, también con el teclado | Test de la interfaz |
| CA2 | El icono de terminal abre un terminal propio con el CLI, la cuenta y la carpeta elegidos (un proyecto, la carpeta personal o cualquier otra); el CLI usa la sesión de esa cuenta | Tests del backend y de la interfaz + prueba en la app instalada |
| CA3 | Hay varios terminales propios en pestañas; siguen al cambiar de página y se cierran con su pestaña | Test de la interfaz |
| CA4 | El panel ya no lista las ejecuciones; un terminal propio no sale en Ejecuciones ni cuenta en los límites, pero su gasto sale en Consumo como «Terminal» de su cuenta | Tests del backend y de la interfaz |
| CA5 | Los iconos propios de Claude Code y Antigravity salen en CLIs y cuentas y donde antes estaba la etiqueta | Test de la interfaz + captura |
| CA6 | «Añadir CLI» solo ofrece los CLIs no instalados y desaparece si están todos; «Añadir cuenta» de Claude Code sigue igual | Test de la interfaz |
| CA7 | Instalar un CLI desde la app enseña el comando, pide confirmación, se ve en un terminal, lo detecta al acabar y ofrece iniciar sesión; si falla, dice por qué | Tests del backend con un instalador simulado + prueba en una máquina sin el CLI |
| CA8 | Al dictar, el texto va apareciendo mientras se habla y se completa al parar; «Probar micrófono» lo muestra igual; sin motor o modelo, dice cómo instalarlos | Tests del backend y de la interfaz + prueba en la app instalada |
| CA9 | Suites completas, lint y `/code-review` en verde | Comandos de `package.json` |

## Prerrequisitos
- Fase 22 cerrada (`v0.9.2`).
- Una máquina (o una cuenta de Windows) sin uno de los CLIs, para CA7.
- La app instalada con micrófono, para CA2 y CA8.

## Riesgos y preguntas abiertas
- **Instaladores oficiales**: hay que confirmar en el plan qué instalador oficial tiene cada CLI en Windows, si pide Node.js, permisos de administrador o reiniciar la consola, y cómo se detecta después (el `PATH` de la app no se actualiza solo). Para Claude Code hay un instalador nativo y uno por npm. Para Antigravity CLI hay que buscar el método oficial.
- **Logos**: son marcas de sus dueños. Se usan solo para identificar cada CLI, sacados de sus fuentes oficiales. El plan concreta de dónde sale cada uno y en qué condiciones se pueden usar.
- **Consumo de los terminales propios**: decidido con el usuario (2026-10-31), sale en Consumo como uso de su cuenta sin agente. El plan concreta cómo se distingue de las ejecuciones en los registros de cada CLI.
- **Carpeta del terminal**: decidido con el usuario (2026-10-31), un proyecto, la carpeta personal o cualquier carpeta. En la carpeta de un proyecto, el CLI puede tocar sus ficheros sin pasar por el flujo de tareas, igual que si se abriera fuera de la app.
- **Transcripción en vivo**: whisper.cpp no transcribe en *streaming*. Hay que transcribir trozos del audio a medida que llega, y que el texto parcial no salte ni repita palabras al juntarse. Además gasta más CPU mientras se habla. El plan lo prueba con el modelo por defecto en una máquina normal y fija el retraso (orientativo: 1–3 s).
