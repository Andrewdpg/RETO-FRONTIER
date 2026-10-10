// Lo que comparten run.ts y paralelo.ts: la guardia contra el original, cómo se manda un paso del log
// y el comparador del README.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";

export type Linea = {
  id: number; seq: string; metodo?: string; ruta?: string; auth?: string | null;
  request: unknown; status: number; response: unknown; par?: string | null; espera?: number | null;
};

const [url, ...resto] = process.argv.slice(2);
export const flags = resto;
const token = process.env.TEAM_ENTRYPOINT_TOKEN;
const original = process.env.BLACK_BOX_URL;
if (!url || !URL.canParse(url)) throw new Error(`uso: node --env-file=.env ${process.argv[1]} <url>`);
if (!token) throw new Error("falta TEAM_ENTRYPOINT_TOKEN en el entorno");
// Llamar al original anula el set: sin BLACK_BOX_URL no hay con qué verificarlo, y no se corre.
if (!original) throw new Error("falta BLACK_BOX_URL en el entorno: no puedo descartar que la URL sea el original");
if (new URL(url).host === new URL(original).host) throw new Error("la URL es la del original: este arnés nunca le habla");
export const base = url.replace(/\/$/, "");

export const leerLog = (): Linea[] =>
  readFileSync(new URL("../experimentos.jsonl", import.meta.url), "utf8")
    .split("\n").filter(Boolean).map((l) => JSON.parse(l)).sort((a, b) => a.id - b.id);

// Mismas cabeceras que mandaron los arneses que generaron el log: exploracion/arnes.ts (t1) y lab/send.py (t2).
// send.py manda cualquier otro valor de auth tal cual como Authorization ("Bearer invalido", "Bearer ", "invalido").
function autorizacion(auth: string | null | undefined): string | undefined {
  if (auth == null || auth === "propio") return `Bearer ${token}`;
  if (auth === "sin token" || auth === "none") return undefined;
  if (auth === "token ajeno") return "Bearer token-que-no-existe-0000";
  if (auth === "esquema Basic") return "Basic dXNlcjpwYXNz";
  return auth;
}

export async function enviar(metodo: string, ruta: string, request: unknown, auth?: string | null) {
  const headers: Record<string, string> = {};
  const a = autorizacion(auth);
  if (a !== undefined) headers.authorization = a;
  const body = request == null ? undefined : typeof request === "string" ? request : JSON.stringify(request);
  if (body !== undefined) headers["content-type"] = "application/json";
  try {
    // 5 s por paso, como el set.
    const res = await fetch(base + ruta, { method: metodo, headers, body, signal: AbortSignal.timeout(5000) });
    return { status: res.status, texto: await res.text() };
  } catch (e) {
    return { status: 0, texto: `(${(e as Error).name}: ${(e as Error).message})` };
  }
}

export const enviarLinea = (l: Linea) => enviar(l.metodo ?? "POST", l.ruta ?? "/msg", l.request, l.auth);
// Una respuesta guardada como string es un cuerpo que no era JSON.
export const esperado = (l: Linea) => (typeof l.response === "string" ? l.response : JSON.stringify(l.response));

// Comparador del README: si los dos cuerpos son JSON, sin orden de claves (isDeepStrictEqual no lo mira);
// si alguno no lo es, texto exacto.
const comoJson = (t: string) => { try { return { ok: true, v: JSON.parse(t) }; } catch { return { ok: false, v: undefined }; } };
export function mismoCuerpo(esp: string, obtenido: string) {
  const a = comoJson(esp), b = comoJson(obtenido);
  return a.ok && b.ok ? isDeepStrictEqual(a.v, b.v) : esp === obtenido;
}

export const corto = (s: string) => (s.length > 200 ? s.slice(0, 200) + "…" : s);
export const pct = (a: number, b: number) => (b ? ((100 * a) / b).toFixed(1) : "0.0");

export function guardar(sufijo: string, resumen: string[], diferencias: string[]) {
  const ahora = new Date().toISOString();
  const informe = [`${ahora} contra ${base}`, ...resumen, "", "id | seq | esperado | obtenido", ...diferencias].join("\n") + "\n";
  mkdirSync(new URL("results/", import.meta.url), { recursive: true });
  const archivo = new URL(`results/${ahora.replace(/[:.]/g, "-")}${sufijo}.txt`, import.meta.url);
  writeFileSync(archivo, informe);
  console.log([`${ahora} contra ${base}`, ...resumen].join("\n"));
  console.log(`${diferencias.length} diferencias en ${archivo.pathname}`);
  process.exitCode = diferencias.length ? 1 : 0;
}
