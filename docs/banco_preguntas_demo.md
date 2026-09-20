# Banco de preguntas para la demo · PitWall

Cada pregunta indica qué debería recuperar el RAG y por qué el chat directo suele fallar o dudar.
Marca con ✅ las que ya probaste y funcionan.

## A. Reglamento vigente (el modelo directo no conoce los cambios de 2026 o los mezcla con años anteriores)

| # | Pregunta | Lo que debe recuperar | Por qué gana el RAG |
|---|---|---|---|
| 1 | ¿Cuánto pesa como mínimo un carro de F1 en 2026? | Reglamento Técnico, Art. C4.1: 726 kg en clasificación y 724 kg en el resto de sesiones, más la masa nominal de los neumáticos; los 768 kg que anunció la FIA incluyen neumáticos | El modelo directo suele decir 798 u 800 kg, y ni siquiera conoce el matiz "sin neumáticos" del reglamento |
| 2 | ¿Qué es el Straight Mode y cuándo lo puede usar un piloto? | Reglamento Técnico C3 (Rear Wing / Front Wing adjustment) y Deportivo B7 | Concepto nuevo de 2026; el directo lo confunde con el DRS |
| 3 | ¿Todavía existe el DRS en 2026? | Deportivo B7 + guías en español | El directo responde con la regla vieja |
| 4 | ¿Cuántos carros quedan eliminados en la Q1 en 2026? | Deportivo B5 (qualifying) | Cambió de 5 a 6 al haber 22 carros |
| 5 | ¿Cuántos puntos da ganar una carrera y cuántos una sprint? | Sección A, Art. A2.2 (sistema de puntos) | El directo puede inventar el punto de vuelta rápida |
| 6 | ¿Qué pasa si un piloto pasa por bandera amarilla doble en clasificación? | Deportivo B1.8.4 | Detalle de artículo; el directo generaliza |
| 7 | ¿Cuál es el tope de gasto (cost cap) y qué pasa si un equipo lo excede? | Financiero D4, D10, D12 | Cifras y sanciones específicas del reglamento |
| 8 | ¿Cuánto tiempo puede tardar el alerón en cambiar de modo? | Técnico C3 (transición ≤ 400 ms) | Dato imposible de saber sin la fuente |

## B. Temporada 2026 (posterior al conocimiento del modelo)

| # | Pregunta | Lo que debe recuperar | Por qué gana el RAG |
|---|---|---|---|
| 9 | ¿Quién va ganando el campeonato de pilotos? | Clasificación de pilotos tras ronda 14 | El directo no tiene datos de 2026 |
| 10 | ¿Quién ganó el Gran Premio de Italia 2026? | Resultados ronda 13 | Idem |
| 11 | ¿Qué pilotos tiene Cadillac y qué motor usan? | Equipos y pilotos 2026 + narrativa | El directo puede saber el anuncio pero no la alineación real |
| 12 | ¿Cuándo es la próxima carrera y dónde? | Calendario 2026 (Azerbaiyán, 26 de septiembre) | Depende de la fecha actual |
| 13 | ¿Por qué el Gran Premio de Baréin se corre en Malasia? | Narrativa: Calendar changes / Postponed and cancelled | Hecho puntual de 2026 |
| 14 | ¿Cuántas victorias lleva Antonelli este año? | Resumen de ganadores 2026 | Conteo exacto desde resultados oficiales |

## C. Conversación guiada (para mostrar que el agente pregunta antes de responder)

| # | Pregunta vaga | Comportamiento esperado |
|---|---|---|
| 15 | "Explícame las reglas" | Debe preguntar: ¿de la carrera, de la clasificación, del carro o de los puntos? con 3 opciones |
| 16 | "Soy nuevo, ¿por dónde empiezo?" | Guía paso a paso desde la guía para nuevos aficionados; ofrece continuar |
| 17 | "¿Y en la sprint?" (después de la 5) | Debe usar la memoria de la conversación y responder sobre puntos de sprint |

## D. Control de honestidad (fuera de la base)

| # | Pregunta | Comportamiento esperado |
|---|---|---|
| 18 | ¿Quién ganó el mundial de 1998? | "No encontré esto en mi base de conocimiento" y ofrece lo que sí tiene (temporada 2026) |
| 19 | ¿Qué piloto es el mejor de la historia? | Aclara que es opinión y que su base cubre el reglamento y la temporada 2026 |

## Guion sugerido de la demo (4 minutos)

1. Pregunta 1 en modo **Sin RAG** → respuesta con cifra vieja. Misma pregunta en **Con RAG** → 768 kg con cita al Art. C4 y panel "Pensando" desplegado.
2. Pregunta 9 en ambos modos → el directo no sabe; el RAG da la tabla con fuente.
3. Pregunta 15 → muestra la conversación guiada con botones.
4. Pregunta 18 → muestra la honestidad del sistema.
5. Cambiar al lienzo de n8n y mostrar la ejecución nodo por nodo de la última pregunta.
