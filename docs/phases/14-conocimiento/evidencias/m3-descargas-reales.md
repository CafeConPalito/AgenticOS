# Bloque 3 · Descargas desde las fuentes reales

- **Fecha**: 2026-10-19 · script `spikes/knowledge/s11_real_downloads.py` (se ejecuta desde el entorno del backend).
- **Qué comprueba**: que las URLs, las revisiones fijadas y los `sha256` del catálogo son los correctos, descargando de las fuentes de verdad con el mismo `DownloadManager` que usa la app.

| Entrada | Fuente | Tamaño | Resultado |
|---|---|---|---|
| `ocr-latin` (3 ficheros) | `modelscope.cn` (RapidOCR v3.10.0) | 18,4 MB | Listo en 4,8 s; los tres `sha256` coinciden con los que publica RapidOCR |
| `llama-cpp` b11720 | GitHub *releases* | 19,7 MB | Listo en 0,9 s; el zip se comprueba, se desempaqueta en `engines/llama-cpp/bin/` y se borra (49 MB en disco); `llama-server.exe` existe |
| `e5-small` | Hugging Face, revisión `761b726d…` | 135,4 MB | **Cancelada al 37 %** (50 331 648 bytes en `model_quantized.onnx.part`) y **reanudada** con `Range`: completa en 2,1 s, verificada |

Disco usado al final: 153,8 MB de modelos y 50,3 MB de motores.

## Lo que queda claro
- La reanudación funciona de verdad contra los servidores reales (Hugging Face redirige a su CDN y el `Range` sobrevive a la redirección).
- **Los modelos de OCR solo están en `modelscope.cn`**: no existe un espejo en Hugging Face (`RapidAI/RapidOCR` no existe allí) ni en las *releases* de GitHub de v3.10. Es el único punto de la fase que depende de un servidor fuera de Hugging Face y GitHub. Si se quiere eliminar esa dependencia, los ~18 MB pueden ir dentro del instalador o alojarse en una *release* propia; ver la decisión abierta en el plan.
- Ninguno de los modelos del catálogo pide cuenta; el *token* de Hugging Face queda implementado pero sin uso.
