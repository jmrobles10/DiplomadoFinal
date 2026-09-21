# PitWall · Guion de presentación (10 minutos)

Cubre los 14 puntos mínimos de la consigna. Tiempos sugeridos entre corchetes. Total: 9 min 30 s + margen.

## 1. Nombre del proyecto [0:15]
**PitWall**: el muro de boxes desde donde el ingeniero de pista responde al piloto con datos en la mano. Un asistente RAG sobre la Fórmula 1 2026.

## 2. Tema elegido [0:20]
La Fórmula 1 en 2026: el mayor reinicio reglamentario de la historia moderna (nuevo carro, nuevo motor híbrido 50/50, aerodinámica activa, 11 equipos) y una temporada en curso que los modelos de lenguaje no conocen.

## 3. Problema o necesidad [0:40]
- Un aficionado nuevo se pierde entre reglas nuevas y jerga en inglés.
- Si le pregunta a un chat "a secas", el modelo responde con reglas viejas o inventa: en la prueba, el modelo directo dijo que el cambio de 2026 "todavía está por venir".
- Necesitamos respuestas actuales, verificables y en lenguaje simple.

## 4. Descripción general de la solución [0:40]
Un agente conversacional que, antes de responder, busca en una base de conocimiento propia (reglamentos FIA vigentes + temporada 2026 + guías en español), redacta en español citando el artículo, verifica que la respuesta esté respaldada y muestra al usuario cómo llegó a ella. Dos interfaces: el chat de n8n para ver el flujo por dentro y un front en blanco y negro para cualquier persona.

## 5. Herramientas utilizadas [0:30]
| Capa | Herramienta | Costo |
|---|---|---|
| Orquestación y agente | n8n 2.39 en local (Node 24) | Gratis |
| Base vectorial | Qdrant 1.19 en local, persistente en disco | Gratis |
| Embeddings | `bge-m3` en Ollama (local), 1.024 dimensiones, multilingüe | Gratis |
| Modelo generador | `qwen3:8b` en Ollama (local, tool calling) | Gratis |
| Modelo evaluador | `qwen3:8b` en Ollama (temperatura 0, salida JSON) | Gratis |
| Preparación de datos | Python (pypdf, chunking por artículo) | Gratis |
| Front | HTML, CSS y JS sin frameworks | Gratis |

## 6. Base de conocimiento [1:00]
- **Reglamentos FIA 2026 vigentes**: Sección A (general y puntos, Issue 03), B Deportivo (Issue 08), C Técnico (Issue 20), D Financiero (Issue 07). 923 fragmentos.
- **Temporada 2026** desde la API oficial de resultados (Jolpica): calendario de 23 rondas, resultados de 14 carreras y 5 sprints, clasificaciones, equipos y pilotos. 24 documentos en español.
- **Narrativa de la temporada** (Wikipedia): cambios de equipos y pilotos, resumen de carreras. 29 fragmentos.
- **11 guías propias en español** escritas para no expertos y verificadas contra el reglamento: qué cambia en 2026, aerodinámica activa, unidad de potencia, modo de adelantamiento, fin de semana y puntos, banderas y sanciones, equipos, temporada al día, glosario de 79 términos, guía para nuevos aficionados, reglamento financiero. 80 fragmentos.
- Total: **1.056 fragmentos**, cada uno con metadatos (documento, artículo, título, página, tipo, fuente).
- Decisión clave: **chunking por artículo**, no por tamaño fijo, para que cada cita apunte a un artículo real. Los formularios del reglamento (líneas de puntos) se descartaron porque rompían los embeddings.

## 7. Flujo RAG implementado [1:30]
Mostrar el lienzo de n8n del flujo 02:
1. **Chat Trigger** recibe la pregunta (del front o del chat de n8n) con un id de sesión.
2. **Reformulador + recuperación** (qwen3:8b + bge-m3): la pregunta se reescribe con el historial y se buscan los 6 fragmentos más parecidos en Qdrant antes de que el agente responda.
2b. **Agente** (qwen3:8b vía Ollama) con memoria de conversación y una regla de oro: siempre consultar la herramienta antes de afirmar un dato.
3. **Recuperador**: la herramienta `buscar_base_conocimiento` convierte la consulta en un vector con bge-m3 (Ollama) y trae los 6 fragmentos más parecidos de Qdrant. El agente formula la consulta en inglés para el reglamento y en español para la temporada.
4. **Generador**: el agente redacta en español, cita documento y artículo, y agrega un bloque oculto con su razonamiento y tres preguntas sugeridas.
5. **Formateo**: un nodo de código extrae los pasos reales (qué buscó, qué encontró) y las fuentes con metadatos.
6. **Evaluador** (qwen3:8b vía Ollama): recibe respuesta y fragmentos y devuelve si está fundamentada.
7. **Respuesta final** al usuario: texto, pasos, fuentes, sugerencias y veredicto.
Flujo 01 (ingesta) y flujo 03 (chat directo para comparar) se muestran en 20 segundos.

## 8. Ejemplo de pregunta [0:20]
"¿Cuántos puntos da ganar una carrera en 2026 y cuántos una sprint?"

## 9. Información recuperada [0:30]
Mostrar el panel "Pensando" del front o el nodo de la herramienta en n8n: consulta `points scored main race sprint session`, fragmento del Reglamento General 2026, Artículo A2.2 "Championship points system", página 10, sub-artículos A2.2.2 a A2.2.3.

## 10. Respuesta generada [0:30]
"Ganar una carrera principal otorga 25 puntos y una sprint 8 puntos..." con la tabla 25-18-15-12-10-8-6-4-2-1 y 8-7-6-5-4-3-2-1, las condiciones del 75 % y 50 % de la distancia, y la línea "Fuentes: Reglamento General 2026 (Sección A), Art. A2.2.1 · A2.2.2". Veredicto del evaluador: respaldada.

## 11. Decisiones de diseño [1:00]
- Agente con herramienta en vez de cadena fija: puede repreguntar cuando la pregunta es vaga y buscar varias veces.
- Chunking por artículo y metadatos ricos: citas verificables.
- Consulta multilingüe: reglamento en inglés, usuario en español.
- Persistencia real: Qdrant en disco y memoria por sesión; nada se pierde al cerrar el chat.
- Thinking visible y honesto: pasos reales del agente, no una animación.
- Evaluador como segunda opinión barata.
- Todo local: n8n, Qdrant, Ollama y el front corren en el mismo PC; no hay ninguna API externa ni costo por pregunta.
- Podium, la segunda sección: un RAG separado (colección, flujo, memoria y chat propios) sobre la historia de los pilotos desde 1950; demuestra que la misma arquitectura sirve para otra base sin mezclar conocimientos.
- La base se actualiza sola: cada 6 h y con cada consulta (en segundo plano) se revisan la API de resultados, Wikipedia y la página de reglamentos de la FIA; como el id de cada fragmento es el hash de su contenido, solo se vectoriza lo nuevo y se retira lo obsoleto, sin duplicar ni reescribir lo demás.

## 12. Dificultades encontradas [1:00]
- La key gratuita de Gemini para usuarios nuevos solo permite 20 respuestas al día con `gemini-3.6-flash`: se resolvió pasando a una key de Gemini con facturación (costo de centavos); Groq queda como plan B gratuito.
- Los embeddings gratuitos toleran unos 30 mil tokens por minuto: la ingesta se hizo en lotes de 20 con pausas de 15 s.
- Formularios del reglamento con miles de puntos suspensivos devolvían vectores vacíos: se limpiaron.
- El PDF técnico extrae la ligadura "ff" como la letra "a" ("eaect"): se reparó con un diccionario.
- Node 24 resuelve `localhost` como IPv6 y Qdrant escucha en IPv4: la credencial usa `127.0.0.1`.

## 13. Mejoras futuras [0:30]
- Reranking de fragmentos y filtros por tipo de fuente.
- Actualización automática de resultados cada lunes desde la API.
- Respuesta en streaming en el front.
- Evaluación sistemática con un banco de 50 preguntas y métricas de fundamentación.
- Voz: preguntar por audio desde el celular.

## 14. Demostración [1:30]
Seguir el guion de `banco_preguntas_demo.md`: pregunta 1 en modo Sin RAG y luego Con RAG; pregunta 9 (líder del campeonato); pregunta 15 (pregunta vaga, el agente repregunta); pregunta 18 (fuera de la base, el agente lo admite). Cerrar mostrando la ejecución nodo por nodo en n8n.

## Cierre [0:15]
"La diferencia entre preguntarle a un chat y construir un sistema que primero consulta información propia es la diferencia entre una opinión y una respuesta con fuente."
