/* =========================================================
   PitWall · app.js
   Front estático (sin frameworks, sin build) para un agente
   RAG de n8n. Vanilla ES2020.
   ========================================================= */

/* ---------------------------------------------------------
   1 · CONFIGURACIÓN  —  esto es lo único que debes editar
   --------------------------------------------------------- */
/** Cada página puede redefinir la configuración antes de cargar este archivo
 *  (window.PITWALL_OVERRIDES). Así palmares.html usa su propio webhook, su
 *  propia sesión y su propio historial: los chats no se mezclan. */
const OV = window.PITWALL_OVERRIDES || {};

const CONFIG = Object.assign({
  APP_NAME: "PitWall",
  WEBHOOK_RAG: "http://localhost:5678/webhook/7f3b2c9e-1a5d-4e8f-9b6a-2c4d8e0f1a23/chat",
  WEBHOOK_DIRECTO: "http://localhost:5678/webhook/c1d2e3f4-5a6b-4c7d-8e9f-0a1b2c3d4e5f/chat",
  TIMEOUT_MS: 180000, // modelo local: la primera respuesta puede tardar más de un minuto mientras Ollama carga el modelo
}, OV.CONFIG || {});

/* =========================================================
   2 · CONSTANTES
   ========================================================= */

/** Si la URL todavía tiene los marcadores de posición, el front
 *  no llama a la red: responde con una respuesta de ejemplo. */
const MOCK_MARCAS = ["TU-INSTANCIA", "REEMPLAZAR"];
const MOCK_DELAY_MS = 2500;

const BIENVENIDA = OV.BIENVENIDA ||
  "Hola, soy PitWall. Consulto el reglamento oficial y la temporada 2026 antes de responderte. ¿Qué quieres saber?";

/** Respaldo: si el HTML no trae los chips, se usan estos. */
const MISSION_FALLBACK = [
  "¿Qué cambió en la F1 en 2026?",
  "Explícame el modo de adelantamiento",
  "¿Quién va ganando el campeonato?",
  "¿Cómo funciona un fin de semana con sprint?",
  "Soy nuevo en la F1, ¿por dónde empiezo?",
];

const ESTADOS_PENSANDO = OV.ESTADOS_PENSANDO || [
  "Leyendo tu pregunta",
  "Buscando en el reglamento FIA 2026",
  "Revisando la temporada 2026",
  "Redactando la respuesta",
];

const ICONO_PASO = {
  razonamiento: "#ico-chispa",
  busqueda: "#ico-lupa",
  herramienta: "#ico-tuerca",
  evaluacion: "#ico-escudo",
};

/** Rótulos de la insignia de evaluación (monocroma). */
const VEREDICTO = {
  si: "Verificada contra las fuentes",
  no: "Con afirmaciones sin respaldo",
  neutro: "Respuesta revisada",
};

const LS_PREFIX = OV.LS_PREFIX || "pitwall";   // palmares.html usa "palmares": sesión e historial aparte
const LS = {
  sid: LS_PREFIX + ".sessionId",
  modo: LS_PREFIX + ".mode",
  hist: (sid) => LS_PREFIX + ".history." + sid,
};

/* =========================================================
   3 · UTILIDADES
   ========================================================= */

const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

/** Solo dejamos pasar esquemas de enlace seguros. */
function urlSegura(url) {
  const u = String(url || "").trim();
  return /^(https?:\/\/|mailto:|#|\.?\/)/i.test(u) ? escapeHtml(u) : "";
}

function uuid() {
  try {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    if (window.crypto && window.crypto.getRandomValues) {
      const b = window.crypto.getRandomValues(new Uint8Array(16));
      b[6] = (b[6] & 0x0f) | 0x40;
      b[8] = (b[8] & 0x3f) | 0x80;
      const hex = Array.prototype.map.call(b, (x) => x.toString(16).padStart(2, "0")).join("");
      return (
        hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" + hex.slice(12, 16) + "-" +
        hex.slice(16, 20) + "-" + hex.slice(20)
      );
    }
  } catch (e) { /* seguimos al respaldo */ }
  return "pw-" + Date.now().toString(16) + "-" + Math.random().toString(16).slice(2, 10);
}

/* almacenamiento local, siempre entre try/catch */
function lsGet(clave) {
  try { return window.localStorage.getItem(clave); } catch (e) { return null; }
}
function lsSet(clave, valor) {
  try { window.localStorage.setItem(clave, valor); return true; } catch (e) { return false; }
}
function lsDel(clave) {
  try { window.localStorage.removeItem(clave); } catch (e) { /* nada */ }
}

function horaCorta(ts) {
  try {
    return new Date(ts || Date.now()).toLocaleTimeString("es-CO", {
      hour: "2-digit", minute: "2-digit", hour12: false,
    });
  } catch (e) { return ""; }
}

function esMock(url) {
  const u = String(url || "");
  return !u || MOCK_MARCAS.some((m) => u.indexOf(m) !== -1);
}

/* =========================================================
   4 · RENDERIZADOR DE MARKDOWN (mínimo, propio)
   Escapa el HTML primero: nunca se inyecta marcado del servidor.
   Soporta: párrafos, saltos, **negrita**, *cursiva*, `código`,
   bloques ```, títulos #/##/###, listas con viñeta y numeradas,
   tablas | a | b | , líneas --- y enlaces [texto](url).
   ========================================================= */

function mdInline(texto) {
  let s = escapeHtml(texto);

  // 1. protegemos el código en línea
  const codigos = [];
  s = s.replace(/`([^`]+)`/g, (_m, p1) => {
    codigos.push(p1);
    return "" + (codigos.length - 1) + "";
  });

  // 2. enlaces
  s = s.replace(/!?\[([^\]]*)\]\(([^)\s]+)\)/g, (_m, txt, url) => {
    const href = urlSegura(url);
    const rotulo = txt || href;
    if (!href) return rotulo;
    return '<a href="' + href + '" target="_blank" rel="noopener noreferrer">' + rotulo + "</a>";
  });

  // 3. énfasis
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*\w])\*([^*\n]+)\*/g, "$1<em>$2</em>");

  // 4. devolvemos el código a su lugar
  s = s.replace(/(\d+)/g, (_m, i) => "<code>" + codigos[Number(i)] + "</code>");
  return s;
}

function mdLista(lineas, desde, tipo) {
  const re = tipo === "ul" ? /^[-*•]\s+(.*)$/ : /^\d+[.)]\s+(.*)$/;
  const items = [];
  let i = desde;
  while (i < lineas.length) {
    const cruda = lineas[i];
    const t = cruda.trim();
    const m = t.match(re);
    if (m) { items.push(mdInline(m[1])); i++; continue; }
    // continuación indentada de la viñeta anterior
    if (t !== "" && /^\s{2,}\S/.test(cruda) && items.length) {
      items[items.length - 1] += "<br>" + mdInline(t);
      i++; continue;
    }
    break;
  }
  const html = "<" + tipo + ">" + items.map((x) => "<li>" + x + "</li>").join("") + "</" + tipo + ">";
  return { html: html, i: i };
}

function mdTabla(filas) {
  const celdas = (f) => f.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
  const esSep = (f) => /^[\s|:\-]+$/.test(f) && f.indexOf("-") !== -1;

  let cabecera = null;
  const cuerpo = [];
  filas.forEach((f, idx) => {
    if (esSep(f)) return;
    if (idx === 0 && filas[1] && esSep(filas[1])) { cabecera = celdas(f); return; }
    cuerpo.push(celdas(f));
  });

  let html = '<div class="md-table-wrap"><table>';
  if (cabecera) {
    html += "<thead><tr>" + cabecera.map((c) => "<th>" + mdInline(c) + "</th>").join("") + "</tr></thead>";
  }
  html += "<tbody>";
  cuerpo.forEach((fila) => {
    html += "<tr>" + fila.map((c) => "<td>" + mdInline(c) + "</td>").join("") + "</tr>";
  });
  html += "</tbody></table></div>";
  return html;
}

function mdToHtml(fuente) {
  const lineas = String(fuente == null ? "" : fuente).replace(/\r\n?/g, "\n").split("\n");
  const salida = [];
  let parrafo = [];
  let i = 0;

  const cerrarParrafo = () => {
    if (parrafo.length) {
      salida.push("<p>" + parrafo.map(mdInline).join("<br>") + "</p>");
      parrafo = [];
    }
  };

  while (i < lineas.length) {
    const cruda = lineas[i];
    const t = cruda.trim();

    // bloque de código
    if (/^```/.test(t)) {
      cerrarParrafo();
      i++;
      const buf = [];
      while (i < lineas.length && !/^```/.test(lineas[i].trim())) { buf.push(lineas[i]); i++; }
      i++;
      salida.push("<pre><code>" + escapeHtml(buf.join("\n")) + "</code></pre>");
      continue;
    }

    if (t === "") { cerrarParrafo(); i++; continue; }

    if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) { cerrarParrafo(); salida.push("<hr>"); i++; continue; }

    const tit = t.match(/^(#{1,3})\s+(.*)$/);
    if (tit) {
      cerrarParrafo();
      const n = tit[1].length;
      salida.push("<h" + n + ">" + mdInline(tit[2]) + "</h" + n + ">");
      i++; continue;
    }

    // tabla: al menos dos barras en la línea
    if (/^\|/.test(t) && (t.match(/\|/g) || []).length >= 2) {
      const filas = [];
      while (i < lineas.length && /^\s*\|/.test(lineas[i])) { filas.push(lineas[i].trim()); i++; }
      cerrarParrafo();
      salida.push(mdTabla(filas));
      continue;
    }

    if (/^[-*•]\s+/.test(t)) {
      cerrarParrafo();
      const r = mdLista(lineas, i, "ul");
      salida.push(r.html); i = r.i; continue;
    }
    if (/^\d+[.)]\s+/.test(t)) {
      cerrarParrafo();
      const r = mdLista(lineas, i, "ol");
      salida.push(r.html); i = r.i; continue;
    }

    parrafo.push(t);
    i++;
  }
  cerrarParrafo();
  return salida.join("\n");
}

/* =========================================================
   5 · RESPUESTAS DE EJEMPLO (modo demo)
   Contenido ilustrativo para poder mostrar y probar la
   interfaz sin n8n conectado.
   ========================================================= */

const NOTA_DEMO = "\n\n*Respuesta de demostración: este front todavía no está conectado a n8n.*";

const FUENTES_DEMO = {
  deportivo: {
    documento: "Reglamento Deportivo FIA 2026",
    articulo: "Art. 55.5",
    pagina: "112",
    url: "https://www.fia.com/regulation/category/110",
  },
  tecnico: {
    documento: "Reglamento Técnico FIA 2026",
    articulo: "Art. 5.4 · Unidad de potencia",
    pagina: "48",
    url: "https://www.fia.com/regulation/category/110",
  },
  temporada: {
    documento: "Datos de la temporada 2026",
    articulo: "Clasificación de pilotos",
    pagina: "actualizado tras la última carrera",
  },
  guia: {
    documento: "Guía PitWall en español",
    articulo: "Glosario y conceptos básicos",
    pagina: "3",
  },
};

const PASOS_DEMO = (consulta, cuantos) => [
  {
    tipo: "razonamiento",
    titulo: "Entendí la pregunta",
    detalle: 'Interpreté tu mensaje como una consulta sobre "' + consulta + '" y decidí buscar en el reglamento antes de responder.',
  },
  {
    tipo: "busqueda",
    titulo: "Consulté las fuentes oficiales",
    detalle: "Reglamento General 2026 · Art. A2.2 (pág. 9) | El fin de semana de F1: clasificación, sprint y puntos",
  },
  {
    tipo: "herramienta",
    titulo: "Revisé los datos de la temporada",
    detalle: "Consulté la tabla de resultados 2026 para confirmar que la respuesta esté al día.",
  },
  {
    tipo: "razonamiento",
    titulo: "Redacté la respuesta",
    detalle: "Me basé en el Reglamento General 2026 y en la guía del fin de semana de F1.",
  },
  {
    tipo: "evaluacion",
    titulo: "Revisé que todo tuviera respaldo",
    detalle: "Todo lo que dice está en los documentos oficiales.",
  },
];

const DEMO_RAG = [
  {
    re: /(cambi|nuevo reglamento|2026.*(cambio|nuevo)|qu[eé] hay de nuevo)/i,
    data: {
      output:
        "### Lo que cambió en la Fórmula 1 en 2026\n\n" +
        "2026 es el cambio de reglas más grande en más de una década. Toca el motor, la aerodinámica y hasta el peso del carro.\n\n" +
        "1. **Motores mitad y mitad.** La potencia queda repartida casi 50/50 entre el motor de combustión y la parte eléctrica: unos **400 kW** térmicos y **350 kW** eléctricos.\n" +
        "2. **Adiós al MGU-H.** Se elimina el generador del turbo, la pieza más costosa y difícil de copiar. Eso abrió la puerta a fabricantes nuevos.\n" +
        "3. **Combustible 100 % sostenible.** Nada de gasolina fósil: combustible sintético o de origen biológico.\n" +
        "4. **Aerodinámica activa.** El alerón delantero y el trasero cambian de posición entre el modo de baja resistencia (rectas) y el de carga (curvas).\n" +
        "5. **Sin DRS, con modo de adelantamiento.** El empujón para atacar ya no viene del alerón, viene de la energía eléctrica.\n" +
        "6. **Carros más livianos y angostos.** Alrededor de **30 kg** menos, **10 cm** menos de ancho y una distancia entre ejes más corta.\n\n" +
        "**En una frase:** el carro de 2026 corre con menos ala y más batería, y el piloto tiene que administrar la energía como antes administraba las llantas." +
        NOTA_DEMO,
      steps: PASOS_DEMO("los cambios de reglamento para 2026", 4),
      sources: [FUENTES_DEMO.tecnico, FUENTES_DEMO.deportivo, FUENTES_DEMO.guia],
      suggestions: [
        "¿Por qué quitaron el MGU-H?",
        "Explícame el modo de adelantamiento",
        "¿Qué es la aerodinámica activa?",
      ],
    },
  },
  {
    re: /(adelantamiento|override|drs|sobrepas)/i,
    data: {
      output:
        "### El modo de adelantamiento en 2026\n\n" +
        "En 2026 desaparece el DRS. En su lugar está el **Manual Override**, que el reglamento describe como un *modo de adelantamiento*: en vez de abrir un alerón para tener menos resistencia al aire, el carro que persigue recibe **más energía eléctrica** para acercarse en la recta.\n\n" +
        "**Cómo funciona, paso a paso**\n\n" +
        "1. Te ubicas a **menos de 1 segundo** del carro de adelante en el punto de detección.\n" +
        "2. El sistema se habilita y el piloto pide el despliegue extra con un botón en el volante.\n" +
        "3. El que persigue sostiene hasta **350 kW** de potencia eléctrica hasta cerca de **337 km/h**.\n" +
        "4. El que va adelante, en cambio, empieza a bajar su despliegue desde los **290 km/h**.\n\n" +
        "| Situación | Carro de adelante | Carro que persigue |\n" +
        "| --- | --- | --- |\n" +
        "| Energía eléctrica | baja desde 290 km/h | hasta 350 kW |\n" +
        "| Efecto en la recta | se queda sin empuje | mantiene el empuje |\n\n" +
        "**En palabras sencillas:** el reglamento ya no te regala menos aire en contra, te regala más empuje. El adelantamiento deja de ser un botón que abre el alerón y pasa a ser una decisión de energía: cuándo la gastas y cuándo la guardas." +
        NOTA_DEMO,
      steps: [
        {
          tipo: "razonamiento",
          titulo: "Entendí la pregunta",
          detalle: "La pregunta es sobre el reemplazo del DRS, así que hay que mirar el reglamento deportivo y el técnico.",
        },
        {
          tipo: "busqueda",
          titulo: "Consulté las fuentes oficiales",
          detalle: 'Reglamento Deportivo 2026 · Art. B7.2 (pág. 41) | Reglamento Técnico 2026 · Art. C5.12',
        },
        {
          tipo: "herramienta",
          titulo: "Verifiqué las cifras",
          detalle: "Contrasté los valores de potencia y velocidad con el artículo del reglamento técnico.",
        },
        {
          tipo: "razonamiento",
          titulo: "Redacté la respuesta",
          detalle: "Ordené los pasos, armé la tabla comparativa y cerré con una explicación en lenguaje sencillo.",
        },
      ],
      sources: [FUENTES_DEMO.deportivo, FUENTES_DEMO.tecnico, FUENTES_DEMO.guia],
      suggestions: [
        "¿Y qué pasó con el DRS?",
        "¿Cuánta potencia eléctrica tiene un carro de 2026?",
        "¿Eso hace las carreras más emocionantes?",
      ],
    },
  },
  {
    re: /(campeonato|clasificaci|puntos|l[ií]der|va ganando|quien gana)/i,
    data: {
      output:
        "### Cómo va el campeonato 2026\n\n" +
        "Esta respuesta sale de la tabla de resultados de la temporada, no del reglamento. Como estoy en **modo demo**, te muestro el formato con datos de ejemplo:\n\n" +
        "| Pos | Piloto | Escudería | Puntos |\n" +
        "| --- | --- | --- | --- |\n" +
        "| 1 | Ejemplo A | Escudería 1 | 214 |\n" +
        "| 2 | Ejemplo B | Escudería 2 | 198 |\n" +
        "| 3 | Ejemplo C | Escudería 1 | 173 |\n\n" +
        "Cuando el front esté conectado al agente de n8n, esta tabla se arma con los resultados reales cargados en la base de conocimiento y te digo además **cuántas carreras faltan** y **qué necesita cada piloto** para quedar campeón.\n\n" +
        "Recuerda cómo se reparten los puntos: 25 al ganador, 18 al segundo, 15 al tercero, y así hasta el décimo. En las carreras sprint se reparten 8 puntos al ganador." +
        NOTA_DEMO,
      steps: [
        {
          tipo: "razonamiento",
          titulo: "Entendí la pregunta",
          detalle: "Pides el estado del campeonato: eso son datos de temporada, no reglamento.",
        },
        {
          tipo: "herramienta",
          titulo: "Consulté la tabla de la temporada 2026",
          detalle: "Traje la clasificación de pilotos y de constructores ordenada por puntos.",
        },
        {
          tipo: "busqueda",
          titulo: "Busqué el sistema de puntaje",
          detalle: "Reglamento General 2026 · Art. A2.2 (pág. 9)",
        },
      ],
      sources: [FUENTES_DEMO.temporada, FUENTES_DEMO.deportivo],
      suggestions: [
        "¿Cómo va el campeonato de constructores?",
        "¿Cuántos puntos se reparten en un sprint?",
        "¿Cuántas carreras faltan?",
      ],
    },
  },
  {
    re: /(sprint|fin de semana|formato|viernes|s[aá]bado)/i,
    data: {
      output:
        "### Un fin de semana con sprint, paso a paso\n\n" +
        "Un fin de semana normal tiene tres prácticas, la clasificación y la carrera. Cuando hay **sprint**, el sábado se llena de acción y solo queda una práctica libre.\n\n" +
        "| Día | Sesión | Para qué sirve |\n" +
        "| --- | --- | --- |\n" +
        "| Viernes | Práctica 1 | La única práctica del fin de semana |\n" +
        "| Viernes | Clasificación del sprint | Define la parrilla del sábado |\n" +
        "| Sábado | Carrera sprint | 100 km, sin paradas obligatorias, puntos para los 8 primeros |\n" +
        "| Sábado | Clasificación | Define la parrilla del domingo |\n" +
        "| Domingo | Carrera | La de siempre: 305 km y puntos completos |\n\n" +
        "**Dos detalles que confunden a todo el mundo**\n\n" +
        "- La clasificación del viernes **no** define la parrilla del domingo: solo la del sprint.\n" +
        "- El resultado del sprint **no** cambia el orden de salida de la carrera del domingo.\n\n" +
        "Con el carro cerrado en *parc fermé* desde el viernes, los equipos tienen una sola hora de pista para acertar con la puesta a punto. Por eso los sábados de sprint suelen tener sorpresas." +
        NOTA_DEMO,
      steps: PASOS_DEMO("el formato de un fin de semana con carrera sprint", 3),
      sources: [FUENTES_DEMO.deportivo, FUENTES_DEMO.guia],
      suggestions: [
        "¿Qué es el parc fermé?",
        "¿Cuántos sprints hay en 2026?",
        "¿Cómo se reparten los puntos del sprint?",
      ],
    },
  },
  {
    re: /(nuevo|empiezo|empezar|principiante|no s[eé] nada|b[aá]sico)/i,
    data: {
      output:
        "### Bienvenido. Empecemos por lo esencial\n\n" +
        "No necesitas saber de mecánica para disfrutar una carrera. Con estas cinco ideas ya entiendes el 80 % de lo que pasa en pantalla.\n\n" +
        "1. **Hay dos campeonatos a la vez.** Uno de pilotos y uno de equipos. Cada carrera reparte puntos para los dos.\n" +
        "2. **La clasificación del sábado decide el orden de salida.** Salir adelante vale oro, porque adelantar es difícil.\n" +
        "3. **Las paradas en boxes son parte de la estrategia.** Cambiar llantas cuesta tiempo, pero unas llantas frescas lo devuelven.\n" +
        "4. **Las llantas se gastan y eso cambia todo.** Un carro rápido con llantas viejas es un carro lento.\n" +
        "5. **Las banderas te cuentan la historia.** Amarilla es peligro, roja es sesión detenida, a cuadros es final.\n\n" +
        "**Tres palabras que vas a oír todo el tiempo**\n\n" +
        "- `pole` — el primer puesto en la parrilla de salida.\n" +
        "- `pit stop` — la parada en boxes para cambiar llantas.\n" +
        "- `undercut` — parar antes que tu rival para adelantarlo con llantas nuevas.\n\n" +
        "Cuando quieras, pregúntame por cualquiera de estas y te la explico con un ejemplo de carrera." +
        NOTA_DEMO,
      steps: PASOS_DEMO("una introducción a la Fórmula 1 para principiantes", 2),
      sources: [FUENTES_DEMO.guia, FUENTES_DEMO.deportivo],
      suggestions: [
        "¿Qué es un undercut?",
        "¿Qué significan las banderas?",
        "¿Qué cambió en la F1 en 2026?",
      ],
    },
  },
];

const DEMO_RAG_DEFECTO = {
  output:
    "### Con gusto te ayudo\n\n" +
    "Antes de responder busco en la base de conocimiento, que hoy tiene:\n\n" +
    "- Los **reglamentos oficiales de la FIA 2026**: deportivo, técnico, general y financiero.\n" +
    "- Los **resultados y clasificaciones** de la temporada 2026.\n" +
    "- Guías y un **glosario en español** para quien está empezando.\n\n" +
    "Estoy en **modo demo**, así que todavía no consulto la base real. En cuanto el front quede conectado al agente de n8n, cada respuesta va a llegar con sus fuentes: documento, artículo y página." +
    NOTA_DEMO,
  steps: PASOS_DEMO("tu pregunta", 2),
  sources: [FUENTES_DEMO.guia],
  suggestions: [
    "¿Qué cambió en la F1 en 2026?",
    "Explícame el modo de adelantamiento",
    "Soy nuevo en la F1, ¿por dónde empiezo?",
  ],
  evaluacion: {
    fundamentada: true,
    confianza: "media",
    comentario: "Todo lo que te dije sale de los documentos que aparecen en «Fuentes consultadas».",
  },
};

function demoDirecto(texto) {
  return {
    output:
      "Te respondo con lo que el modelo de lenguaje tiene en su memoria, **sin consultar ningún documento**.\n\n" +
      "En 2026 la Fórmula 1 estrena unidades de potencia con mucho más peso eléctrico, combustible sostenible y aerodinámica que se mueve; el DRS deja su lugar a un modo de adelantamiento basado en energía.\n\n" +
      "Ten en cuenta que en este modo **no puedo mostrarte de dónde salió cada dato**, ni garantizar que las cifras estén al día. Para números exactos, artículos del reglamento o resultados de la temporada, vuelve al modo **Con RAG**." +
      NOTA_DEMO,
    steps: [
      {
        tipo: "razonamiento",
        titulo: "Respondí sin búsqueda",
        detalle: 'Modo directo: el modelo contestó "' + texto.slice(0, 80) + '" con su conocimiento previo, sin consultar la base de conocimiento.',
      },
    ],
    sources: [],
    suggestions: [],
    evaluacion: {
      fundamentada: false,
      confianza: "baja",
      comentario: "Sin búsqueda no hay documentos que respalden las cifras: tómalas como aproximadas.",
    },
  };
}

function respuestaDemo(texto, modo) {
  if (modo === "directo") return demoDirecto(texto);
  const hallado = DEMO_RAG.find((c) => c.re.test(texto));
  return hallado ? hallado.data : DEMO_RAG_DEFECTO;
}

/* =========================================================
   6 · NORMALIZACIÓN DE LA RESPUESTA DEL AGENTE
   ========================================================= */

function primerTexto(obj) {
  const llaves = ["output", "text", "message", "answer"];
  for (let i = 0; i < llaves.length; i++) {
    const v = obj[llaves[i]];
    if (typeof v === "string" && v.trim() !== "") return v;
    if (v && typeof v === "object") {
      const anidado = primerTexto(v);
      if (anidado) return anidado;
    }
  }
  return "";
}

function limpiarPasos(valor) {
  if (!Array.isArray(valor)) return [];
  return valor
    .map((p) => {
      if (typeof p === "string") return { tipo: "razonamiento", titulo: p, detalle: "" };
      if (!p || typeof p !== "object") return null;
      return {
        tipo: String(p.tipo || p.type || "razonamiento").toLowerCase(),
        titulo: String(p.titulo || p.title || ""),
        detalle: String(p.detalle || p.detail || p.descripcion || ""),
      };
    })
    .filter((p) => p && (p.titulo || p.detalle));
}

function limpiarFuentes(valor) {
  if (!Array.isArray(valor)) return [];
  return valor
    .map((f) => {
      if (typeof f === "string") return { documento: f, articulo: "", pagina: "", url: "" };
      if (!f || typeof f !== "object") return null;
      return {
        documento: String(f.documento || f.document || f.titulo || f.source || ""),
        articulo: String(f.articulo || f.article || ""),
        pagina: String(f.pagina || f.page || ""),
        url: String(f.url || f.link || ""),
      };
    })
    .filter((f) => f && (f.documento || f.articulo || f.url));
}

/** { fundamentada, confianza, comentario } → normalizado o null. */
function limpiarEvaluacion(valor) {
  if (!valor || typeof valor !== "object" || Array.isArray(valor)) return null;

  const cruda = valor.fundamentada != null ? valor.fundamentada : valor.grounded;
  let fundamentada = null;
  if (typeof cruda === "boolean") fundamentada = cruda;
  else if (typeof cruda === "string") {
    const t = cruda.trim().toLowerCase();
    if (/^(true|s[ií]|si|yes|1)$/.test(t)) fundamentada = true;
    else if (/^(false|no|0)$/.test(t)) fundamentada = false;
  }

  const confianza = String(valor.confianza || valor.confidence || "").trim();
  const comentario = String(valor.comentario || valor.comment || "").trim();

  if (fundamentada === null && !confianza && !comentario) return null;
  return { fundamentada: fundamentada, confianza: confianza, comentario: comentario };
}

/** Si el agente no mandó el objeto `evaluacion` pero sí un paso de
 *  tipo `evaluacion`, deducimos el veredicto de su texto. */
function evaluacionDePasos(pasos) {
  if (!Array.isArray(pasos)) return null;
  const paso = pasos.find((p) => p && p.tipo === "evaluacion");
  if (!paso) return null;

  const texto = (paso.titulo + " " + paso.detalle).toLowerCase();
  let fundamentada = null;
  if (/sin respaldo|no fundament|no verificad|infundad|sin sustento|sin fuente/.test(texto)) fundamentada = false;
  else if (/respald|fundament|verificad|sustentad|coincide con/.test(texto)) fundamentada = true;

  return { fundamentada: fundamentada, confianza: "", comentario: "" };
}

function limpiarSugerencias(valor) {
  if (!Array.isArray(valor)) return [];
  return valor
    .map((s) => (typeof s === "string" ? s : s && (s.texto || s.text || s.label)))
    .filter((s) => typeof s === "string" && s.trim() !== "")
    .map((s) => s.trim())
    .slice(0, 6);
}

function normalizar(cruda) {
  let d = cruda;

  // arreglo -> primer elemento
  if (Array.isArray(d)) d = d.length ? d[0] : {};
  // envolturas típicas de n8n
  if (d && typeof d === "object" && d.json && typeof d.json === "object") d = d.json;
  if (d && typeof d === "object" && d.data && typeof d.data === "object" && !d.output) d = d.data;

  // no es JSON: el texto crudo es la respuesta
  if (typeof d === "string") {
    return { output: d, steps: [], sources: [], suggestions: [], evaluacion: null, mode: "" };
  }
  if (!d || typeof d !== "object") {
    return { output: "", steps: [], sources: [], suggestions: [], evaluacion: null, mode: "" };
  }

  const texto = primerTexto(d);
  const pasos = limpiarPasos(d.steps || d.pasos);
  return {
    output: texto || "El agente respondió, pero sin texto que mostrar.",
    steps: pasos,
    sources: limpiarFuentes(d.sources || d.fuentes),
    suggestions: limpiarSugerencias(d.suggestions || d.sugerencias),
    evaluacion: limpiarEvaluacion(d.evaluacion || d.evaluation) || evaluacionDePasos(pasos),
    mode: String(d.mode || d.modo || ""),
  };
}

/* =========================================================
   7 · LLAMADA AL AGENTE
   ========================================================= */

function esperar(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function urlDeModo(modo) {
  return modo === "directo" ? CONFIG.WEBHOOK_DIRECTO : CONFIG.WEBHOOK_RAG;
}

/** Etiqueta chiquita RAG / DIRECTO. Si el agente devuelve `mode`, ese manda. */
function etiquetaDeModo(modoLocal, modoServidor) {
  const m = String(modoServidor || modoLocal || "").trim().toLowerCase();
  if (m.indexOf("direct") === 0 || m === "sin rag" || m === "llm") return "DIRECTO";
  return "RAG";
}

async function preguntar(texto, modo) {
  const url = urlDeModo(modo);

  // --- modo demo: no toca la red ---
  if (esMock(url)) {
    await esperar(MOCK_DELAY_MS);
    return normalizar(respuestaDemo(texto, modo));
  }

  const cuerpo = {
    action: "sendMessage",
    sessionId: estado.sid,
    chatInput: texto,
    metadata: { mode: modo, origen: "front" },
  };

  const ctrl = new AbortController();
  let vencido = false;
  const reloj = window.setTimeout(() => { vencido = true; ctrl.abort(); }, CONFIG.TIMEOUT_MS);

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
      signal: ctrl.signal,
    });

    if (!res.ok) {
      const err = new Error("HTTP " + res.status);
      err.codigo = "http";
      err.status = res.status;
      throw err;
    }

    const crudo = await res.text();
    let datos;
    try { datos = JSON.parse(crudo); } catch (e) { datos = crudo; }
    return normalizar(datos);

  } catch (e) {
    if (vencido || (e && e.name === "AbortError")) {
      const t = new Error("timeout");
      t.codigo = "timeout";
      throw t;
    }
    throw e;
  } finally {
    window.clearTimeout(reloj);
  }
}

function mensajeDeError(e) {
  const segundos = Math.round(CONFIG.TIMEOUT_MS / 1000);
  if (e && e.codigo === "timeout") {
    return "Se agotó el tiempo de espera (" + segundos + " s). El agente no alcanzó a responder.";
  }
  if (e && e.codigo === "http") {
    return "El servidor respondió con un error (HTTP " + e.status + "). Revisa que el flujo de n8n esté activo.";
  }
  return "No pude conectarme con el agente. Revisa tu conexión o la URL del webhook en app.js.";
}

async function preguntarSeguro(texto, modo) {
  try {
    const r = await preguntar(texto, modo);
    return {
      ok: true,
      modo: modo,
      output: r.output,
      steps: r.steps,
      sources: r.sources,
      suggestions: r.suggestions,
      evaluacion: r.evaluacion,
      mode: r.mode,
    };
  } catch (e) {
    if (window.console && console.warn) console.warn("[" + CONFIG.APP_NAME + "] fallo la consulta:", e);
    return { ok: false, modo: modo, error: mensajeDeError(e) };
  }
}

/* =========================================================
   8 · ESTADO Y NODOS DEL DOM
   ========================================================= */

const estado = {
  sid: "",
  modo: "rag",
  ocupado: false,
  historial: [],
};

const dom = {
  lista: $("#messages"),
  pensando: $("#thinking"),
  pensandoEstado: $("#thinking-status"),
  pensandoReloj: $("#thinking-timer"),
  form: $("#composer"),
  input: $("#input"),
  enviar: $("#btn-enviar"),
  comparar: $("#btn-comparar"),
  nueva: $("#btn-nueva"),
  etiquetaModo: $("#chat-mode-tag"),
  etiquetaDemo: $("#demo-tag"),
  /* dos interruptores: el de la tarjeta del chat y el del menú de teléfono.
     Son grupos de radio distintos para que los dos puedan quedar marcados. */
  radios: $$('input[name="modo"], input[name="modo-nav"]'),
  chipsHero: $("#mission-chips"),
  nav: $("#nav"),
  navBoton: $("#nav-toggle"),
};

let nodoSugerencias = null;

const MISSION_CHIPS = (function () {
  const desdeHtml = $$("[data-prompt]", dom.chipsHero).map((b) => b.getAttribute("data-prompt"));
  return desdeHtml.length ? desdeHtml : MISSION_FALLBACK;
})();

/* =========================================================
   9 · PLANTILLAS DE RENDER
   ========================================================= */

function htmlPasos(pasos) {
  if (!pasos || !pasos.length) return "";
  const items = pasos.map((p) => {
    const icono = ICONO_PASO[p.tipo] || "#ico-flujo";
    return (
      '<li class="paso">' +
        '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="' + icono + '"/></svg>' +
        "<div>" +
          '<p class="paso__t">' + escapeHtml(p.titulo) + "</p>" +
          (p.detalle ? '<p class="paso__d">' + escapeHtml(p.detalle) + "</p>" : "") +
        "</div>" +
      "</li>"
    );
  });
  return '<ol class="pasos">' + items.join("") + "</ol>";
}

function htmlFuentes(fuentes) {
  if (!fuentes || !fuentes.length) return "";
  const items = fuentes.map((f) => {
    const ref = [f.articulo, f.pagina ? "pág. " + f.pagina : ""].filter(Boolean).join(" · ");
    const href = urlSegura(f.url);
    const doc = escapeHtml(f.documento || "Documento sin nombre");
    const nombre = href
      ? '<a href="' + href + '" target="_blank" rel="noopener noreferrer">' + doc + "</a>"
      : doc;
    return (
      '<li class="fuentes__item">' +
        '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#ico-doc"/></svg>' +
        "<div>" +
          '<p class="fuentes__doc">' + nombre + "</p>" +
          (ref ? '<p class="fuentes__ref">' + escapeHtml(ref) + "</p>" : "") +
        "</div>" +
      "</li>"
    );
  });
  return (
    '<div class="fuentes">' +
      '<p class="label">Fuentes consultadas</p>' +
      '<ul class="fuentes__list">' + items.join("") + "</ul>" +
    "</div>"
  );
}

/** Insignia monocroma con el veredicto de la evaluación. */
function htmlVeredicto(ev) {
  if (!ev) return "";

  let clase = "neutro";
  let texto = VEREDICTO.neutro;
  if (ev.fundamentada === true) { clase = "si"; texto = VEREDICTO.si; }
  else if (ev.fundamentada === false) { clase = "no"; texto = VEREDICTO.no; }

  const extra = ev.confianza
    ? ' <span class="veredicto__extra">· confianza ' + escapeHtml(ev.confianza) + "</span>"
    : "";

  return (
    '<p class="veredicto veredicto--' + clase + '">' +
      '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#ico-escudo"/></svg>' +
      "<span>" + escapeHtml(texto) + extra + "</span>" +
    "</p>"
  );
}

function htmlDetalles(rec) {
  const pasos = htmlPasos(rec.steps);
  const fuentes = htmlFuentes(rec.sources);
  const comentario = rec.evaluacion && rec.evaluacion.comentario
    ? '<p class="comentario">' + escapeHtml(rec.evaluacion.comentario) + "</p>"
    : "";
  // Sin pasos, fuentes ni comentario no hay nada que abrir: el bloque no se dibuja.
  if (!pasos && !fuentes && !comentario) return "";
  return (
    '<details class="detalles">' +
      "<summary>" +
        '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#ico-chevron"/></svg>' +
        "<span>¿Cómo llegué a esta respuesta?</span>" +
      "</summary>" +
      pasos +
      fuentes +
      comentario +
    "</details>"
  );
}

function htmlMeta(nombre, etiqueta, ts) {
  return (
    '<p class="msg__meta">' +
      "<span>" + escapeHtml(nombre) + "</span>" +
      (etiqueta ? '<span class="tag">' + escapeHtml(etiqueta) + "</span>" : "") +
      "<span>" + escapeHtml(horaCorta(ts)) + "</span>" +
    "</p>"
  );
}

function nodoMensajeBot(rec, extraClase) {
  const art = document.createElement("article");
  art.className = "msg msg--bot" + (extraClase ? " " + extraClase : "");
  art.innerHTML =
    htmlMeta(CONFIG.APP_NAME, rec.tag || "", rec.ts) +
    '<div class="bubble">' +
      mdToHtml(rec.output) +
      htmlVeredicto(rec.evaluacion) +
      htmlDetalles(rec) +
    "</div>";
  return art;
}

function nodoMensajeUsuario(rec) {
  const art = document.createElement("article");
  art.className = "msg msg--user";
  art.innerHTML =
    htmlMeta("Tú", "", rec.ts) +
    '<div class="bubble">' + mdToHtml(rec.text) + "</div>";
  return art;
}

function nodoError(rec) {
  const art = document.createElement("article");
  art.className = "msg msg--error";
  art.innerHTML =
    htmlMeta(CONFIG.APP_NAME, rec.tag ? rec.tag + " · Error" : "Error", rec.ts) +
    '<div class="bubble">' +
      '<p class="err__linea">' +
        '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#ico-alerta"/></svg>' +
        "<span>" + escapeHtml(rec.text) + "</span>" +
      "</p>" +
      '<p class="err__acciones">' +
        '<button class="btn btn--outline" type="button" data-retry="1">Reintentar</button>' +
      "</p>" +
    "</div>";
  const boton = $("[data-retry]", art);
  if (boton) {
    boton.addEventListener("click", function () {
      if (estado.ocupado) return;
      if (rec.retryKind === "compare") comparar(rec.retryText);
      else enviar(rec.retryText, { modo: rec.retryKind || estado.modo });
    });
  }
  return art;
}

function nodoComparacion(rec) {
  const caja = document.createElement("div");
  caja.className = "compare";
  caja.innerHTML = '<p class="compare__q">Comparación · «' + escapeHtml(rec.q) + "»</p>";
  rec.items.forEach(function (it) {
    if (it.ok === false) {
      caja.appendChild(nodoError({
        text: it.error, ts: rec.ts, retryText: rec.q, retryKind: "compare", tag: it.tag,
      }));
    } else {
      caja.appendChild(nodoMensajeBot({
        output: it.output, steps: it.steps, sources: it.sources,
        evaluacion: it.evaluacion, tag: it.tag, ts: rec.ts,
      }));
    }
  });
  return caja;
}

function pintarRegistro(rec) {
  let nodo = null;
  if (rec.role === "user") nodo = nodoMensajeUsuario(rec);
  else if (rec.role === "bot") nodo = nodoMensajeBot(rec);
  else if (rec.role === "error") nodo = nodoError(rec);
  else if (rec.role === "compare") nodo = nodoComparacion(rec);
  if (nodo) dom.lista.appendChild(nodo);
}

function refrescarSugerencias() {
  if (nodoSugerencias && nodoSugerencias.parentNode) nodoSugerencias.parentNode.removeChild(nodoSugerencias);
  nodoSugerencias = null;

  const ultimo = estado.historial[estado.historial.length - 1];
  if (!ultimo) return;

  let sugs = [];
  if (ultimo.role === "bot") sugs = ultimo.suggestions || [];
  else if (ultimo.role === "compare") {
    const primero = ultimo.items.find((x) => x.ok !== false);
    sugs = (primero && primero.suggestions) || [];
  }
  if (!sugs.length) return;

  const caja = document.createElement("div");
  caja.className = "chips sugs";
  caja.innerHTML =
    '<p class="label chips__title">' + (ultimo.welcome ? "Preguntas para empezar" : "Puedes seguir con") + "</p>" +
    '<div class="chips__row">' +
      sugs.map((s) => '<button class="chip" type="button" data-prompt="' + escapeHtml(s) + '">' + escapeHtml(s) + "</button>").join("") +
    "</div>";
  dom.lista.appendChild(caja);
  nodoSugerencias = caja;
}

function alFinal() {
  try {
    dom.lista.scrollTop = dom.lista.scrollHeight;
  } catch (e) { /* nada */ }
}

/* =========================================================
   10 · HISTORIAL
   ========================================================= */

function guardarHistorial() {
  lsSet(LS.hist(estado.sid), JSON.stringify(estado.historial.slice(-60)));
}

function cargarHistorial() {
  const crudo = lsGet(LS.hist(estado.sid));
  if (!crudo) return [];
  try {
    const arr = JSON.parse(crudo);
    return Array.isArray(arr) ? arr : [];
  } catch (e) { return []; }
}

function agregar(rec) {
  rec.ts = rec.ts || Date.now();
  estado.historial.push(rec);
  guardarHistorial();
  pintarRegistro(rec);
  refrescarSugerencias();
  alFinal();
}

function repintarTodo() {
  dom.lista.innerHTML = "";
  nodoSugerencias = null;
  estado.historial.forEach(pintarRegistro);
  refrescarSugerencias();
  alFinal();
}

function mensajeBienvenida() {
  agregar({
    role: "bot",
    output: BIENVENIDA,
    steps: [],
    sources: [],
    suggestions: MISSION_CHIPS,
    tag: "",
    welcome: true,
  });
}

/* =========================================================
   11 · PANEL "PENSANDO"
   ========================================================= */

let rotEstado = 0;
let temporizadorEstado = 0;
let inicioReloj = 0;
let temporizadorReloj = 0;

function mostrarPensando(comparando) {
  rotEstado = 0;
  dom.pensandoEstado.textContent = comparando
    ? "Preguntando a los dos agentes"
    : ESTADOS_PENSANDO[0];
  dom.pensando.hidden = false;

  temporizadorEstado = window.setInterval(function () {
    rotEstado = (rotEstado + 1) % ESTADOS_PENSANDO.length;
    dom.pensandoEstado.textContent = ESTADOS_PENSANDO[rotEstado];
  }, 1500);

  inicioReloj = Date.now();
  dom.pensandoReloj.textContent = "0.0 s";
  temporizadorReloj = window.setInterval(function () {
    dom.pensandoReloj.textContent = ((Date.now() - inicioReloj) / 1000).toFixed(1) + " s";
  }, 100);

  alFinal();
}

function ocultarPensando() {
  window.clearInterval(temporizadorEstado);
  window.clearInterval(temporizadorReloj);
  temporizadorEstado = 0;
  temporizadorReloj = 0;
  dom.pensando.hidden = true;
}

/* =========================================================
   12 · FLUJO PRINCIPAL
   ========================================================= */

function marcarOcupado(v) {
  estado.ocupado = v;
  dom.enviar.disabled = v;
  dom.comparar.disabled = v;
  dom.input.setAttribute("aria-busy", v ? "true" : "false");
}

function limpiarCompositor() {
  dom.input.value = "";
  ajustarAlto();
}

async function enviar(texto, opciones) {
  const t = String(texto || "").trim();
  if (!t || estado.ocupado) return;
  const modo = (opciones && opciones.modo) || estado.modo;

  agregar({ role: "user", text: t });
  marcarOcupado(true);
  mostrarPensando(false);

  try {
    const r = await preguntarSeguro(t, modo);
    if (r.ok) {
      agregar({
        role: "bot",
        output: r.output,
        steps: r.steps,
        sources: r.sources,
        suggestions: r.suggestions,
        evaluacion: r.evaluacion,
        tag: etiquetaDeModo(modo, r.mode),
      });
    } else {
      agregar({ role: "error", text: r.error, retryText: t, retryKind: modo });
    }
  } finally {
    ocultarPensando();
    marcarOcupado(false);
    dom.input.focus();
  }
}

async function comparar(texto) {
  const t = String(texto || "").trim();
  if (!t || estado.ocupado) return;

  agregar({ role: "user", text: t });
  marcarOcupado(true);
  mostrarPensando(true);

  try {
    const pares = await Promise.all([preguntarSeguro(t, "rag"), preguntarSeguro(t, "directo")]);
    agregar({
      role: "compare",
      q: t,
      items: [
        Object.assign({}, pares[0], { tag: "RAG" }),
        Object.assign({}, pares[1], { tag: "DIRECTO" }),
      ],
    });
  } finally {
    ocultarPensando();
    marcarOcupado(false);
    dom.input.focus();
  }
}

/* =========================================================
   13 · INTERFAZ: eventos
   ========================================================= */

function ajustarAlto() {
  const el = dom.input;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 180) + "px";
}

/** Deja los dos interruptores (chat y menú) mostrando el mismo modo. */
function sincronizarRadios() {
  dom.radios.forEach(function (r) {
    const debe = r.value === estado.modo;
    if (r.checked !== debe) r.checked = debe;
  });
}

/* --- menú de teléfono --- */
function cerrarMenu() {
  if (!dom.nav || !dom.navBoton) return;
  dom.nav.setAttribute("data-open", "false");
  dom.navBoton.setAttribute("aria-expanded", "false");
}

function alternarMenu() {
  if (!dom.nav || !dom.navBoton) return;
  const abierto = dom.nav.getAttribute("data-open") === "true";
  dom.nav.setAttribute("data-open", abierto ? "false" : "true");
  dom.navBoton.setAttribute("aria-expanded", abierto ? "false" : "true");
}

/* --- huecos de Envato: si la foto o el video no están, queda el
       bloque de respaldo y la maquetación no se mueve --- */
function prepararMedios() {
  $$(".media").forEach(function (fig) {
    const el = $(".media__el", fig);
    if (!el) {
      fig.classList.add("media--fallback");
      return;
    }
    const marcar = function () { fig.classList.add("media--fallback"); };
    el.addEventListener("error", marcar);
    // pudo fallar antes de que este script corriera
    if (el.tagName === "IMG" && el.complete && el.naturalWidth === 0) marcar();
    if (el.tagName === "VIDEO") {
      if (el.error) marcar();
      el.addEventListener("stalled", function () { if (el.error) marcar(); });
    }
  });
}

function actualizarEtiquetas() {
  const rotulo = estado.modo === "directo" ? "Sin RAG" : "Con RAG";
  dom.etiquetaModo.textContent = "Modo · " + rotulo;
  const demo = esMock(urlDeModo(estado.modo));
  dom.etiquetaDemo.hidden = !demo;
  dom.etiquetaDemo.title = demo
    ? "Las URL de los webhooks todavía tienen los valores de ejemplo en app.js, así que las respuestas son de demostración."
    : "";
}

function nuevaConversacion() {
  cerrarMenu();
  lsDel(LS.hist(estado.sid));
  estado.sid = uuid();
  lsSet(LS.sid, estado.sid);
  estado.historial = [];
  dom.lista.innerHTML = "";
  nodoSugerencias = null;
  ocultarPensando();
  marcarOcupado(false);
  limpiarCompositor();
  mensajeBienvenida();
  dom.input.focus();
}

function conectarEventos() {
  dom.form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    const t = dom.input.value;
    if (!t.trim()) { dom.input.focus(); return; }
    limpiarCompositor();
    enviar(t, { modo: estado.modo });
  });

  dom.input.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
      ev.preventDefault();
      const t = dom.input.value;
      if (!t.trim() || estado.ocupado) return;
      limpiarCompositor();
      enviar(t, { modo: estado.modo });
    }
  });

  const placeholderOriginal = dom.input.getAttribute("placeholder") || "";
  dom.input.addEventListener("input", function () {
    ajustarAlto();
    if (dom.input.placeholder !== placeholderOriginal) dom.input.placeholder = placeholderOriginal;
  });

  dom.comparar.addEventListener("click", function () {
    const t = dom.input.value;
    if (!t.trim()) {
      dom.input.focus();
      dom.input.placeholder = "Escribe una pregunta y luego pulsa Comparar…";
      return;
    }
    limpiarCompositor();
    comparar(t);
  });

  dom.nueva.addEventListener("click", nuevaConversacion);

  dom.radios.forEach(function (r) {
    r.addEventListener("change", function () {
      if (!r.checked) return;
      estado.modo = r.value === "directo" ? "directo" : "rag";
      lsSet(LS.modo, estado.modo);
      sincronizarRadios();
      actualizarEtiquetas();
    });
  });

  // menú de teléfono
  if (dom.navBoton) {
    dom.navBoton.addEventListener("click", alternarMenu);
  }
  $$("#nav-panel a").forEach(function (a) {
    a.addEventListener("click", cerrarMenu);
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") cerrarMenu();
  });
  window.addEventListener("resize", function () {
    if (window.innerWidth >= 900) cerrarMenu();
  });

  // chips: los de las sugerencias y los del bloque de datos
  document.addEventListener("click", function (ev) {
    const boton = ev.target && ev.target.closest ? ev.target.closest("[data-prompt]") : null;
    if (!boton) return;
    ev.preventDefault();
    if (estado.ocupado) return;
    const texto = boton.getAttribute("data-prompt") || boton.textContent;
    const zona = document.getElementById("zona-chat");
    if (zona && zona.scrollIntoView) {
      try { zona.scrollIntoView({ block: "start", behavior: "smooth" }); } catch (e) { zona.scrollIntoView(); }
    }
    enviar(texto, { modo: estado.modo });
  });
}

/* =========================================================
   14 · ARRANQUE
   ========================================================= */

function iniciar() {
  // sesión
  const guardado = lsGet(LS.sid);
  estado.sid = guardado || uuid();
  if (!guardado) lsSet(LS.sid, estado.sid);

  // modo
  const modoGuardado = lsGet(LS.modo);
  estado.modo = modoGuardado === "directo" ? "directo" : "rag";
  sincronizarRadios();

  actualizarEtiquetas();
  prepararMedios();
  conectarEventos();
  ajustarAlto();

  // historial
  estado.historial = cargarHistorial();
  if (estado.historial.length) repintarTodo();
  else mensajeBienvenida();

  if (window.console && console.info) {
    console.info(
      "[" + CONFIG.APP_NAME + "] sesión " + estado.sid + " · modo " + estado.modo +
      (esMock(urlDeModo(estado.modo)) ? " · MODO DEMO (edita CONFIG en app.js)" : " · conectado a n8n")
    );
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", iniciar);
} else {
  iniciar();
}
