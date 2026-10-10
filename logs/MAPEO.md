# Mapeo de ids de los logs de la mañana

t1 conserva sus ids. t2 suma 10000: `id = id_original + 10000`.

| Token | Secuencia | ids originales | ids en experimentos.jsonl | Primera hipótesis |
|---|---|---|---|---|
| t1 | t1-s01-ejemplos | 1-20 | 1-20 | reproduce ejemplo 1: espera 200 {"pong":true} |
| t1 | t1-s02-integridad | 21-49 | 21-49 | H-mod97: control con 0 a la izquierda (03) vale igual que 3 |
| t1 | t1-s03-entrada | 50-80 | 50-80 | auth: sin token en /msg |
| t1 | t1-s04-ping-sugerencia | 81-91 | 81-91 | PING no valida el control: letras |
| t1 | t1-s05-montos-orden | 92-115 | 92-115 | ALTA crea AC-0001 tras reset |
| t1 | t1-s06-anula | 116-129 | 116-129 | ALTA AC-0001 |
| t1 | t1-s07-bordes | 130-157 | 130-157 | ALTA AC-0001 |
| t1 | t1-s08-ocultos | 158-174 | 158-174 | ALTA para tener AC-0001 |
| t1 | t1-s09-conc-deposito | 175-186 | 175-186 | ALTA AC-0001 |
| t1 | t1-s10-conc-alta | 187-194 | 187-194 | 5 ALTA en paralelo: ¿ids repetidos? |
| t1 | t1-s11-conc-transfer | 195-204 | 195-204 | ALTA AC-0001 |
| t1 | t1-s12-bordes | 205-225 | 205-225 | ALTA AC-0001 |
| t1 | t1-s14-anula-deposito | 226-231 | 226-231 | ALTA AC-0001 |
| t1 | t1-s13-sugerencia | 232-242 | 232-242 | sugerencia: TRANSF — distancia 2 a TRANSFER: si sugiere, el umbral es  |
| t1 | t1-s15-bloqueo-serie | 243-254 | 243-254 | ALTA AC-0001 |
| t1 | t1-s16-bloqueo-cuenta | 255-262 | 255-262 | ALTA AC-0001 |
| t1 | t1-s17-bloqueo-e506 | 263-269 | 263-269 | ALTA AC-0001 |
| t1 | t1-s18-monto-max | 270-279 | 270-279 | ALTA AC-0001 |
| t1 | t1-s19-oculto-sondeo | 280-292 | 280-292 | sondeo de comandos ocultos por sugerencia: DUMP |
| t1 | t1-s20-halt | 293-295 | 293-295 | HALT sin argumentos |
| t1 | t1-s21-auth-vs-cuerpo | 296-298 | 296-298 | orden: sin token y cuerpo no JSON → ¿E001 o E100? |
| t1 | t1-s22-bloqueo-orden | 299-310 | 299-310 | ALTA AC-0001 |
| t1 | t1-s23-bloqueo-alcance | 311-326 | 311-326 | ALTA AC-0001 |
| t1 | t1-s24-rechazo-e303 | 327-333 | 327-333 | ALTA AC-0001 |
| t1 | t1-s24-rechazo-e304 | 334-340 | 334-340 | ALTA AC-0001 |
| t1 | t1-s24-rechazo-e401 | 341-347 | 341-347 | ALTA AC-0001 |
| t1 | t1-s24-rechazo-mixto | 348-355 | 348-355 | ALTA AC-0001 |
| t1 | t1-s24-rechazo-deposito | 356-363 | 356-363 | ALTA AC-0001 |
| t1 | t1-s26-monto-tope | 364-374 | 364-374 | ALTA AC-0001 |
| t1 | t1-s27-saldo-grande | 375-382 | 375-382 | ALTA AC-0001 |
| t1 | t1-s28-limite-diario | 383-392 | 383-392 | ALTA AC-0001 |
| t1 | t1-s29-sugerencia-empates | 393-398 | 393-398 | sugerencia, empate PING/HALT: alfabético → HALT, PING primero en la ta |
| t1 | t1-s30-ocultos-admin | 399-447 | 399-447 | ALTA AC-0001 |
| t1 | t1-s32-desbloqueo-entrante | 448-457 | 448-457 | ALTA AC-0001 |
| t1 | t1-s33-desbloqueo-deposito | 458-467 | 458-467 | ALTA AC-0001 |
| t1 | t1-s34-desbloqueo-anula | 468-478 | 468-478 | ALTA AC-0001 |
| t1 | t1-s35-racha-entrante | 479-487 | 479-487 | ALTA AC-0001 |
| t1 | t1-s25-bloqueo-tiempo | 488-497 | 488-497 | ALTA AC-0001 |
| t2 | t2-s1 | 1-21 | 10001-10021 | reset abre el replay de los 20 ejemplos grabados en la mañana |
| t2 | t2-s2 | 22-54 | 10022-10054 | reset deja el estado inicial; abre la secuencia de rutas y auth |
| t2 | t2-s3 | 55-69 | 10055-10069 | reset antes de la numeración de cuentas y del orden de validación |
| t2 | t2-s4 | 70-172 | 10070-10172 | escaneo de control de 'CONSULTA;AC-0009': estado limpio |
| t2 | t2-s5 | 173-182 | 10173-10182 | escaneo de control de 'CONSULTA;AC-0003': estado limpio |
| t2 | t2-s6 | 183-189 | 10183-10189 | escaneo de control de 'CONSULTA;AC-0004': estado limpio |
| t2 | t2-s7 | 190-193 | 10190-10193 | escaneo de control de 'CONSULTA;AC-0005': estado limpio |
| t2 | t2-s8 | 194-291 | 10194-10291 | escaneo de control de 'CONSULTA;AC-0006': estado limpio |
| t2 | t2-s9 | 292-386 | 10292-10386 | escaneo de control de 'CONSULTA;AC-0007': estado limpio |
| t2 | t2-s10 | 387-478 | 10387-10478 | escaneo de control de 'CONSULTA;AC-0008': estado limpio |
| t2 | t2-s11 | 479-564 | 10479-10564 | escaneo de control de 'CONSULTA;AC-0010': estado limpio |
| t2 | t2-s12 | 565-620 | 10565-10620 | escaneo de control de 'CONSULTA;AC-0020': estado limpio |
| t2 | t2-s13 | 621-630 | 10621-10630 | escaneo de control de 'CONSULTA;AC-0100': estado limpio |
| t2 | t2-s14 | 631-730 | 10631-10730 | escaneo de control de 'CONSULTA;A': estado limpio |
| t2 | t2-s15 | 731-824 | 10731-10824 | escaneo de control de 'CONSULTA;AB': estado limpio |
| t2 | t2-s16 | 825-861 | 10825-10861 | escaneo de control de 'ANULA;AC-0009': estado limpio |
| t2 | t2-s17 | 862-950 | 10862-10950 | escaneo de control de 'consulta;AC-0009': estado limpio |
| t2 | t2-s18 | 951-958 | 10951-10958 | reset antes del holdout de la fórmula del control |
