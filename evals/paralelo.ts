// E-10: reproduce las secuencias con ráfagas en paralelo (log 175–204) contra el reemplazo.
//   node --env-file=.env evals/paralelo.ts <url>
// Los pasos seguidos con el mismo par salen a la vez. Qué request recibe qué respuesta depende del orden
// de llegada, así que cada ráfaga se compara como multiconjunto de (status, cuerpo): mismos ids, mismas
// operaciones y cuántos 200/E507/E510. Los pasos en serie se comparan exactos y fijan el estado final (saldos, ids).
import { corto, enviar, enviarLinea, esperado, guardar, leerLog, mismoCuerpo, pct, type Linea } from "./comun.ts";

const seqs = [...Map.groupBy(leerLog(), (l) => l.seq)].filter(([, ls]) => ls.some((l) => l.par != null));

// Forma canónica de un cuerpo para ordenar el multiconjunto: claves ordenadas si es JSON, texto si no.
const ordenar = (v: unknown): unknown =>
  Array.isArray(v) ? v.map(ordenar) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => (a < b ? -1 : 1)).map(([k, x]) => [k, ordenar(x)])) : v;
const canonica = (status: number, texto: string) => {
  try { return `${status} ${JSON.stringify(ordenar(JSON.parse(texto)))}`; } catch { return `${status} ${texto}`; }
};

let pasos = 0, pasosOk = 0, seqsOk = 0;
const diferencias: string[] = [];
for (const [seq, ls] of seqs) {
  let ok = true;
  // Estas secuencias son del rango 1–497: su /__reset inicial no tiene línea en el log.
  const reset = await enviar("POST", "/__reset", null);
  if (reset.status !== 200) { ok = false; diferencias.push(`reset | ${seq} | 200 | ${reset.status} ${corto(reset.texto)}`); }
  for (let i = 0; i < ls.length; ) {
    let j = i + 1;
    while (ls[i].par != null && j < ls.length && ls[j].par === ls[i].par) j++;
    const rafaga: Linea[] = ls.slice(i, j);
    i = j;
    const rs = await Promise.all(rafaga.map(enviarLinea));
    pasos += rafaga.length;
    if (rafaga.length === 1) {
      const [l] = rafaga, [r] = rs;
      if (r.status === l.status && mismoCuerpo(esperado(l), r.texto)) { pasosOk++; continue; }
      ok = false;
      diferencias.push(`${l.id} | ${seq} | ${l.status} ${corto(esperado(l))} | ${r.status} ${corto(r.texto)}`);
      continue;
    }
    const esp = rafaga.map((l) => canonica(l.status, esperado(l))).sort();
    const obt = rs.map((r) => canonica(r.status, r.texto)).sort();
    if (esp.every((e, k) => e === obt[k])) { pasosOk += rafaga.length; continue; }
    ok = false;
    diferencias.push(`${rafaga[0].id}–${rafaga.at(-1)!.id} | ${seq} | ${esp.join(" ; ")} | ${obt.join(" ; ")}`);
  }
  if (ok) seqsOk++;
}

guardar("-paralelo", [
  `pasos iguales: ${pasosOk}/${pasos} (${pct(pasosOk, pasos)} %)`,
  `secuencias iguales: ${seqsOk}/${seqs.length} (${pct(seqsOk, seqs.length)} %)`,
], diferencias);
