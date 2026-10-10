// Arnés de exploración contra el original.
//   node exploracion/arnes.ts run <corpus.jsonl>   manda cada secuencia tras un /__reset y la registra
//   node exploracion/arnes.ts replay [seq...]       repite secuencias ya registradas y marca qué cambió
// Corpus: una línea por request {seq, hipotesis, request, metodo?, ruta?, auth?, par?, espera?}.
//   request: objeto JSON o string (se manda tal cual, para cuerpos no JSON).
//   metodo y ruta: POST y /msg por defecto.
//   auth: "propio" (defecto) | "sin token" | "token ajeno" (uno inventado) | "esquema Basic". El token nunca se escribe.
//   par: los pasos seguidos con el mismo par salen a la vez (ráfaga ≤ 10, con 1,1 s de silencio antes y después).
//   espera: milisegundos de pausa antes de mandar el paso (para medir efectos del tiempo).
// Campos extra del log respecto del README: metodo, ruta, auth, par, espera y texto (el cuerpo no era JSON).
// Cada request al original queda en experimentos.jsonl, también los del replay.
import { appendFileSync, existsSync, readFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";

process.loadEnvFile(new URL("../.env", import.meta.url).pathname);
const URL_BASE = process.env.BLACK_BOX_URL!.replace(/\/$/, "");
const TOKEN = process.env.BLACK_BOX_TOKEN!;
const LOG = new URL("../experimentos.jsonl", import.meta.url).pathname;
const MAX_REQ = Number(process.env.MAX_REQ ?? 300); // tope por corrida; el día tiene 8.000 por token
const INTERVALO_MS = 110; // 10 req/s por token, con margen

type Paso = { seq: string; hipotesis: string; request: unknown; metodo?: string; ruta?: string; auth?: string; par?: string; espera?: number };
type Linea = Paso & { id: number; x_req: number | null; status: number; response: unknown; texto?: true; conclusion?: string };

const leerJsonl = <T>(f: string): T[] =>
  existsSync(f) ? readFileSync(f, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];

let enviados = 0;
let ultimo = 0;
const dormir = (ms: number) => new Promise((r) => setTimeout(r, ms));
async function enviar(method: string, path: string, body: unknown, auth = "propio", espaciar = true) {
  if (!["propio", "sin token", "token ajeno", "esquema Basic"].includes(auth)) throw new Error(`auth desconocido: ${auth}`);
  if (++enviados > MAX_REQ) throw new Error(`tope de ${MAX_REQ} requests alcanzado (MAX_REQ)`);
  const headers: Record<string, string> = {};
  if (auth === "propio") headers.authorization = `Bearer ${TOKEN}`;
  if (auth === "token ajeno") headers.authorization = "Bearer token-que-no-existe-0000";
  if (auth === "esquema Basic") headers.authorization = "Basic dXNlcjpwYXNz";
  if (body !== undefined) headers["content-type"] = "application/json";
  for (;;) {
    const espera = ultimo + INTERVALO_MS - Date.now();
    if (espaciar && espera > 0) await dormir(espera);
    ultimo = Date.now();
    const res = await fetch(URL_BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : typeof body === "string" ? body : JSON.stringify(body),
    });
    const txt = await res.text();
    // La respuesta de rate-limit es de la infraestructura: no es comportamiento del servicio.
    if (res.headers.get("x-frontier-infra") === "rate-limit") {
      console.error(`rate-limit en ${method} ${path}; espero 2 s`);
      await dormir(2000);
      continue;
    }
    let response: unknown = txt;
    let texto = true;
    try { response = JSON.parse(txt); texto = false; } catch {}
    const xr = res.headers.get("x-req");
    return { status: res.status, response, texto, x_req: xr === null ? null : Number(xr) };
  }
}

const log = leerJsonl<Linea>(LOG);
let siguienteId = Math.max(0, ...log.map((l) => l.id)) + 1;
const seqsUsadas = new Set(log.map((l) => l.seq));
const nombreLibre = (base: string) => {
  let n = base, i = 2;
  while (seqsUsadas.has(n)) n = `${base}~${i++}`;
  seqsUsadas.add(n);
  return n;
};

// Comparación del README: JSON sin orden de claves (isDeepStrictEqual lo ignora); si no es JSON, texto exacto.
const igual = (a: Linea, b: { status: number; response: unknown; texto: boolean }) =>
  a.status === b.status && !!a.texto === b.texto && isDeepStrictEqual(a.response, b.response);

async function correr(pasos: Paso[], previas?: Linea[]) {
  const seq = nombreLibre(pasos[0].seq);
  const r = await enviar("POST", "/__reset", undefined);
  // Sin cortar: si HALT detuvo el servicio, las líneas de la secuencia muestran qué pasa después.
  if (r.status !== 200) console.error(`AVISO: /__reset inicial de ${seq} respondió ${r.status} ${JSON.stringify(r.response)}`);
  let cambios = 0;
  for (let i = 0; i < pasos.length; ) {
    // Una ráfaga son los pasos seguidos con el mismo par; un paso sin par es una ráfaga de uno.
    let j = i + 1;
    while (pasos[i].par && j < pasos.length && pasos[j].par === pasos[i].par) j++;
    const grupo = pasos.slice(i, j);
    if (grupo.length > 1) await dormir(1100);
    if (grupo[0].espera) await dormir(grupo[0].espera);
    const outs = await Promise.all(grupo.map((p) => enviar(p.metodo ?? "POST", p.ruta ?? "/msg", p.request, p.auth ?? "propio", grupo.length === 1)));
    if (grupo.length > 1) await dormir(1100);
    for (const [k, out] of outs.entries()) {
      const p = grupo[k];
      const linea: Linea = {
        id: siguienteId++, seq, x_req: out.x_req, hipotesis: p.hipotesis,
        metodo: p.metodo ?? "POST", ruta: p.ruta ?? "/msg", auth: p.auth ?? "propio",
        request: p.request ?? null, status: out.status, response: out.response,
      };
      if (out.texto) linea.texto = true;
      if (p.par) linea.par = p.par;
      if (p.espera) linea.espera = p.espera;
      const antes = previas?.[i + k];
      if (antes) {
        const ok = igual(antes, out);
        if (!ok) cambios++;
        linea.conclusion = ok ? `replay de id ${antes.id}: sin cambios` : `replay de id ${antes.id}: CAMBIÓ (antes ${antes.status} ${JSON.stringify(antes.response)})`;
        if (!ok) console.log(`CAMBIÓ id ${antes.id} ${JSON.stringify(p.request)}\n  antes ${antes.status} ${JSON.stringify(antes.response)}\n  ahora ${out.status} ${JSON.stringify(out.response)}`);
      } else {
        console.log(`${linea.id}\t${seq}\tx${out.x_req}\t${JSON.stringify(p.request).slice(0, 90)}\t${out.status}\t${JSON.stringify(out.response)}`);
      }
      appendFileSync(LOG, JSON.stringify(linea) + "\n");
    }
    i = j;
  }
  return cambios;
}

const agrupar = <T extends { seq: string }>(xs: T[]) => {
  const g = new Map<string, T[]>();
  for (const x of xs) g.set(x.seq, [...(g.get(x.seq) ?? []), x]);
  return g;
};

const [modo, ...args] = process.argv.slice(2);
if (modo === "run") {
  for (const pasos of agrupar(leerJsonl<Paso>(args[0])).values()) await correr(pasos);
} else if (modo === "replay") {
  // Solo secuencias originales (no replays previos), filtrables por nombre.
  const grupos = [...agrupar(log.filter((l) => !l.conclusion?.startsWith("replay"))).entries()]
    .filter(([s]) => args.length === 0 || args.includes(s));
  let total = 0;
  for (const [seq, lineas] of grupos) {
    const pasos = lineas.map(({ hipotesis, request, metodo, ruta, auth, par }) => ({ seq: `${seq}@replay`, hipotesis: `replay: ${hipotesis}`, request, metodo, ruta, auth, par }));
    total += await correr(pasos, lineas);
  }
  console.log(`${grupos.length} secuencias repetidas, ${total} respuestas cambiaron`);
} else {
  console.error("uso: node exploracion/arnes.ts run <corpus.jsonl> | replay [seq...]");
  process.exit(1);
}
