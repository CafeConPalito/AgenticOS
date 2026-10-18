# Prueba manual M1: el decisor real (CA2)

El código de producción (`decider.call`, con `resolve_executable`, el entorno limpio y los argumentos de verdad) contra los CLIs reales de esta máquina, con las ramas de la plantilla «Backend y frontend» y tres tareas de ejemplo. 2026-10-18.

| CLI | Modelo | Tarea | Esperado | Elegido | Tiempo | Coste / tokens |
|---|---|---|---|---|---|---|
| Claude Code | `haiku` | Endpoint GET /clientes | Backend | Backend | 7,5 s | 0,00098 USD |
| Claude Code | `haiku` | Botón de modo oscuro | Frontend | Frontend | 7,0 s | 0,00088 USD |
| Claude Code | `haiku` | Filtro de pedidos por fecha (API y pantalla) | las dos | las dos | 6,2 s | 0,00077 USD |
| agy | `gemini-3.8-flash-low` | Endpoint GET /clientes | Backend | Backend | 11,0 s | 11 806 / 101 tokens |
| agy | `gemini-3.8-flash-low` | Botón de modo oscuro | Frontend | Frontend | 9,0 s | 11 806 / 308 tokens |
| agy | `gemini-3.8-flash-low` | Filtro de pedidos por fecha | las dos | las dos | 6,0 s | 11 815 / 101 tokens |

**6 de 6.** Cada rama, tomada o no, trae su motivo en una frase en español. Ninguna llamada dejó ficheros ni cambió la configuración global (spikes S1 y S2). agy no informa de coste (solo tokens), como en la fase 07.
