# PitWall · front del asistente de F1 2026

Interfaz web del proyecto **PitWall**, un asistente de chat en español sobre la Fórmula 1 2026
conectado a un agente RAG hecho en n8n.

Es una página **estática**: HTML, CSS y JavaScript puro. No hay frameworks, ni instalación, ni
paso de compilación. Funciona igual si abres el archivo directamente en el navegador
(`file://`) o si la publicas en GitHub Pages.

```
front/
├── index.html      La página completa (incluye las ilustraciones SVG en línea)
├── styles.css      Los estilos (blanco y negro; el color solo vive en los carros)
├── app.js          La lógica del chat  ← aquí van las URL de los webhooks
├── assets/
│   └── favicon.svg El ícono de la pestaña del navegador
├── screenshots/    Capturas de referencia (móvil y escritorio)
└── README.md       Este archivo
```

---

## 1. Configurar las URL de los webhooks

Abre **`app.js`** y edita el bloque que está al principio del archivo. Es lo único que tienes
que cambiar:

```js
const CONFIG = {
  APP_NAME: "PitWall",
  WEBHOOK_RAG: "https://TU-INSTANCIA.app.n8n.cloud/webhook/REEMPLAZAR/chat",
  WEBHOOK_DIRECTO: "https://TU-INSTANCIA.app.n8n.cloud/webhook/REEMPLAZAR-DIRECTO/chat",
  TIMEOUT_MS: 90000,
};
```

| Línea | Qué es | Qué poner |
| --- | --- | --- |
| `WEBHOOK_RAG` | Flujo de n8n **con** búsqueda en la base de conocimiento | La URL de producción del webhook del agente RAG |
| `WEBHOOK_DIRECTO` | Flujo de n8n **sin** búsqueda (le pregunta directo al modelo) | La URL de producción del segundo webhook |
| `TIMEOUT_MS` | Cuánto espera el front antes de rendirse | `90000` son 90 segundos; súbelo si tu agente es lento |
| `APP_NAME` | El nombre que aparece en las burbujas del asistente | Déjalo en `PitWall` |

En n8n, la URL la copias del nodo **Webhook** con el botón *Production URL*. Ojo: la URL de
prueba (*Test URL*) solo funciona mientras tienes el editor de n8n abierto y escuchando.

> Si todavía no tienes los dos flujos, puedes poner la misma URL en las dos líneas. El
> interruptor «Con RAG / Sin RAG» seguirá funcionando, pero las dos respuestas van a ser iguales.

---

## 2. Modo demo (para probar sin n8n)

Si la URL que está seleccionada todavía contiene los textos **`TU-INSTANCIA`** o
**`REEMPLAZAR`**, el front **no llama a la red**: espera 2,5 segundos y muestra una respuesta
de ejemplo, con pasos, fuentes y sugerencias, como si viniera del agente.

- Sirve para mostrar la página en una presentación sin depender de que n8n esté arriba.
- Mientras está activo, aparece una etiqueta discreta **`modo demo`** en el pie de página.
- Hay respuestas de ejemplo preparadas para: qué cambió en 2026, el modo de adelantamiento,
  el campeonato, el fin de semana con sprint y «soy nuevo en la F1». Cualquier otra pregunta
  recibe una respuesta general.
- Las respuestas de demostración terminan con una línea en cursiva que lo dice claramente,
  para que nadie las confunda con datos verificados.

En cuanto pegas una URL real, el modo demo se apaga solo.

---

## 3. Qué envía y qué espera recibir el front

### Lo que envía (POST)

Encabezado `Content-Type: application/json` y este cuerpo:

```json
{
  "action": "sendMessage",
  "sessionId": "8f1c...-uuid-de-la-conversacion",
  "chatInput": "Explícame el modo de adelantamiento",
  "metadata": { "mode": "rag", "origen": "front" }
}
```

- `sessionId` es un UUID que se crea una sola vez por conversación y se guarda en el navegador.
  Sirve para que el agente pueda tener memoria. Cambia cuando pulsas «Nueva conversación».
- `metadata.mode` vale `"rag"` o `"directo"` según el interruptor de la cabecera.

### Lo que espera recibir

```json
{
  "output": "Texto de la respuesta en **Markdown**",
  "steps": [
    { "tipo": "razonamiento", "titulo": "Entendí la pregunta", "detalle": "..." },
    { "tipo": "busqueda",     "titulo": "Busqué en la base",   "detalle": "..." },
    { "tipo": "herramienta",  "titulo": "Consulté la tabla",   "detalle": "..." }
  ],
  "sources": [
    { "documento": "Reglamento Deportivo FIA 2026", "articulo": "Art. 55.5", "pagina": "112", "url": "https://..." }
  ],
  "suggestions": ["¿Y qué pasó con el DRS?", "¿Cuánta potencia eléctrica tienen?"]
}
```

Solo **`output`** es obligatorio. `steps`, `sources` y `suggestions` son opcionales:

- `steps` se muestran dentro del bloque desplegable **«¿Cómo llegué a esta respuesta?»**.
  El campo `tipo` solo cambia el ícono (`razonamiento`, `busqueda` o `herramienta`).
- `sources` se muestran como **«Fuentes consultadas»**. Si traen `url`, el nombre del documento
  queda como enlace.
- `suggestions` se dibujan como botones de respuesta rápida debajo del último mensaje.

El front es **tolerante** con lo que llega, para que no se rompa por detalles del flujo:

- Si la respuesta es un arreglo (`[{...}]`), toma el primer elemento.
- Si viene envuelta en `json` o `data` (algo típico de n8n), la desenvuelve.
- Si no hay `output`, busca `text`, `message` o `answer`.
- Si la respuesta no es JSON, usa el texto crudo como respuesta.

El texto se interpreta como **Markdown** con un intérprete propio y pequeño: títulos, negrita,
cursiva, `código`, listas con viñeta y numeradas, tablas y enlaces. El HTML se escapa siempre
antes de mostrarlo, así que el servidor no puede inyectar etiquetas en la página.

### En n8n

Al final del flujo pon un nodo **Respond to Webhook** en modo *JSON* con algo así:

```
{
  "output": "{{ $json.output }}",
  "steps": {{ JSON.stringify($json.steps ?? []) }},
  "sources": {{ JSON.stringify($json.sources ?? []) }},
  "suggestions": {{ JSON.stringify($json.suggestions ?? []) }}
}
```

Y en el nodo **Webhook** (pestaña *Options*) agrega **`Allowed Origins (CORS)`**. Si no lo haces,
el navegador va a bloquear las llamadas desde GitHub Pages con un error de CORS:

- Para pruebas: `*`
- Para producción: `https://TU-USUARIO.github.io`

---

## 4. Probarlo en tu computador

**Opción rápida:** doble clic en `index.html`. Funciona, incluido el modo demo.

**Opción recomendada** (igual de simple, y sin sorpresas con rutas o CORS), desde la carpeta
`front/`:

```bash
python -m http.server 8765
```

Y abre <http://localhost:8765>.

Lista de chequeo para una demostración:

1. Pulsa una de las preguntas sugeridas y mira el panel **«Pensando»** con el carro en la pista.
2. Abre **«¿Cómo llegué a esta respuesta?»** para ver los pasos y las fuentes.
3. Escribe una pregunta y pulsa **«Comparar»**: la misma pregunta va a los dos flujos y las
   respuestas quedan lado a lado (una al lado de la otra en computador, una debajo de la otra
   en celular).
4. Recarga la página: la conversación se restaura.
5. Pulsa **«Nueva conversación»**: se borra el historial y empieza otra sesión.

---

## 5. Publicar en GitHub Pages

GitHub Pages solo puede publicar la **raíz** de una rama o la carpeta `/docs`. Como el front vive
en `front/`, tienes tres caminos. Elige uno.

### Opción A · Rama `gh-pages` con un solo comando (la más simple)

Desde la raíz del repositorio, con todo confirmado (*commit*) en `main`:

```bash
git subtree push --prefix front origin gh-pages
```

Eso sube el contenido de `front/` a la raíz de una rama llamada `gh-pages`. Después, en GitHub:

**Settings → Pages → Build and deployment → Source: _Deploy from a branch_ → Branch: `gh-pages` / `(root)` → Save.**

Cada vez que cambies el front, repites el mismo comando.

### Opción B · GitHub Actions (se publica solo en cada push)

Crea el archivo `.github/workflows/pages.yml` en la raíz del repositorio:

```yaml
name: Publicar front en GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  publicar:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: front
      - id: deployment
        uses: actions/deploy-pages@v4
```

Y en GitHub: **Settings → Pages → Source: _GitHub Actions_.**

### Opción C · Copiar a `/docs`

Copia `index.html`, `styles.css`, `app.js` y la carpeta `assets/` dentro de `docs/`, y configura
**Settings → Pages → Branch: `main` / `/docs`**. Es la opción más manual: te toca acordarte de
copiar los archivos cada vez que cambies algo.

### Después de publicar

La página queda en `https://TU-USUARIO.github.io/rag-f1-n8n/`. Revisa dos cosas:

1. Que el chat responda. Si ves un error de conexión, casi siempre es **CORS**: vuelve al punto 3
   y agrega el origen en el nodo Webhook de n8n.
2. Que la URL del sitio sea `https://`. Si el webhook fuera `http://`, el navegador bloquearía la
   llamada por contenido mixto. Las URL de n8n Cloud ya son `https://`.

---

## 6. Notas de diseño y accesibilidad

- La interfaz es **estrictamente blanco y negro**. El único color de la página está en las
  ilustraciones de los carros de Fórmula 1, que son SVG dibujados a mano (no hay imágenes ni
  logos: ninguna ilustración representa a un equipo real).
- Las ilustraciones van **en línea** dentro de `index.html`, como símbolos SVG reutilizables.
  Por eso la página funciona abierta desde `file://` sin peticiones adicionales. El color de cada
  carro se cambia con una clase (`livery--papaya`, `livery--rosso`, `livery--plata`,
  `livery--navy`, `livery--verde`, `livery--azul`, `livery--blanco`).
- Tipografías: **IBM Plex Mono** para etiquetas y datos, **Space Grotesk** para el texto. Se
  cargan desde Google Fonts; si no hay internet, el navegador usa tipografías del sistema y la
  página se ve bien igual.
- Diseño **mobile-first**: pensado para 375 px de ancho y probado hasta 1280 px, sin desborde
  horizontal.
- Si en tu sistema operativo tienes activado *reducir movimiento*, la animación del carro en el
  panel «Pensando» se desactiva sola.
- La lista de mensajes es una región `aria-live`, los botones e inputs tienen etiquetas y el foco
  del teclado siempre se ve.
- Atajos: **Enter** envía, **Shift+Enter** hace un salto de línea.

## 7. Qué se guarda en el navegador

Solo en el `localStorage` de quien visita la página, nada viaja a otro servidor:

| Clave | Para qué |
| --- | --- |
| `pitwall.sessionId` | El identificador de la conversación actual |
| `pitwall.history.<sessionId>` | Los mensajes ya mostrados, para restaurarlos al recargar |
| `pitwall.mode` | Si dejaste seleccionado «Con RAG» o «Sin RAG» |

«Nueva conversación» borra el historial de esa sesión y crea una nueva. Si el navegador tiene el
almacenamiento bloqueado, la página sigue funcionando: solo pierde la memoria al recargar.

---

Proyecto final · Diplomado en IA Generativa · Mateo Robles · 2026
