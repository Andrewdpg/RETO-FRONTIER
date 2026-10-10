// Reemplazo de la caja negra: estaciones 1–4 de DESIGN §3.11 (ruta, token, tamaño, JSON y campo m).
// Las estaciones 5–14 están en reglas.ts.
import { createServer, type ServerResponse } from 'node:http';
import { nuevoEstado, procesar, servicioDetenido } from './reglas.ts';

const TOKEN = process.env.TEAM_ENTRYPOINT_TOKEN;
if (!TOKEN) {
  console.error('falta la variable TEAM_ENTRYPOINT_TOKEN: el servidor no arranca sin el token del equipo');
  process.exit(1);
}
const PORT = Number(process.env.PORT ?? 8080);

const TOPE_BYTES = 8192; // log 10976 (8.192 pasa), 10977 (8.193 no)
const TOPE_NIVELES = 20; // log 10999 (20 pasa), 11007 (21 no)

const RUTAS = new Set(['POST /msg', 'POST /__reset', 'GET /health']);

// Estado en memoria (D1).
let estado = nuevoEstado();

const err = (error: string, mensaje: string) => ({ error, mensaje });
const E404 = err('E404', 'ruta desconocida');
const E001 = err('E001', 'no autorizado');
const E101 = err('E101', 'cuerpo demasiado grande');
const E100 = err('E100', 'json inválido');
const E102 = err('E102', 'falta m');

function responder(res: ServerResponse, status: number, cuerpo: unknown) {
  // Sin cuerpo en HEAD: node:http lo descarta solo (log 10967, 10970).
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(cuerpo));
}

// Máximo anidamiento de arrays y objetos; el exterior es el nivel 1. JSON.parse no tiene tope (log 10972).
function profundidad(texto: string): number {
  let nivel = 0, max = 0, enString = false;
  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    if (enString) {
      if (c === '\\') i++;
      else if (c === '"') enString = false;
    } else if (c === '"') enString = true;
    else if (c === '[' || c === '{') max = Math.max(max, ++nivel);
    else if (c === ']' || c === '}') nivel--;
  }
  return max;
}

function atender(metodo: string, url: string, auth: string | undefined, cuerpo: Buffer): [number, unknown] {
  const ruta = `${metodo} ${url.split('?')[0]}`; // la query se ignora (log 68)
  if (!RUTAS.has(ruta)) return [404, E404];
  if (auth !== `Bearer ${TOKEN}`) return [401, E001];
  if (ruta === 'GET /health') return [200, { ok: true }];
  if (ruta === 'POST /__reset') {
    estado = nuevoEstado();
    return [200, { ok: true }];
  }

  // Detenido, E599 gana incluso a un cuerpo de 8.193 bytes (log 11320, 11324).
  const detenido = servicioDetenido(estado);
  if (detenido) return detenido;
  if (Buffer.byteLength(cuerpo) > TOPE_BYTES) return [413, E101];
  // Buffer.toString conserva el BOM, y JSON.parse lo rechaza como el original (log 10966).
  const texto = cuerpo.toString('utf8');
  let json: unknown;
  try {
    json = JSON.parse(texto);
  } catch {
    return [400, E100];
  }
  if (profundidad(texto) > TOPE_NIVELES) return [400, E100];
  const m = (json as { m?: unknown } | null)?.m;
  if (typeof m !== 'string') return [400, E102];

  return procesar(m, estado);
}

createServer((req, res) => {
  // ponytail: el cuerpo entero en memoria; Cloud Run ya corta en 32 MB.
  const partes: Buffer[] = [];
  req.on('data', (c: Buffer) => partes.push(c));
  req.on('end', () => {
    // Desde aquí todo es síncrono: validar y modificar el estado no se intercalan con otro request (§7.3).
    try {
      const [status, cuerpo] = atender(req.method ?? '', req.url ?? '', req.headers.authorization, Buffer.concat(partes));
      responder(res, status, cuerpo);
    } catch (e) {
      // Supuesto: el original nunca mostró un 500; esto solo evita que un error tumbe el único proceso.
      console.error(e);
      res.writeHead(500).end();
    }
  });
}).listen(PORT, () => console.log(`escuchando en :${PORT}`));
