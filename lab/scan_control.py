"""Busca qué controles acepta el servicio para un mensaje, probando 0..99.

    BB_TOKEN=... python3 lab/scan_control.py "CONSULTA;AC-0009" [más cuerpos...] [--stop-at-hit]

El servicio solo dice si un control es válido (E202 si no lo es), así que cada mensaje cuesta hasta 100
requests. Conviene un mensaje que no cambie el estado: CONSULTA a una cuenta que no existe da E401 cuando
el control es válido. Cada request pasa por send.py y queda en experimentos.jsonl.
"""
import sys
from collections import Counter

from send import Client

EXTRA = ["00", "05"]  # formas con cero a la izquierda: ¿E201 por el cero o por el largo?
ABORT_AFTER = 10


def code_of(entry):
    r = entry["response"]
    return r.get("error", "ok") if isinstance(r, dict) else "texto"


def scan(client, body, stop_at_hit):
    client.reset(f"escaneo de control de '{body}': estado limpio")
    seen, hits = Counter(), []
    candidates = [str(c) for c in range(100)] + ([] if stop_at_hit else EXTRA)
    for i, c in enumerate(candidates, 1):
        entry = client.send(f"¿{c} es un control válido para '{body}'? (escaneo)", m=f"{body};{c}")
        code = code_of(entry)
        seen[code] += 1
        if code != "E202":
            hits.append((c, code, entry["status"], entry["id"]))
            print(f"  {c:>2} -> {entry['status']} {code} (id {entry['id']})")
            if stop_at_hit and c.isdigit() and 0 <= int(c) <= 99 and code != "E201":
                break
        # Si el error de otro paso gana a E202 (p. ej. E401), todas las respuestas son iguales y el
        # escaneo no dice nada: se corta antes de gastar los 100 requests.
        if i == ABORT_AFTER and len(seen) == 1 and "E202" not in seen:
            print(f"  las primeras {ABORT_AFTER} respuestas son todas {code}: este mensaje no discrimina")
            return seen, hits, False
    return seen, hits, True


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    client = Client()
    for body in args:
        print(body)
        seen, hits, ok = scan(client, body, "--stop-at-hit" in sys.argv)
        valid = [h[0] for h in hits if h[1] != "E201"]
        print(f"  {sum(seen.values())} requests; respuestas {dict(seen)}; controles aceptados: {valid or 'ninguno'}"
              + ("" if ok else "; ESCANEO NO CONCLUYENTE"))


if __name__ == "__main__":
    main()
