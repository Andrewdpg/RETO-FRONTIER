// Control mod 97 estilo IBAN (DESIGN §3.2): 98 − (N·100 mod 97).
// N: el cuerpo sin lo que no sea [A-Za-z0-9], en mayúsculas, A→1…Z→26 sin relleno, dígitos tal cual.
// Se filtra antes de toUpperCase porque 'ß'.toUpperCase() es 'SS' y el original descarta la ß (log 222, 278).
// N puede tener miles de dígitos (log 220): el módulo se calcula dígito a dígito, nunca con Number(N).
export function controlEsperado(cuerpo: string): string {
  const n = cuerpo.replace(/[^A-Za-z0-9]/g, '').toUpperCase()
    .replace(/[A-Z]/g, (l) => String(l.charCodeAt(0) - 64));
  let resto = 0;
  for (const d of n + '00') resto = (resto * 10 + Number(d)) % 97; // + '00' es el ·100
  return String(98 - resto);
}
