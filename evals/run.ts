// E-01: reproduce experimentos.jsonl contra el reemplazo y compara como el set oculto.
//   node --env-file=.env evals/run.ts <url> [--sin-espera]
// Cada secuencia (seq) va en orden de id. Los ids 1–497 no registraron el /__reset inicial
// (DESIGN, encabezado): se manda antes de cada una de esas secuencias. Desde el 498 el reset ya es una línea.
// Se saltan las secuencias con pasos en paralelo (par): los pasos siguientes dependen de la ráfaga (E-10, paralelo.ts).
// --sin-espera salta los pasos con espera (log 495–497, 10 min en total).
import { corto, enviar, enviarLinea, esperado, flags, guardar, leerLog, mismoCuerpo, pct, percentil } from "./comun.ts";

const sinEspera = flags.includes("--sin-espera");
const seqs = Map.groupBy(leerLog(), (l) => l.seq);

let pasos = 0, pasosOk = 0, seqsCorridas = 0, seqsOk = 0, saltadasPar = 0, saltadosEspera = 0;
const diferencias: string[] = [];
const latencias: number[] = [];
for (const [seq, ls] of seqs) {
  if (ls.some((l) => l.par != null)) { saltadasPar++; continue; }
  seqsCorridas++;
  let ok = true;
  if (ls[0].id < 498) {
    const r = await enviar("POST", "/__reset", null);
    if (r.status !== 200) { ok = false; diferencias.push(`reset | ${seq} | 200 | ${r.status} ${corto(r.texto)}`); }
  }
  for (const l of ls) {
    if (l.espera) {
      if (sinEspera) { saltadosEspera++; continue; }
      await new Promise((r) => setTimeout(r, l.espera!));
    }
    const r = await enviarLinea(l);
    pasos++;
    latencias.push(r.ms);
    if (r.status === l.status && mismoCuerpo(esperado(l), r.texto)) { pasosOk++; continue; }
    ok = false;
    diferencias.push(`${l.id} | ${seq} | ${l.status} ${corto(esperado(l))} | ${r.status} ${corto(r.texto)}`);
  }
  if (ok) seqsOk++;
}

guardar("", [
  `pasos iguales: ${pasosOk}/${pasos} (${pct(pasosOk, pasos)} %)`,
  `secuencias iguales: ${seqsOk}/${seqsCorridas} (${pct(seqsOk, seqsCorridas)} %)`,
  `saltadas: ${saltadasPar} secuencias con par, ${saltadosEspera} pasos con espera`,
  `latencia por paso (E-08, desde esta máquina): p50 ${percentil(latencias, 50).toFixed(1)} ms, p95 ${percentil(latencias, 95).toFixed(1)} ms, máx ${percentil(latencias, 100).toFixed(1)} ms`,
], diferencias);
