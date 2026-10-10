// Estaciones 5–14 de DESIGN §3.11 (D2): una tabla de comandos y una lista ordenada de validaciones.
// Si el servicio cambia, se edita una fila de COMANDOS o se reordena ESTACIONES; el pipeline no se toca.
import { controlEsperado } from './control.ts';

// intentosBloqueada: cuántos E510 seguidos respondió la cuenta (log 12772–12774). No lo reinician recibir una transferencia
// ni ANULA (log 968–970, 991–993); el depósito que desbloquea sí (log 12779).
type Cuenta = { id: string; nombre: string; saldo: number; rechazosSeguidos: number; intentosBloqueada: number };
type Operacion = { id: string; tipo: 'DEPOSITO' | 'TRANSFER'; origen?: Cuenta; destino: Cuenta; monto: number; anulada: boolean };
// detenido: lo prende HALT;1 y solo /__reset lo apaga, porque reset crea un estado nuevo (log 11138–11140, 11210).
export type Estado = { cuentas: Map<string, Cuenta>; operaciones: Map<string, Operacion>; detenido: boolean };
export const nuevoEstado = (): Estado => ({ cuentas: new Map(), operaciones: new Map(), detenido: false });

export type Respuesta = [status: number, cuerpo: Record<string, unknown>];

const ERRORES = {
  E103: [400, 'falta control'],
  E104: [400, 'segmento vacío'],
  E201: [400, 'control mal formado'],
  E202: [400, 'control inválido'],
  E301: [400, 'comando desconocido '], // con espacio final (log 12, 89)
  E302: [400, 'aridad inválida'],
  E303: [400, 'monto inválido'],
  E304: [400, 'origen y destino iguales'],
  E401: [404, 'cuenta inexistente'],
  E402: [404, 'operación inexistente'],
  E510: [423, 'cuenta bloqueada'], // 423 desde la v2 (log 968)
  E506: [422, 'límite excedido'],
  E507: [422, 'saldo insuficiente'],
  E520: [409, 'operación destructiva: detiene el servicio; reenvía con confirmación'],
  E599: [503, 'service halted'],
} as const;
type Codigo = keyof typeof ERRORES;
const error = (codigo: Codigo, extra = {}): Respuesta => [ERRORES[codigo][0], { error: codigo, mensaje: ERRORES[codigo][1], ...extra }];

// Solo estos rechazos suman a la racha del origen; E303, E304 y E401 no (log 330–347).
const RECHAZOS_QUE_BLOQUEAN: Codigo[] = ['E506', 'E507'];
const RECHAZOS_PARA_BLOQUEO = 3; // log 249, 269

// Tipo de cada argumento: decide qué estaciones lo miran.
type Arg = 'texto' | 'cuenta' | 'origen' | 'destino' | 'monto' | 'operacion';

type Pedido = {
  segmentos: string[]; nombre: string; args: string[]; fila?: Comando;
  cuentas: Partial<Record<'cuenta' | 'origen' | 'destino', Cuenta>>; operacion?: Operacion; monto: number;
};

type Comando = {
  args: Arg[];
  validaControl: boolean;
  // Monto máximo por operación (E506); `salvo` dice cuándo no se aplica.
  limite?: { monto: number; salvo?: (p: Pedido) => boolean };
  confirmacion?: string; // único argumento que ejecuta un comando destructivo
  efecto: (p: Pedido, e: Estado) => Respuesta;
};

// Desde la v2 CONSULTA muestra el saldo en unidades con dos decimales, armado como texto para no pasar por floats:
// 991 → "9.91", -50 → "-0.50" (log 518, 640, 723, 745, 891).
function comoDecimal(saldo: number): string {
  const digitos = String(Math.abs(saldo)).padStart(3, '0');
  return `${saldo < 0 ? '-' : ''}${digitos.slice(0, -2)}.${digitos.slice(-2)}`;
}

const nuevoId = (prefijo: string, n: number) => `${prefijo}-${String(n).padStart(4, '0')}`;

function registrar(e: Estado, op: Omit<Operacion, 'id' | 'anulada'>): Respuesta {
  // Los rechazos no crean operaciones (log 9, 10) y nada se borra: el próximo número es el tamaño + 1.
  const id = nuevoId('OP', e.operaciones.size + 1);
  e.operaciones.set(id, { ...op, id, anulada: false });
  return [200, { status: 'recieved', operacionId: id }]; // "recieved" tal cual (log 6)
}

// Ordenados alfabéticamente: en un empate de la sugerencia gana el primero (log 238, 239, 393–398).
const COMANDOS: Record<string, Comando> = {
  ALTA: {
    args: ['texto'], validaControl: true,
    efecto: (p, e) => {
      const id = nuevoId('AC', e.cuentas.size + 1);
      e.cuentas.set(id, { id, nombre: p.args[0], saldo: 0, rechazosSeguidos: 0, intentosBloqueada: 0 });
      return [201, { cuentaId: id }]; // camelCase aquí, snake_case en CONSULTA (log 3, 5)
    },
  },
  ANULA: {
    args: ['operacion'], validaControl: true,
    efecto: (p) => {
      const op = p.operacion!;
      if (op.anulada) return [200, { ok: false, motivo: 'ya anulada' }]; // log 14
      // Sin revisar saldo: puede dejarlo negativo (log 122, 231). No toca rechazosSeguidos (log 456–457).
      op.destino.saldo -= op.monto;
      if (op.origen) op.origen.saldo += op.monto;
      op.anulada = true;
      return [200, { ok: true, anulada: op.id }];
    },
  },
  CONSULTA: {
    args: ['cuenta'], validaControl: true,
    efecto: (p) => [200, { cuenta_id: p.cuentas.cuenta!.id, saldo: comoDecimal(p.cuentas.cuenta!.saldo) }],
  },
  DEPOSITO: {
    args: ['cuenta', 'monto'], validaControl: true,
    efecto: (p, e) => {
      const cuenta = p.cuentas.cuenta!;
      cuenta.saldo += p.monto;
      cuenta.rechazosSeguidos = 0; // el depósito desbloquea (log 250, 323–324, 466–467)
      cuenta.intentosBloqueada = 0; // y el próximo E510 vuelve a decir 1 (log 12779, visto una vez)
      return registrar(e, { tipo: 'DEPOSITO', destino: cuenta, monto: p.monto });
    },
  },
  HALT: {
    // Solo '1' confirma (log 11134, 11199); cualquier otro argumento pide confirmación (log 292, 11068–11128).
    // Sin argumentos o con dos, E302 (log 293, 11159). El mismo request ya responde E599.
    args: ['texto'], validaControl: true, confirmacion: '1',
    efecto: (p, e) => {
      if (p.args[0] !== p.fila!.confirmacion) return error('E520');
      e.detenido = true;
      return error('E599');
    },
  },
  PING: {
    args: [], validaControl: false, // acepta cualquier control (log 25–29, 81, 82)
    efecto: () => [200, { pong: true }],
  },
  TRANSFER: {
    args: ['origen', 'destino', 'monto'], validaControl: true,
    limite: {
      monto: 50_000, // v2: 50.000 pasa y 50.001 da E506 (log 12758, 12856, 12854). En la v1 era 100.000 (log 155–157)
      // Mismo titular: nombre del ALTA idéntico, distinguiendo mayúsculas (log 11782, 11794; Ana→Beto 11788, Ana→ana 11800).
      // En la v2 sigue sin límite (log 12604, 12685).
      // El saldo se sigue revisando (log 11575, 11805). Supuesto sin medir: como no hay E506, no suma al bloqueo.
      salvo: (p) => p.cuentas.origen!.nombre === p.cuentas.destino!.nombre,
    },
    efecto: (p, e) => {
      const { origen, destino } = p.cuentas as Required<Pedido['cuentas']>;
      origen.saldo -= p.monto;
      destino.saldo += p.monto;
      origen.rechazosSeguidos = 0; // log 258–262
      return registrar(e, { tipo: 'TRANSFER', origen, destino, monto: p.monto });
    },
  },
};

// Por code points, no por unidades UTF-16: "PI😀😀" está a distancia 2 de PING (log 1289, 1314).
function levenshtein(x: string, y: string): number {
  const a = Array.from(x), b = Array.from(y);
  let previa = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const fila = [i];
    for (let j = 1; j <= b.length; j++)
      fila[j] = Math.min(previa[j] + 1, fila[j - 1] + 1, previa[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    previa = fila;
  }
  return previa[b.length];
}

// Distancia ≤ 2 contando espacios, sobre el nombre en mayúsculas; empate → orden alfabético (DESIGN §3.10).
function sugerencia(nombre: string): string | undefined {
  let mejor: string | undefined, mejorDist = 3;
  for (const c of Object.keys(COMANDOS).sort()) {
    const d = levenshtein(nombre, c);
    if (d < mejorDist) [mejor, mejorDist] = [c, d];
  }
  return mejor;
}

const MONTO = /^[1-9][0-9]{0,9}$/; // ASCII, sin signos, ceros a la izquierda ni espacios (log 94–99, 144, 206–214, 365–374)

const indice = (fila: Comando, tipo: Arg) => fila.args.indexOf(tipo);

// Estaciones 5–13 en el orden medido (§3.11). Cada una devuelve un error o nada; la 14 es el efecto de la fila.
const ESTACIONES: ((p: Pedido, e: Estado) => Respuesta | undefined)[] = [
  // 5. Segmentos
  (p) => (p.segmentos.length < 2 ? error('E103') : undefined),
  (p) => (p.segmentos.includes('') ? error('E104') : undefined),
  // 6. Control (PING lo saltea; se compara como texto: '03' ≠ '3', log 21)
  (p) => {
    if (p.fila && !p.fila.validaControl) return;
    const control = p.segmentos.at(-1)!;
    if (!/^[0-9]{1,2}$/.test(control)) return error('E201');
    if (control !== controlEsperado(p.segmentos.slice(0, -1).join(';'))) return error('E202');
  },
  // 7. Comando y aridad
  (p) => {
    if (!p.fila) {
      const s = sugerencia(p.nombre);
      return error('E301', s ? { sugerencia: s } : {});
    }
    if (p.args.length !== p.fila.args.length) return error('E302');
  },
  // 8. Monto. E301/E302 van antes que E303 (log 11328–11335).
  (p) => {
    const i = indice(p.fila!, 'monto');
    if (i < 0) return;
    if (!MONTO.test(p.args[i])) return error('E303');
    p.monto = Number(p.args[i]); // ya validado: hasta 10 dígitos, exacto en un double
  },
  // 9. Origen y destino distintos
  (p) => {
    const [o, d] = [indice(p.fila!, 'origen'), indice(p.fila!, 'destino')];
    if (o >= 0 && d >= 0 && p.args[o] === p.args[d]) return error('E304');
  },
  // 10. Existencia: ids comparados como texto exacto (log 100, 101, 115, 136, 126–128, 223–225)
  (p, e) => {
    for (const tipo of ['cuenta', 'origen', 'destino'] as const) {
      const i = indice(p.fila!, tipo);
      if (i < 0) continue;
      const cuenta = e.cuentas.get(p.args[i]);
      if (!cuenta) return error('E401');
      p.cuentas[tipo] = cuenta;
    }
    const i = indice(p.fila!, 'operacion');
    if (i >= 0 && !(p.operacion = e.operaciones.get(p.args[i]))) return error('E402');
  },
  // 11. Bloqueo del origen; cada E510 suma un intento a la cuenta (log 968, 970)
  (p) => {
    const o = p.cuentas.origen;
    if (o && o.rechazosSeguidos >= RECHAZOS_PARA_BLOQUEO) return error('E510', { intentos: ++o.intentosBloqueada });
  },
  // 12. Límite por operación
  (p) => {
    const l = p.fila!.limite;
    if (l && p.monto > l.monto && !l.salvo?.(p)) return error('E506');
  },
  // 13. Saldo del origen
  (p) => (p.cuentas.origen && p.cuentas.origen.saldo < p.monto ? error('E507') : undefined),
];

// Estación 2c: detenido, todo POST /msg con token da E599 antes que el JSON y el resto (log 11135, 11137, 11202–11207).
export const servicioDetenido = (e: Estado): Respuesta | undefined => (e.detenido ? error('E599') : undefined);

// Recibe un m ya validado como string (estaciones 1–4 en server.ts). Síncrono de punta a punta (§7.3).
export function procesar(m: string, e: Estado): Respuesta {
  const segmentos = m.split(';');
  // El nombre va en mayúsculas sin recortar espacios (log 11, 34, 35, 86, 91), y solo de a–z: toUpperCase
  // convertiría ſ en S e ı en I, y el original las deja y responde E301 (log 1239, 1241, 1261, 1263).
  // La sugerencia se calcula sobre este mismo texto.
  const nombre = segmentos[0].replace(/[a-z]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 32));
  const p: Pedido = {
    segmentos, nombre, args: segmentos.slice(1, -1), fila: Object.hasOwn(COMANDOS, nombre) ? COMANDOS[nombre] : undefined,
    cuentas: {}, monto: 0,
  };
  for (const estacion of ESTACIONES) {
    const r = estacion(p, e);
    if (!r) continue;
    const codigo = r[1].error as Codigo;
    if (p.cuentas.origen && RECHAZOS_QUE_BLOQUEAN.includes(codigo)) p.cuentas.origen.rechazosSeguidos++;
    return r;
  }
  return p.fila!.efecto(p, e);
}
