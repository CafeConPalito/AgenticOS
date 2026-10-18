# ADR 0018: Pull requests, credenciales y claves SSH

- **Estado**: aceptado
- **Fecha**: 2026-10-18
- **Contexto de decisión**: fase 12 ([`spec.md`](../phases/12-control-git/spec.md), [`plan.md`](../phases/12-control-git/plan.md))

## Contexto
La app abre, lee y fusiona pull requests de GitHub y GitLab, y necesita credenciales para hacerlo. Hay que decidir de dónde sale el token, dónde se guarda el que pega la persona, cómo se distinguen los servicios y cómo se traducen sus errores. El principio de partida: **la app no guarda ningún secreto propio**.

## Decisión

### El token es el de git
- Se pide con `git credential fill` (`protocol=https`, `host=<host>`): devuelve el que ya tiene guardado Git Credential Manager (OAuth) o el *helper* que haya configurado la persona, y vale para la API (spike S3).
- Si no hay, solo se abre la ventana de inicio de sesión de GCM cuando la persona pide una acción (crear un pull request, abrirlo desde una tarea). Las lecturas nunca abren ventanas: sin token, `auth_failed` y la UI ofrece pegar uno.
- Un token personal pegado entra en el mismo almacén con `git credential approve`. Se valida (sin saltos de línea ni nulos) y no se devuelve nunca por la API: solo se responde si hay o no hay token de un host.

### Un `Forge` común, dos implementaciones
`services/forges/base.py` define una interfaz con `list`, `get` (estado, checks, revisiones y comentarios), `create`, `merge` (`merge`, `squash`, `rebase`), `describe`, `close`, `reopen` y `update_branch`; GitHub (REST v3, también Enterprise por host) y GitLab (REST v4, también instancias propias) la implementan y devuelven los mismos modelos.

- GitLab no tiene «fusionar con rebase» como opción: se hace `PUT …/rebase` y después `merge`. El borrador es el prefijo `Draft: ` del título, que se quita al leerlo.
- `describe` existe solo para enlazar entre sí los pull requests de una tarea con varios repos: el primero se crea antes de conocer la dirección de los siguientes.

### Detección del servicio
Por el host de la URL del remoto (`github.com`, `gitlab.com`, y los que empiezan por `github.`/`gitlab.`). Para cualquier otro, la persona elige el servicio en los ajustes del repo (`ProjectRepo.forge`); sin eso, `forge_unknown` con el motivo. Se entienden las tres formas de URL de git (https, `ssh://` y la de `git@host:ruta`).

### Errores
`httpx` con 15 s. Los fallos de la API se traducen a códigos estables que la UI muestra en español: `auth_failed` (401, 403), `rate_limited` (429, o 403 con `x-ratelimit-remaining: 0`), `not_found`, `conflict` (405, 406, 409, 422), `network`, `timeout` y `forge_failed` para el resto. Nunca se muestra el cuerpo crudo de la respuesta.

### Pull requests desde una tarea
Uno por repositorio donde la tarea dejó trabajo: se hace *push* de la rama y se abre, con título `T-n: <título>` y descripción con el resumen de la etapa, los cambios (`diff --shortstat`) y la tarea. Si falla uno, los demás siguen y el resultado lo dice por repo. `Project.on_approve = pull_request` lo hace al aprobar y, si algo falla, deja una petición en la bandeja con el motivo.

### Claves SSH (`gitx/ssh.py`)
- Se listan los `~/.ssh/*.pub` con su huella (`ssh-keygen -lf`); una clave sin su mitad privada se marca como huérfana.
- «Generar» crea una `ed25519` con `ssh-keygen`. **Nunca sobrescribe**: si el nombre existe, `key_exists`. El nombre se valida (`^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$`), así que no puede salir de la carpeta.
- «Probar conexión» corre `ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new`: nunca espera una contraseña. GitHub y GitLab contestan con el usuario aunque salgan con 1, así que se lee el saludo y no el código de salida. Host y usuario se validan para que no se cuele una opción (`-oProxyCommand…`).
- Se usa el `ssh` y el `ssh-keygen` de Git for Windows (los que usa git); si no están, los del `PATH`.

## Consecuencias
- Con GCM no hay nada que configurar: quien ya hizo `git push` a GitHub tiene token.
- Un token pegado vale para git y para la API a la vez, y se gestiona con las herramientas de git (`git credential reject`, el gestor del sistema).
- La prueba contra un GitHub real no se puede automatizar sin credenciales: los tests usan un transporte HTTP simulado y un almacén `store` temporal. Queda como prueba manual de la fase.
- Añadir otro servicio (Bitbucket, Gitea) es una clase más que cumpla `Forge`.
