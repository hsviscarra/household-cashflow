"""Synthetic bank transfer notices, shaped like Produbanco's and Pichincha's emails (names,
accounts and references invented)."""

FOOTER = (
    "\n\nAtentamente Produbanco\n\n| [](https://www.produbanco.com.ec/) |\n| [](+5931700123123) |"
    "\n\n| Si tienes alguna consulta: no es necesario responder a este correo electrónico. |"
)

PRODU_SENT = (
    "Transferencia enviada por $408.74 desde Produbanco",
    " Produbanco enlínea notificacion nuevo formato\n| |\n\nEstimado/a\n\nTITULAR DE PRUEBA\n\n"
    "Fecha y Hora: 8/Septiembre/2026 8:49\n\n"
    "Transacción: *Transferencia Enviada Exitosamente desde Produbanco*\n\n*Detalle*\n\n"
    "*Contacto:* NAPOLES TRANSPORT SA\n*Banco Destino:* BANCO PICHINCHA\n"
    "*Cuenta Destino:* XXXXX55511\n*Monto:* $408.74\n*Descripción:* Flete obra\n"
    "*Canal:* App Móvil\n*Referencia:* 750716020900\n\n"
    "Esta transacción tiene un costo de $0.41 por motivo de Transferencia Interbancaria." + FOOTER,
)

PRODU_SENT_OWN = (
    "Transferencia enviada por $50.00 desde Produbanco",
    "Fecha y Hora: 9/Septiembre/2026 8:49\n\n*Contacto:* TITULAR DE PRUEBA\n"
    "*Banco Destino:* BANCO PICHINCHA\n*Cuenta Destino:* XXXXX70800\n*Monto:* $50.00\n"
    "*Descripción:* Transferencia Local\n*Referencia:* 750716020901" + FOOTER,
)

PRODU_RECEIVED = (
    "Transferencia Recibida en Produbanco",
    "| |\n\nEstimado/a\n\nTITULAR DE PRUEBA\n\nFecha y Hora: 15/octubre/2026 13:34\n\n"
    "Transacción: *Transferencia Recibida Produbanco*\n\n*Detalle*\n\n"
    "*Enviada por:* INTELLIGENT ENTERPRISE MANAG\n*Banco Origen:* BANCO DE GUAYAQUIL\n"
    "*Beneficiario:* TITULAR DE PRUEBA\n*Cuenta Beneficiario:* XXXXXX93721\n"
    "*Monto:* $1,065.00\n*Descripción:* SOLICITUD DEL ORDENANTE\n"
    "*Referencia:* 261015036021550815" + FOOTER,
)

PRODU_CREDITED = (
    "Transferencia acreditada Produbanco",
    "| |\n\nEstimado/a\n\nTITULAR DE PRUEBA\n\n"
    "Te confirmamos que PERSONA DE PRUEBA ha realizado una transferencia a tu cuenta en "
    "Produbanco.\n\n*Fecha y Hora:* 09/08/2026 12:07:36\n\n"
    "Transacción: *Transferencia recibida Produbanco*\n\n*Detalle*\n\n"
    "*Banco Destino:* Produbanco\n*Cuenta Destino:* XXXXXX93721\n*Monto:* $150.00\n"
    "*Descripción:* Pagos\n*Referencia:* 119383287" + FOOTER,
)

# A copy for someone else's account (a relative's): not the household's money.
PRODU_TO_SOMEONE_ELSE = (
    "Transferencia recibida desde Produbanco",
    "Estimado/a\n\n*OTRO TITULAR*\nTe confirmamos que *PERSONA DE PRUEBA* ha realizado una "
    "transferencia a tu cuenta en *BANCO PICHINCHA*, enviada desde Produbanco.\n\n"
    "Fecha y Hora: 8/Septiembre/2026 12:08\n\n*Banco Destino:* BANCO PICHINCHA\n"
    "*Cuenta Destino:* XXXXX31704\n*Monto:* $181.00\n*Descripción:* Viaje\n"
    "*Referencia:* 834503020900" + FOOTER,
)

PICHINCHA_SENT = (
    "NOTIFICACION BANCO PICHINCHA",
    "| |\n| Titular De Prueba Tu cédula termina en: ******* 0000 | |\n\n"
    "| | ¡Transferencia exitosa! |\n\n| Hola, Titular De Prueba, |\n"
    "| Realizaste una transferencia. |\n\n| |\n| Detalle de la transacción Monto: Concepto |\n\n"
    "| |\n| 25.00 Para mamá |\n\n| |\n| Cuenta de origen Número de cuenta: |\n\n| |\n"
    "| ******0800 |\n\n| |\n| Cuenta destino Nombre: Número de cuenta: |\n\n| |\n"
    "| PERSONA DESTINO DE PRUEBA ******9635 |\n\n| |\n| Documento: Fecha: |\n\n| |\n"
    "| 32942365 14/10/2026 |\n\n| Si no has solicitado este servicio, repórtalo |",
)

PICHINCHA_COPY_NOT_OURS = (
    "NOTIFICACION BANCO PICHINCHA",
    "| PERSONA DESTINO DE PRUEBA Tu cif termina en: ******* 0000 | |\n| TRANSFERENCIA |\n"
    "| La transferencia se realizó correctamente |\n| Detalle | |\n"
    "| Cuenta acreditada: | ******9635 |\n| Fecha: | 14/10/2026 |\n"
    "| Nombre del ordenante: | Titular De Prueba |\n| Monto: | USD 25.00 |\n"
    "| Concepto: | |\n| Número de documento: | 32942365 |",
)

PICHINCHA_RECEIVED = (
    "NOTIFICACION BANCO PICHINCHA",
    "| Titular De Prueba Tu cif termina en: ******* 0000 | |\n| TRANSFERENCIA |\n"
    "| La transferencia se realizó correctamente |\n| Detalle | |\n"
    "| Cuenta acreditada: | ******0800 |\n| Fecha: | 20/10/2026 |\n"
    "| Nombre del ordenante: | Ruben Prueba |\n| Monto: | USD 1,237.09 |\n"
    "| Concepto: | Saldo octubre |\n| Número de documento: | 33000001 |",
)

NOT_A_TRANSFER = ("NOTIFICACION BANCO PICHINCHA", "Tu clave fue cambiada.")
