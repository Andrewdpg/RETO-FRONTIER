"""Verifica que SPEC.md cite evidencia que existe y que dice lo que la fila afirma.

    python3 lab/spec_check.py [SPEC.md] [experimentos.jsonl]

Por fila: cada id citado tiene que existir en el log. Si la fila nombra códigos de error (E303, E510…),
al menos uno de sus ids tiene que responder con alguno de ellos. Lo que no se puede chequear así
(efectos, saldos, orden) queda para revisar a mano. Salida 0 si no hay problemas, 1 si los hay.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = re.compile(r"\bE\d{3}\b")


def ids_of(evidence):
    out = []
    # Los rangos se escriben con guion largo o corto: 11068–11128. "ver ERR-01 a ERR-19" no cita ids.
    for lo, hi, single in re.findall(r"\b(\d+)\s*[–-]\s*(\d+)\b|\b(\d+)\b", re.sub(r"[A-Z]+-\d+", "", evidence)):
        lo, hi = (int(lo), int(hi)) if lo else (int(single), int(single))
        out.extend(range(lo, hi + 1))
    return out


def main():
    spec = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "SPEC.md").read_text()
    log = {}
    for line in Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "experimentos.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            log[r["id"]] = r
    problems, rows = [], 0
    for line in spec.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4 or not re.fullmatch(r"[A-Z]+(-[A-Z]+)?-\d+", cells[0]):
            continue
        rows += 1
        rid, text, evidence, conf = cells
        if conf == "supuesto":
            if evidence not in ("—", "-", ""):
                problems.append(f"{rid}: es supuesto pero cita evidencia ({evidence})")
            continue
        cited = ids_of(evidence)
        if not cited:
            if "ver " not in evidence:
                problems.append(f"{rid}: {conf} sin ids")
            continue
        missing = [i for i in cited if i not in log]
        if missing:
            problems.append(f"{rid}: ids que no están en el log: {missing[:10]}")
        codes = set(CODE.findall(text))
        if codes:
            seen = {log[i]["response"].get("error") for i in cited
                    if i in log and isinstance(log[i].get("response"), dict)}
            if not codes & seen:
                problems.append(f"{rid}: nombra {sorted(codes)} pero ningún id citado responde con esos códigos")
        if conf == "confirmado":
            seqs = {log[i]["seq"] for i in cited if i in log}
            if len(seqs) < 2:
                problems.append(f"{rid}: confirmado con evidencia de una sola secuencia ({sorted(seqs)})")
    print(f"{rows} filas revisadas, {len(problems)} para mirar")
    for p in problems:
        print("-", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
