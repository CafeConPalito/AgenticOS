# Fase 15: Ampliación del conocimiento · Validación

## Tests automáticos
```
PENDIENTE DE RELLENAR AL FINAL DE LA FASE
```

## Criterios de aceptación
| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| CA1 | Un agente llama a `propose_knowledge` basándose en un PDF: documento «Propuesto» vinculado al PDF, en la Inbox y en el filtro «Propuestos» | ⏳ | |
| CA2 | Un propuesto no aparece en el contexto, `search_knowledge` ni `read_knowledge` hasta aceptarlo | ⏳ | |
| CA3 | Aceptar (con edición de título, texto y nivel) lo procesa sin conversión; rechazar lo descarta y queda registrado | ⏳ | |
| CA4 | El PDF original y su Markdown no cambian | ⏳ | |
| CA5 | Máximo por ejecución, tamaño, duplicados y ajuste que desactiva, con el motivo en palabras | ⏳ | |
| CA6 | «Generado por agente», procedencia en la ficha, marca en el índice y en los resultados | ⏳ | |
| CA7 | El grafo distingue fichero / web / imagen / aceptado / pendiente, con aristas, filtros, búsqueda y clic | ⏳ | |
| CA8 | Relaciones en local, con umbral y tope, recalculadas al indexar, quitar o cambiar de modelo | ⏳ | |
| CA9 | El grafo mejora el acierto sin empeorar los resultados directos | ⏳ | |
| CA10 | Fluido con 300 documentos y 1 000 aristas | ⏳ | |
| CA11 | Borrar el origen no borra el derivado: «origen eliminado» | ⏳ | |
| CA12 | Con el binario empaquetado, el flujo completo funciona | ⏳ | |
| CA13 | `knowledge_map` agrupa en temas coherentes y estables | ⏳ | |
| CA14 | `explore_knowledge` y `knowledge_path` respetan saltos, filtros, topes y visibilidad | ⏳ | |
| CA15 | Una pregunta a dos saltos se resuelve explorando y no con la búsqueda sola | ⏳ | |
| CA16 | Un agente usa mapa → explorar → leer; queda en el registro; el contexto incluye los temas | ⏳ | |

## Code review
| Hallazgo | Severidad | Resolución |
|---|---|---|

## Retro
- **Cambios respecto a la spec**:
- **Impacto en fases futuras**:

## Cierre
- [ ] OK del usuario
- [ ] Merge a `main` (`--no-ff`)
- [ ] Tag `v1.7`
- [ ] `docs/roadmap.md` actualizado
