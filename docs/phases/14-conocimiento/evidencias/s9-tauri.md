# S9 · Tauri: rutas al soltar ficheros, visor y CSP

- **Fecha**: 2026-10-18 · Tauri 2.12.1, `tauri-utils` 2.10.1, `@tauri-apps/api` 2.12.1, `tauri-plugin-dialog` 2.8.1, WebView2.
- **Método**: lectura del código fuente de las *crates* en `~/.cargo/registry` y de los tipos de `node_modules/@tauri-apps/api`. **No se ha podido comprobar con una ventana real** (no hay forma de arrastrar un fichero ni de ver la ventana desde esta sesión): esa parte queda como prueba manual del bloque 8.

## Verificado
1. **Arrastrar y soltar con rutas reales**: `drag_drop_enabled` vale `true` por defecto (`tauri-utils/src/config.rs`, `Default for WindowConfig`). `getCurrentWebview().onDragDropEvent` entrega `{ type: 'drop', paths: string[], position }` con las rutas absolutas del sistema de ficheros (`webview.d.ts`). El ratón sobre la zona de suelta se sigue con `enter`/`over`/`leave` (posición en píxeles físicos, relativa al *webview*).
2. **Selector de ficheros**: `dialog:allow-open` ya está concedido en `capabilities/default.json`. `open({ multiple: true, directory: false, filters })` devuelve las rutas; solo hay que ampliar la descripción del permiso.
3. **Abrir el original y «Mostrar en la carpeta»**: lo hace el **backend** (`os.startfile` y `explorer /select,`), así que no hace falta ninguna capacidad nueva de Tauri (no se añade `opener` ni `shell:open` a la interfaz).
4. **El tablero (dnd-kit)** usa eventos de puntero, no el arrastrar y soltar HTML5, así que `drag_drop_enabled = true` no lo afecta.

## Pendiente de la prueba manual del bloque 8 (con plan B)
| Punto | Qué comprobar | Plan B |
|---|---|---|
| Visor de PDF | `<iframe src="http://127.0.0.1:<puerto>/knowledge/docs/<id>/original">` muestra el PDF con el visor integrado de WebView2 (respuesta `Content-Type: application/pdf` y `Content-Disposition: inline`) | `pdf.js` (Apache 2.0, ~1 MB) en un diálogo |
| Imágenes | `<img>` desde el backend (`img-src http://127.0.0.1:*`) | `blob:` obtenido con `fetch` |
| CSP | `default-src 'self'` bloquea marcos y, hoy, imágenes del backend: hay que añadir `frame-src http://127.0.0.1:* http://localhost:*` y ampliar `img-src` (la `connect-src` ya los admite) | — |
| Sin fuga de acceso | `GET …/original` sirve **solo** documentos registrados (por id), nunca una ruta recibida | — |
