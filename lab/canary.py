"""Compara la última corrida de lab/probes/002-replay.jsonl con las respuestas grabadas de la mañana.

    python3 lab/canary.py [--log experimentos.jsonl] [--ejemplos material/pruebas/ejemplos.jsonl]

Salida 0: sin cambios. 1: el servicio responde distinto. 2: no hay una corrida completa que comparar.
Solo ve los comandos de esos 20 ejemplos; un comando o un límite nuevo se le escapa.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def same(a, b):
    # En Python 1 == 1.0 == True: el README exige strings y números idénticos, así que se compara el tipo.
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def load(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def messages(rows):
    """Los POST /msg de una secuencia, sin contar el reset."""
    return [r for r in rows if "ruta" not in r and "metodo" not in r]


def latest_replay(log, expected):
    # La corrida se reconoce por sus requests, no por el texto de la hipótesis, que es frágil.
    by_seq = {}
    for r in log:
        by_seq.setdefault(r["seq"], []).append(r)
    found = None
    for rows in by_seq.values():
        msgs = messages(rows)
        if len(msgs) >= 2 and [m["request"] for m in msgs] == [e["request"] for e in expected[:len(msgs)]]:
            found = rows
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default=ROOT / "experimentos.jsonl")
    ap.add_argument("--ejemplos", default=ROOT / "material/pruebas/ejemplos.jsonl")
    args = ap.parse_args()
    expected, log = load(args.ejemplos), load(args.log)

    rows = latest_replay(log, expected)
    if rows is None:
        print("incompleta: en el log no hay una corrida del replay (002)")
        return 2
    msgs = messages(rows)
    bad = [r["id"] for r in rows if "error" in r]
    if len(msgs) < len(expected) or bad:
        print(f"incompleta: {len(msgs)} de {len(expected)} requests, líneas con error: {bad}")
        return 2

    diffs = [(e, m) for e, m in zip(expected, msgs)
             if m["status"] != e["status"] or not same(m["response"], e["response"])]
    when = msgs[0].get("ts", "sin hora")
    if not diffs:
        print(f"sin cambios: {len(expected)} de {len(expected)} iguales ({rows[0]['seq']}, {when})")
        return 0
    print(f"CAMBIÓ: {len(diffs)} de {len(expected)} difieren ({rows[0]['seq']}, {when})")
    for i, (e, m) in enumerate(diffs):
        # Si cambia un ALTA, los ids que vienen después se corren: solo la primera diferencia es causa.
        print(("causa  " if i == 0 else "efecto ") + f"ejemplo {e['n']} {json.dumps(e['request'], ensure_ascii=False)}")
        print(f"  antes {e['status']} {json.dumps(e['response'], ensure_ascii=False)}")
        print(f"  ahora {m['status']} {json.dumps(m['response'], ensure_ascii=False)}  (log id {m['id']})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
