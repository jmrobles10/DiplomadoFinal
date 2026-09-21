# PitWall · front del asistente de F1 2026

Interfaz web del proyecto **PitWall**, un asistente de chat en español sobre la Fórmula 1 2026
conectado a un agente RAG hecho en n8n. Pensada para personas que no saben de tecnología.

Es una página **estática**: HTML, CSS y JavaScript puro, sin frameworks ni compilación. Funciona
abierta desde el archivo (`file://`) o servida con `python scripts/serve_cors.py 8765 front`.

```
front/
├── index.html      La página completa (íconos SVG monocromos en línea)
├── styles.css      Estilos: blanco y negro estricto; el color solo entra por las fotos y el video
├── app.js          Lógica del chat  ← aquí van las URL de los webhooks (bloque CONFIG)
├── assets/
│   ├── favicon.svg
│   └── envato/     Fotos y video de Envato Elements (no se versionan; ver lista abajo)
├── screenshots/    Capturas de referencia
└── README.md
```

## Diseño

El lenguaje visual sigue el de mysugr.com, traducido a monocromo:

- Tipografía **Figtree** (400/500/700) como equivalente libre de Brandon Text; cuerpo 18 px, titulares grandes y en negrita.
- Fondos blanco y #FAFAFA, tarjetas blancas con sombra suave y esquinas de 16 px, botones tipo píldora
  (negro sobre blanco y blanco con borde negro), chips de sugerencias, mucho aire entre secciones.
- Paleta estrictamente monocroma en CSS, íconos y SVG. **El único color de la página son las fotos y el video.**
- Móvil primero: perfecta a 375 px, sin desplazamiento horizontal, objetivos táctiles de 44 px, foco visible,
  animaciones desactivadas con `prefers-reduced-motion`.

## Recursos gráficos (Envato Elements)

Descárgalos con tu suscripción y guárdalos con estos nombres exactos en `front/assets/envato/`.
Si falta alguno, la página muestra un bloque gris con el nombre del archivo en su lugar y no se rompe.

| Archivo | Uso | Formato sugerido |
|---|---|---|
| `hero.jpg` | Foto principal del inicio (un F1 en pista, en color) | JPG horizontal 3:2, mínimo 1600 px de ancho |
| `detalle-neumaticos.jpg` | Sección "La base de conocimiento" | JPG vertical 4:5 o cuadrado, mínimo 1000 px |
| `loop-pista.mp4` | Video en bucle de la sección "Cómo funciona" | MP4 H.264 sin audio, 16:9, máximo 15 s y 8 MB |
| `detalle-boxes.jpg` | Póster del video mientras carga | JPG 16:9 |
| `detalle-bandera.jpg` | Sección "Dos modos" | JPG vertical 4:5 |
| `detalle-podio.jpg` | Banda "Podium" al final del inicio | JPG vertical 4:5, mínimo 1000 px |
| `hero-podium.jpg` | Foto principal de `podium.html` (celebración en el podio) | JPG horizontal 3:2, mínimo 1600 px de ancho |

Al descargar, Envato pide licenciar cada ítem a un proyecto: usa **PitWall**. No uses fotos con logos de equipos en primer plano.

## Configurar los webhooks

Al inicio de `app.js`:

```js
const CONFIG = {
  APP_NAME: "PitWall",
  WEBHOOK_RAG: "http://localhost:5678/webhook/7f3b2c9e-1a5d-4e8f-9b6a-2c4d8e0f1a23/chat",
  WEBHOOK_DIRECTO: "http://localhost:5678/webhook/c1d2e3f4-5a6b-4c7d-8e9f-0a1b2c3d4e5f/chat",
  TIMEOUT_MS: 90000,
};
```

Los flujos 02 y 03 deben estar **publicados** en n8n para que esas URL respondan. Si las URL contienen
`TU-INSTANCIA` o `REEMPLAZAR`, el front entra en modo demo y responde con ejemplos sin llamar a la red.

## Qué hace la página

- Envía `{ action: "sendMessage", sessionId, chatInput, metadata: { mode, origen } }` al webhook y espera
  `{ output, steps, sources, suggestions, evaluacion, mode }`.
- Mientras espera muestra el panel "Pensando"; al llegar la respuesta lo reemplaza por los pasos reales del
  agente (qué buscó, qué encontró, cómo lo verificó) y la lista de fuentes con documento, artículo y página.
- Interruptor **Con RAG / Sin RAG** y botón **Comparar** para mostrar las dos respuestas lado a lado.
- Guarda la sesión y el historial en el navegador; **Nueva conversación** reinicia ambos.
- Renderiza el Markdown de la respuesta con un conversor propio y seguro (nunca inyecta HTML del servidor).
