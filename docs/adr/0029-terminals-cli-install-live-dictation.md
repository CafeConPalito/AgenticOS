# ADR 0029: Terminales propios, instalación de CLIs y dictado en vivo

- **Estado**: aceptado (plan aprobado el 2026-10-31 y fase 23 cerrada el 2026-11-01)
- **Fecha**: 2026-10-31
- **Contexto de decisión**: fase 23 ([spec](../phases/23-inicio-clis-voz/spec.md) · [plan](../phases/23-inicio-clis-voz/plan.md))

## Contexto
El usuario quiere:
- abrir Claude Code o Antigravity a mano, con la cuenta y la carpeta que elija, sin crear un agente, y que lo que gaste salga en Consumo;
- instalar desde la app los CLIs que le faltan;
- reconocer cada CLI de un vistazo;
- ver el texto del dictado mientras habla.

Las normas de marca de Anthropic piden aprobación previa para usar su logo. Whisper procesa ventanas de 30 s, así que cada transcripción cuesta lo mismo aunque el audio sea corto.

## Decisión
1. **El terminal propio es una ejecución de tipo `terminal`**, sin agente, tarea ni proyecto. Así reutiliza el pseudo-terminal, los visores por WebSocket y la lectura del consumo. No sale en Ejecuciones (`LISTED_RUN_KINDS`). Su gasto sale en Consumo como «Terminal», pero no cuenta para el límite diario de la cuenta: lo gastado a mano no frena a los agentes.
2. **Los CLIs se instalan con su instalador oficial**, a la vista y tras confirmar:
   - El comando exacto se enseña antes de ejecutarlo.
   - Corre en un pseudo-terminal visible.
   - La app detecta el CLI sin reiniciarse: además del `PATH` del proceso, lee el `PATH` del usuario del registro (expandiendo las variables) y las carpetas conocidas de cada instalador.
3. **Iconos propios y neutros para los CLIs**, no sus logos: un color asociado al CLI y un símbolo simple, sin copiar formas de las marcas registradas. No hace falta permiso de marca.
4. **Dictado en trozos**:
   - whisper-server arranca con una ventana de audio de ~10 s (`-ac 512`). Con ella cada petición cuesta ~1 s y el texto es el mismo en trozos de hasta 10 s.
   - Todo se transcribe en trozos de ≤ 9 s cortados en las pausas; el backend corta también cualquier WAV más largo.
   - En vivo, la interfaz pide el texto provisional del trozo en curso cada ~1,5 s y fija cada trozo en una pausa. El texto no salta hacia atrás.

## Consecuencias
- Un terminal propio tiene los permisos que el CLI pida al usuario. En la carpeta de un proyecto puede cambiar sus ficheros sin pasar por las tareas, igual que fuera de la app.
- Instalar un CLI ejecuta un script descargado de su fabricante. La app lo enseña y pide confirmación, y no instala nada que no sea el instalador oficial.
- Con la ventana corta, un audio de más de ~10 s en una sola petición perdería texto: por eso el corte en trozos está en el backend y no solo en la interfaz.
