# Fase 23: Inicio, CLIs y voz · Plan técnico

- **Spec**: [spec.md](spec.md)
- **Estado**: aprobado (2026-10-31), con iconos propios en lugar de los logos oficiales

## Lo que ya se sabe (revisado al escribir el plan)
- **Ejecuciones** (`models/run.py`):
  - `RunKind` tiene `agent`, `decision`, `describe` y `architect`.
  - `LISTED_RUN_KINDS` (fase 21) decide qué sale en Ejecuciones y en su contador.
  - Una ejecución puede no tener agente ni tarea (`agent_id`, `task_id` y `project_id` opcionales), como las del Arquitecto. Lleva `cwd`, la cuenta (`account_id`, `account_label`) y su registro de consumo.
- **El Arquitecto** (`services/runs/manager.py`, `launch_architect`): lanza un CLI interactivo sin tarea en un `RunSession` (pseudo-terminal, *scrollback* y visores por WebSocket), con el entorno de su cuenta (`account_ops.env_for`). Sus *hooks* y la *status line* hacen que el consumo se lea igual que el de cualquier ejecución.
- **Consumo** (`services/usage/`):
  - Todo sale de las filas `Run`: el lector de transcripciones las pone al día y `stats` las agrupa por agente (`agent_id` o `name:<agent_name>`), proyecto, cuenta o tarea.
  - **Los límites diarios son por cuenta** (`limits.py`): el gasto de hoy de la cuenta frena al scheduler.
- **Panel de terminales** (`components/terminal/TerminalDock.tsx`): una pestaña por ejecución activa (sin el Arquitecto), `Ctrl+º` y el estado en `dock-store.ts`. `TerminalPanel` se conecta al WebSocket de la ejecución.
- **Detección de CLIs** (`services/clis.py`): `shutil.which` sobre el `PATH` del proceso del backend, con caché de 10 minutos.
  - Solo hay dos `CliSpec`: Claude Code (`claude`) y Antigravity CLI (`agy`).
  - `CliTag` (`components/agentic/primitives.tsx`) pinta dos letras sobre fondo `primary`.
- **Instaladores oficiales de Windows** (leídos, sin ejecutarlos, el 2026-10-31):
  - **Claude Code**: `irm https://claude.ai/install.ps1 | iex` ([docs](https://code.claude.com/docs/en/install.md)). Descarga el binario de `downloads.claude.ai`, comprueba su SHA-256 y ejecuta `claude.exe install`, que lo deja en `%USERPROFILE%\.local\bin`. No pide administrador ni Node.js. No funciona en Windows de 32 bits.
  - **Antigravity CLI**: `irm https://antigravity.google/cli/install.ps1 | iex`. Descarga un manifiesto, comprueba el SHA-512 y deja `agy.exe` en `%LOCALAPPDATA%\agy\bin` (admite `--dir`). Luego ejecuta `agy install` para el entorno. No pide administrador.
  - Los dos cambian el `PATH` **del usuario**, pero el backend en marcha conserva el `PATH` con el que arrancó, así que `shutil.which` no los ve sin más.
- **Logos**:
  - Las normas de marca de Anthropic ([trademark guidelines](https://www.anthropic.com/legal/trademark-guidelines)) solo permiten usar sus marcas «as specifically permitted» y en materiales aprobados antes. No se pueden alterar, ni sugerir patrocinio.
  - Google no publica normas propias para Antigravity: su [formulario de permisos de marca](https://support.google.com/contact/brand_request_form) cubre el uso de logos.
- **Dictado**:
  - `lib/dictation/controller.ts` graba (`recorder.ts`), y al parar envía el WAV entero a `POST /api/dictation/transcribe`. El backend lo pasa a `whisper-server`, una transcripción cada vez.
  - El texto se inserta en el ancla del campo (`insert.ts`, `trackAnchor`), que sigue los cambios del campo mientras se graba.
  - `MicrophoneTest` (Ajustes › Dictado) usa el mismo `recorder`.
- **Selector de carpetas**: `components/FolderPicker.tsx` (diálogo nativo en la app de escritorio, ruta escrita en el navegador).

## Bloque 0 · Spikes (antes de programar)
| # | Pregunta | Si falla |
|---|---|---|
| S1 | **Velocidad de whisper-server** con el modelo por defecto (Whisper small) en este equipo: ¿cuánto tarda en transcribir 3, 6, 10 y 20 s de audio? ¿Cuánta CPU usa mientras transcribe sin parar? | Si 6 s de audio tardan más de ~2 s: ventanas más cortas y retraso mayor (3–4 s), o solo el texto final con el modelo pequeño y el parcial con `base`. |
| S2 | **Instalador en un pseudo-terminal**: el de Antigravity con `--dir` en una carpeta temporal (no toca la instalación real). ¿Se ve la salida en ConPTY? ¿Termina sin preguntar nada? ¿Qué código de salida da al fallar sin red? | Si pide algo por pantalla, el terminal ya deja escribir; si no se ve la salida, se ejecuta con `-NoProfile -NonInteractive` y se vuelca a la vista. |
| S3 | **Detección tras instalar**: leer el `PATH` del usuario del registro (`HKCU\Environment`) y probar las carpetas conocidas (`%USERPROFILE%\.local\bin`, `%LOCALAPPDATA%\agy\bin`). ¿Basta para encontrar el CLI sin reiniciar la app? | Pedir reiniciar la app al acabar la instalación. |

## Resultados de los spikes (bloque 0, 2026-10-31)
- **S1 · velocidad de whisper-server** (`spikes/dictation/s23_live_speed.py`, con la muestra `dictado.wav`, en este equipo):

  | Modelo | 3 s | 6 s | 10 s | 20 s |
  |---|---|---|---|---|
  | small (el de por defecto) | 2,7 s | 2,9 s | 3,4 s | 4,0 s |
  | base | 0,7 s | 0,7 s | 0,8 s | 1,2 s |
  | small con `-ac 512` | 0,9 s | 1,1 s | 1,1 s | 1,2 s |

  - Whisper procesa siempre ventanas de 30 s, así que con el modelo small cada petición cuesta ~3 s aunque el audio sea corto: así no se puede transcribir en vivo.
  - Con `-ac 512` (una ventana de ~10 s), el mismo modelo tarda ~1 s y en clips de 8 y 10 s da **el mismo texto** que sin ella (comparado palabra a palabra). A partir de ~10 s se perdería audio.
  - El modelo base es rápido, pero se equivoca más («compreve»).
  - → **Diseño**: whisper-server arranca con `-ac 512`, y **todo** se transcribe en trozos de como mucho 9 s, cortados en una pausa.
    - El backend corta él mismo cualquier WAV más largo, por el punto más silencioso cerca del límite, y junta los textos. Así ninguna petición pierde audio, venga de donde venga.
    - En vivo, una petición cada ~1,5 s cabe de sobra (~1 s cada una).
- **S2 · instalador en un pseudo-terminal**: no se ejecuta el instalador real en este equipo. Su paso `agy install` cambiaría el `PATH` del usuario, y los dos CLIs ya están instalados.
  - Se prueba con un instalador simulado: salida en ConPTY, código de salida y error sin red.
  - El instalador real se prueba en la validación, en una cuenta de Windows sin el CLI (CA7).
  - Los dos scripts oficiales son no interactivos: no preguntan nada y acaban con un código de salida (leídos el 2026-10-31).
- **S3 · detección tras instalar**: ✅ los dos instaladores dejan su carpeta en el `PATH` del usuario en el registro. En este equipo están `C:\Users\…\.local\bin` y `%LOCALAPPDATA%\agy\bin`: la segunda con la variable sin expandir, así que hay que expandirla. Leer `HKCU\Environment\Path` (con `winreg`, expandiendo las variables) y buscar ahí el ejecutable basta, sin reiniciar la app.

## Diseño
### 1. Accesos directos en Inicio
- Componente `HomeShortcuts`, entre el saludo y «Te necesitan». Hay seis botones redondos con emoji:

  | Acceso | Emoji | Destino |
  |---|---|---|
  | Contexto | 📚 | `/conocimiento?vista=documentos` |
  | Skills | 🧩 | `/conocimiento?vista=skills` |
  | MCPs | 🔌 | `/conexiones` |
  | Tablero | 📋 | `/tablero` |
  | Ejecuciones | ▶️ | `/ejecuciones` |
  | Ajustes | ⚙️ | `/ajustes` |

- Cada botón es un `Link` con `aria-label` y un `Tooltip` (el componente de shadcn que ya se usa) que se abre al pasar el ratón y al recibir el foco. El emoji va con `aria-hidden`.

### 2. Terminal propio
- **Modelo**: `RunKind.TERMINAL` (`terminal`), sin agente, tarea ni proyecto, con `agent_name = "Terminal"`. No entra en `LISTED_RUN_KINDS`, así que no sale en Ejecuciones. No hace falta migración: `kind` es un `String(12)` sin `CHECK`.
- **Lanzar**: `RunManager.launch_terminal(cli, account, cwd)`, como `launch_architect` pero:
  - sin instrucciones, sin MCP y sin *prompt*;
  - el CLI interactivo tal cual, con los permisos que pida al usuario;
  - con los *hooks* y la *status line* que el consumo necesita.
  - Los adaptadores ganan un modo «terminal» que solo prepara eso. agy no tiene *hooks*: su consumo sale de su transcripción, que se lee al final, como en sus ejecuciones.
- **API**:
  - `POST /api/terminals` con `{cli, account_id, cwd}` crea la ejecución y devuelve su id. El WebSocket es el de cualquier ejecución.
  - `GET /api/terminals` da los terminales abiertos.
  - `DELETE /api/terminals/{id}` cierra uno, que termina su CLI.
  - `cwd` tiene que existir y ser una carpeta.
- **Consumo**: el terminal es una fila `Run` más, así que Consumo la cuenta sola, agrupada como «Terminal» y con su cuenta.
- **Límites**: `limits.py` deja fuera `kind = terminal` al sumar el gasto de hoy de la cuenta. El gasto hecho a mano no frena a los agentes, tal como dice la spec.
- **Panel**: `TerminalDock` pasa a listar `GET /api/terminals`.
  - La pestaña «+» abre `NewTerminalDialog`, con el CLI (solo los instalados), la cuenta de ese CLI (la predeterminada marcada) y la carpeta.
  - La carpeta se elige entre los proyectos, la carpeta personal, o «Otra…» con `FolderPicker`.
  - Cerrar la pestaña llama a `DELETE`.
  - Abrir el panel sin terminales abre el diálogo.
  - Se quitan del panel las ejecuciones de los agentes, la acción «Expandir a la ejecución» y lo que solo servía para ellas.
- **Al cerrar la app**: el backend termina los terminales abiertos (la misma limpieza que las ejecuciones) y los marca como acabados.

### 3. Logos y «Añadir CLI»
- **Iconos de los CLIs** (decidido con el usuario, 2026-10-31): **iconos propios y neutros**, no los logos oficiales, pero que se reconozca cada CLI. Componente `CliIcon`, con un SVG propio por CLI:
  - **Claude Code**: cuadrado redondeado en terracota (`#c96442`), el color con el que se asocia Claude, con un *prompt* de terminal `>_` en blanco.
  - **Antigravity CLI**: cuadrado redondeado en azul y violeta, en degradado, con una flecha hacia arriba sobre una órbita, en blanco (la «antigravedad»).
  - **Los CLIs que lleguen después** (Codex, OpenCode…) siguen el mismo patrón, con su color y un símbolo simple. Un CLI sin icono propio usa uno genérico de terminal.
  - Ninguno copia formas de los logos registrados (ni el destello de Claude ni el símbolo de Antigravity). Los colores de los iconos son colores de datos, como los de los agentes, y se declaran en `theme/palettes.ts` (la excepción que ya permite el test de colores fijos).
  - `CliIcon` sustituye a `CliTag` en todas partes: CLIs y cuentas, tarjetas de agente, ejecuciones, consumo y selectores. El nombre del CLI va siempre en el `aria-label`.
- **«Añadir CLI»**:
  - `CliInfo` gana `install: {command, docs_url} | null`, con el instalador oficial de cada `CliSpec`.
  - El botón de la cabecera de `/clis` solo sale si hay algún CLI admitido sin instalar, y abre `AddCliDialog`:
    1. Se elige el CLI.
    2. Se ve el comando exacto que se va a ejecutar y de dónde sale.
    3. Se confirma.
  - La instalación corre en un pseudo-terminal visible: `POST /api/clis/{id}/install` y `WS /api/clis/{id}/install/terminal`, con el mismo protocolo que el inicio de sesión (`accounts_login.py`). Va con `powershell -NoProfile -ExecutionPolicy Bypass -Command "<comando oficial>"`.
  - Al acabar, `clis.refresh()` busca también en el `PATH` del usuario leído del registro y en las carpetas conocidas (S3), y `resolve_executable` hace lo mismo.
  - Si lo encuentra, ofrece «Iniciar sesión»: para Claude Code, «Añadir cuenta»; para agy, su terminal de inicio de sesión.
  - Si falla, muestra el código de salida, las últimas líneas y el enlace a la guía oficial.
  - El enlace `?nueva=1` y la acción de la paleta «Añadir cuenta» siguen abriendo «Añadir cuenta» de Claude Code.

### 4. Transcripción en vivo
- **Recorder**: `Recording.snapshot(fromSample)` devuelve el WAV de lo grabado desde una muestra dada, sin parar de grabar. Los niveles ya marcan los silencios.
- **whisper-server** arranca con `-ac 512` (S1). `WhisperServer.transcribe` corta el WAV en trozos de ≤ 9 s por el punto más silencioso de cada final de trozo, y junta los textos.
- **Controller**: mientras se graba, transcribe el audio pendiente cada ~1,5 s:
  - El audio pendiente es el que va desde el último trozo **fijado**.
  - Lo que vuelve es el texto **provisional**: se escribe en el campo en el ancla y sustituye al provisional anterior (se sigue su longitud, como ya se sigue el ancla).
  - Al llegar a una pausa (≥ 0,6 s por debajo del umbral de nivel) o a 8 s de audio pendiente, ese trozo se **fija**: su texto ya no cambia y el siguiente empieza desde ahí. Así cada petición manda poco audio y el texto no salta hacia atrás.
  - Solo hay una petición parcial a la vez: si una tarda, se salta el turno siguiente.
  - Al parar, se transcribe lo pendiente y queda el texto final.
  - Si el usuario escribe en el campo durante el dictado, el provisional se deja de tocar (`trackAnchor` ya lo detecta) y el resto se añade al final.
- **Backend**: `POST /dictation/transcribe` admite `partial=true`. Le da menos prioridad a la cola: una transcripción final no espera detrás de una parcial, porque la parcial pendiente se descarta.
- **Probar micrófono**: usa el mismo flujo, con la transcripción en vivo bajo el medidor de nivel. Si falta el motor o el modelo (`409 engine_missing/model_missing`), muestra solo el nivel y el enlace a Ajustes › Modelos locales.

## Archivos
| Archivo | Cambio |
|---|---|
| `docs/adr/0029-terminals-and-cli-install.md` | nuevo: terminal propio como ejecución «terminal», instalación de CLIs, logos |
| `backend/src/agentic_os/models/run.py` | `RunKind.TERMINAL` (sin migración) |
| `backend/src/agentic_os/services/runs/manager.py` | `launch_terminal`, cierre de los terminales al apagar |
| `backend/src/agentic_os/services/adapters/*` | modo «terminal» (sin instrucciones ni MCP) |
| `backend/src/agentic_os/api/terminals.py` | nuevo: crear, listar y cerrar terminales |
| `backend/src/agentic_os/services/usage/limits.py` | fuera los terminales al sumar el gasto de la cuenta |
| `backend/src/agentic_os/services/clis.py`, `services/runs/launcher.py` | instalador oficial por CLI; buscar en el `PATH` del usuario y en las carpetas conocidas |
| `backend/src/agentic_os/services/cli_install.py`, `api/clis.py` | nuevo: instalación en un pseudo-terminal |
| `backend/src/agentic_os/services/dictation/service.py`, `api/dictation.py`, `services/localmodels/whisper.py` | `partial`, prioridad de la final, `-ac 512` y trozos de ≤ 9 s |
| `frontend/src/pages/home/HomeShortcuts.tsx`, `HomePage.tsx` | accesos directos |
| `frontend/src/components/terminal/*`, `NewTerminalDialog.tsx`, `api/terminals.ts` | panel de terminales propios |
| `frontend/src/components/agentic/CliIcon.tsx`, `theme/palettes.ts` | iconos propios de los CLIs; sustituyen a `CliTag` |
| `frontend/src/pages/clis/ClisPage.tsx`, `AddCliDialog.tsx`, `use-install-terminal.ts` | «Añadir CLI» con instalación |
| `frontend/src/lib/dictation/recorder.ts`, `controller.ts`, `insert.ts` | transcripción en vivo |
| `frontend/src/pages/settings/DictationSection.tsx` | «Probar micrófono» con transcripción en vivo |
| `frontend/src/i18n/es.json` | textos nuevos |

## Tareas (en orden)
1. [ ] Spikes S1–S3; resultados en este plan.
2. [ ] ADR 0029.
3. [ ] Accesos directos en Inicio.
4. [ ] `RunKind.TERMINAL`, `launch_terminal`, API y límites; tests del backend.
5. [ ] Panel de terminales propios y `NewTerminalDialog`; tests de la interfaz.
6. [ ] `CliIcon` en todas partes.
7. [ ] Detección con el `PATH` del usuario; instalación de CLIs (backend y `AddCliDialog`).
8. [ ] Transcripción en vivo: `recorder`, `controller`, backend; «Probar micrófono».
9. [ ] Suites completas (de una en una), lint, `cargo test`, `/code-review`, instalador y prueba del usuario en la app instalada; `validacion.md`.

## Tests previstos
| Test | Cubre |
|---|---|
| `home.test.tsx`: seis accesos con su destino, *tooltip* con ratón y con teclado | CA1 |
| `test_terminals.py`: crear con CLI, cuenta y carpeta (el CLI simulado recibe el entorno de la cuenta y el `cwd`); carpeta que no existe → 422; listar y cerrar; no sale en `/api/runs`; su consumo sale en Consumo agrupado como «Terminal»; no cuenta en el límite de la cuenta | CA2, CA4 |
| `TerminalDock.test.tsx`, `new-terminal.test.tsx`: abrir sin terminales → diálogo; varios en pestañas; siguen al navegar; cerrar la pestaña llama a `DELETE`; carpeta del proyecto, personal u otra | CA2, CA3 |
| `clis.test.tsx` y pruebas de las páginas: el icono de cada CLI, con su nombre accesible, en lugar de las letras | CA5 |
| `clis.test.tsx`: «Añadir CLI» solo con CLIs sin instalar, oculto si están todos; «Añadir cuenta» de Claude igual | CA6 |
| `test_cli_install.py`: con un instalador simulado, la salida llega al terminal; al acabar, el CLI se detecta en una carpeta conocida y en el `PATH` del registro (simulado); error con su código | CA7 |
| `add-cli.test.tsx`: comando visible, confirmación, terminal, «Iniciar sesión» al acabar, error con enlace | CA7 |
| `dictation-live.test.ts`: con un *recorder* y un backend simulados, el texto provisional se sustituye, se fija en las pausas, el final completa; escribir durante el dictado no se pisa | CA8 |
| `test_dictation_api.py`, `test_whisper_server.py`: `partial`, prioridad de la final, `-ac 512` en los argumentos, un WAV de 25 s se corta en trozos de ≤ 9 s por las pausas y se juntan los textos; `test_dictation_real.py` sigue en verde con el motor real | CA8 |
| `dictation-settings.test.tsx`: «Probar micrófono» muestra el texto en vivo; sin motor, solo el nivel y el enlace | CA8 |
| Prueba en la app instalada: terminal propio con una cuenta y una carpeta cualquiera; dictado en vivo; instalar un CLI que falte | CA2, CA7, CA8 |

## Decisiones (ADR)
- **ADR 0029**:
  - el terminal propio es una ejecución de tipo `terminal`, para reaprovechar el pseudo-terminal, la reanudación de los visores y el consumo;
  - su gasto sale en Consumo pero no cuenta para el límite de la cuenta;
  - los CLIs se instalan con su instalador oficial, a la vista y tras confirmar, y se detectan sin reiniciar la app;
  - los CLIs se identifican con iconos propios y neutros, no con sus logos, que son marcas registradas;
  - la transcripción en vivo va por trozos que se fijan en las pausas.
- **Logos**: decidido con el usuario (2026-10-31), iconos propios y neutros que recuerdan a cada CLI por su color y un símbolo simple. No hace falta ningún permiso de marca.
