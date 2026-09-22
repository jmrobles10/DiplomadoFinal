# PitWall · Speech de 3 minutos

9 diapositivas. 2:10 de exposición + 0:50 de demo.
Antes de empezar: `iniciar_pitwall.bat`, el front abierto en `http://localhost:8765` y una pregunta de calentamiento ya hecha.

---

**[1 · PitWall — 0:00]**
PitWall es el muro de boxes: responde sobre la Fórmula 1 2026 con el reglamento en la mano. Cita el artículo del que sale cada dato y funciona entero dentro de este equipo, sin nube.

**[2 · Le pregunté a un modelo por un piloto de 2026 — 0:12]**
En 2026 la F1 cambió el motor, la aerodinámica y el formato del fin de semana. Un modelo entrenado antes de eso no tiene cómo saberlo, pero responde igual. Le pregunté cuántas victorias tiene Kimi Antonelli y me habló de Kimi Räikkönen, con una cifra que tampoco es cierta. Piloto equivocado, dato falso, y ninguna forma de notarlo.

**[3 · Una pregunta, seis paradas — 0:35]**
Así se arregla eso. Toda pregunta pasa por seis paradas. Entra con un id de sesión. Se reescribe con el historial del chat, para que "¿y el de pilotos?" se convierta en una consulta completa. Se vuelve un vector de 1.024 números. Se buscan los seis artículos más cercanos. El modelo redacta solo con esos artículos. Y un evaluador comprueba cada cifra. La parada cuatro, la búsqueda, es la que convierte esto en RAG, y no es opcional: ocurre siempre, no cuando el modelo decide.

**[4 · 1.056 artículos, no 1.056 trozos — 1:00]**
El archivo se construyó cortando por la numeración del reglamento, no cada mil caracteres. Cada fragmento es un artículo o un sub-artículo completo, con su número, su título y su página. Son 1.056: 923 del reglamento FIA, 80 de guías propias, 53 de la temporada. Cada uno viaja con sus metadatos, por eso la respuesta puede decir "artículo A2.2.1, página 9" y eso se abre en el PDF.

**[5 · Buscar deja de ser buscar palabras — 1:25]**
Aquí está el análisis vectorial. Cada artículo se convierte en un punto de 1.024 coordenadas con bge-m3, que corre en Ollama. La pregunta se convierte en otro punto con el mismo modelo, porque vectores de modelos distintos no se pueden comparar. Buscar es medir el ángulo entre los dos: similitud de coseno. Y como bge-m3 es multilingüe, una pregunta en español recupera un artículo escrito en inglés. En este ejemplo real, "¿cuántos puntos da ganar una carrera?" trajo la guía del fin de semana con 0,66 y el artículo A2.2 con 0,62.

**[6 · Al modelo se le pone a trabajar con límites — 1:50]**
El prompt le ordena usar únicamente los fragmentos recuperados, citar documento y artículo, y decirlo si el dato no está. El agente recuerda la conversación y puede volver a buscar si lo recuperado no alcanza. Y un evaluador, en una segunda llamada a temperatura cero, compara cada cifra contra los fragmentos. Todo esto vive en un flujo de n8n; Qdrant y los modelos responden en localhost.

**[7 · La misma pregunta, con archivo y sin archivo — 2:05]**
Esta es la prueba. Mismo modelo, misma pregunta. Sin archivo responde de memoria y se equivoca de piloto. Con archivo responde con el palmarés oficial y cita la fuente. La mejora no viene del modelo: viene de la base.

**[8 · El archivo no envejece — 2:15]**
Cada fragmento se identifica por el hash de su propio texto. Cada seis horas, y también cuando alguien pregunta, se revisan la API de resultados, Wikipedia y la página de reglamentos de la FIA. Lo que cambió genera hash nuevo y se vectoriza; lo que sigue igual no se toca. En la última ejecución se actualizaron 2 fragmentos de 1.056.

**[9 · Lo que ve quien pregunta — 2:25 → demo]** Lo vemos en vivo.

---

## Demo (0:50)

1. En el front, escribir **"¿Cuántas victorias tiene Kimi Antonelli?"** y pulsar **Comparar**. Las dos respuestas lado a lado.
2. Abrir **"¿Cómo llegué a esta respuesta?"** en la respuesta con archivo: documentos, artículos e insignia de verificación.
3. Si queda tiempo: en n8n, la última ejecución, el nodo de búsqueda con los seis fragmentos y el veredicto del evaluador.

**Cierre:** "La diferencia entre preguntarle a un chat y construir un sistema que primero consulta información propia es la diferencia entre una opinión y una respuesta con fuente."
