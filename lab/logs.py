"""Junta los logs del equipo en el experimentos.jsonl que se entrega.

    python3 lab/logs.py importar --t1 <log de t1> --t2 <log de t2>   (una sola vez)
    python3 lab/logs.py armar                                        (cada vez que haga falta)

Durante el día cada token escribe en su archivo (logs/t1.jsonl, logs/t2.jsonl) y en su rango de ids
(t1 desde 1, t2 desde 10001), así nunca chocan ni hay conflictos de git. `armar` concatena los dos,
ordena por id y verifica que no haya ids repetidos.

`importar` trae los logs de la mañana: el de t1 conserva sus ids, porque el DESIGN.md los cita; el de
t2 se corre 10000 y guarda su id viejo en `id_original`. A los dos les agrega `token` y el prefijo en
`seq`. El mapeo queda en logs/MAPEO.md.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
OFFSET = {"t1": 0, "t2": 10000}


def load(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def write(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def tag(rows, token):
    out = []
    for r in rows:
        r = dict(r)
        if OFFSET[token]:
            r["id_original"] = r["id"]
            r["id"] = r["id"] + OFFSET[token]
        r["token"] = token
        r["seq"] = f"{token}-{r['seq']}"
        out.append(r)
    return out


def importar(args):
    LOGS.mkdir(exist_ok=True)
    targets = {t: LOGS / f"{t}.jsonl" for t in OFFSET}
    if any(p.exists() and p.stat().st_size for p in targets.values()) and not args.forzar:
        sys.exit("logs/ ya tiene contenido: importar se corre una sola vez (--forzar para rehacerlo)")
    rows = {"t1": tag(load(args.t1), "t1"), "t2": tag(load(args.t2), "t2")}
    if max(r["id"] for r in rows["t1"]) >= OFFSET["t2"]:
        sys.exit("el log de t1 llega al rango de t2: hay que mover el offset")
    for t, p in targets.items():
        write(p, rows[t])

    lines = ["# Mapeo de ids de los logs de la mañana", "",
             "t1 conserva sus ids. t2 suma 10000: `id = id_original + 10000`.", "",
             "| Token | Secuencia | ids originales | ids en experimentos.jsonl | Primera hipótesis |",
             "|---|---|---|---|---|"]
    for t in OFFSET:
        seqs = {}
        for r in rows[t]:
            seqs.setdefault(r["seq"], []).append(r)
        for seq, rs in seqs.items():
            orig = [r.get("id_original", r["id"]) for r in rs]
            new = [r["id"] for r in rs]
            h = rs[0]["hipotesis"].replace("|", "/")[:70]
            lines.append(f"| {t} | {seq} | {min(orig)}-{max(orig)} | {min(new)}-{max(new)} | {h} |")
    (LOGS / "MAPEO.md").write_text("\n".join(lines) + "\n")
    print(f"t1: {len(rows['t1'])} líneas, t2: {len(rows['t2'])} líneas; mapeo en logs/MAPEO.md")


def armar(args):
    rows = [r for p in sorted(LOGS.glob("t*.jsonl")) for r in load(p)]
    rows.sort(key=lambda r: r["id"])
    ids = [r["id"] for r in rows]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        sys.exit(f"ids repetidos: {dup[:10]}")
    write(ROOT / "experimentos.jsonl", rows)
    print(f"experimentos.jsonl: {len(rows)} líneas, ids {ids[0]}-{ids[-1]}")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("importar")
    i.add_argument("--t1", required=True)
    i.add_argument("--t2", required=True)
    i.add_argument("--forzar", action="store_true")
    sp.add_parser("armar")
    args = ap.parse_args()
    {"importar": importar, "armar": armar}[args.cmd](args)


if __name__ == "__main__":
    main()
