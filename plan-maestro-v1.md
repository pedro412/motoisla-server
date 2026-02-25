# Plan Maestro v1 — Plataforma Operativa Moto Isla (POS + Ledger + Catálogo Web)

Fecha: 2026-02-25  
Versión: v1 (funcional, sin diseño técnico)

---

## 1) Objetivo del sistema (v1)

Centralizar en una sola plataforma la gestión de **productos, inventario y ventas** de Moto Isla para operar de forma consistente en **tienda física** y **canal en línea (catálogo, sin checkout en v1)**, asegurando que los datos transaccionales del negocio sean **propios, accesibles y trazables**, con el fin de habilitar **métricas, análisis y Business Intelligence** sin depender de las limitaciones del POS actual.

---

## 2) Alcance v1

### 2.1 Incluye (v1)

**A. Core operativo (obligatorio)**
- Catálogo centralizado de productos (identificación y búsqueda operativa).
- Inventario con entradas (compras/recepciones), salidas (ventas), ajustes y trazabilidad mínima.
- Compras/recepciones con registro de costo.
- Ventas en tienda física con POS básico funcional (efectivo/tarjeta), ticket/nota y actualización automática de inventario.
- Métricas básicas de operación (ventas por periodo, ticket promedio, top productos, ventas por método de pago).

**B. Inversionistas / ledger (incluido en v1, acotado pero completo en trazabilidad)**
- Registro de inversionistas (alta con capital inicial).
- Aportaciones y retiros de capital (retiros solo de capital líquido disponible).
- Control de capital líquido vs dinero en inventario (inventario del inversionista).
- Cálculo automático en venta de productos asociados a inversionista (utilidad, comisiones, devolución de capital, reparto 50/50).
- Historial cronológico de movimientos (toda afectación trazable).
- Acción de reinversión: transferir utilidad a capital.

**C. Apartados y saldos a favor (incluido en v1 por alta frecuencia operativa)**
- Apartado con anticipo (ej. 30%), vigencia (15 días), reserva de producto.
- Liquidación posterior y conversión a venta final.
- Vencimiento: conversión de anticipo a saldo a favor (no reembolsable en efectivo).
- Aplicación de saldo a favor a compras futuras, con trazabilidad.

**D. Canal digital (solo visualización en v1)**
- Catálogo web sincronizado (sin carrito/checkout/pagos).

**E. Control financiero interno (básico)**
- Registro de **gastos fijos** (y, opcionalmente, operativos manuales básicos) para reportes internos.
- Reportes internos gerenciales (base para estado de resultados gerencial y balance gerencial).

**F. Seguridad operativa**
- Usuarios, roles y accesos: **admin, cajero, inversionista**.

### 2.2 No incluye (v1) — exclusiones explícitas
- Venta en línea transaccional (carrito/checkout/pagos web).
- Envíos/logística e integraciones con paqueterías.
- Facturación electrónica CFDI integrada (a definir en fase posterior si aplica).
- Promociones complejas/cupones/reglas avanzadas.
- BI avanzado (data warehouse, dashboards complejos).
- Contabilidad fiscal completa tipo ERP (pólizas, cuentas contables, depreciaciones, etc.).
- Integraciones con marketplaces externos.
- App móvil nativa (posible futuro).

---

## 3) Módulos del sistema (v1)

1. **Catálogo**
2. **Inventario**
3. **Compras / Recepciones**
4. **Ventas (POS básico)**
5. **Apartados y Saldo a Favor**
6. **Inversionistas / Ledger**
7. **Gastos (fijos y operativos básicos)**
8. **Métricas y Reportes Básicos**
9. **Usuarios, Roles y Accesos**
10. **Catálogo Web (solo visualización)**

---

## 4) Roles (v1)

### 4.1 Admin
- Gestiona catálogo, inventario, compras, ventas (consulta), métricas/reportes, gastos.
- Gestiona usuarios/roles.
- Acceso a información de inversionistas (según política interna).

### 4.2 Cajero
- Opera ventas POS: búsqueda, cobro, confirmación, ticket.
- Opera apartados y liquidaciones (según política interna).
- No modifica costos sensibles, ni estados de inversionistas, ni usuarios/roles.
- Ajustes/cancelaciones sensibles solo con autorización admin (a definir).

### 4.3 Inversionista
- Solo lectura: métricas y estados propios, historial de movimientos.
- No ve información de otros inversionistas ni operación interna sensible.
- No modifica operación (catálogo, inventario, ventas).

---

## 5) Reglas de negocio críticas (v1)

### 5.1 Integridad de catálogo e inventario
**RB-31. SKU único**  
No se permitirá crear productos con SKU duplicado. Si se captura un SKU existente, el sistema deberá detectar el duplicado y dirigir al usuario a usar el producto existente.

**RB-33. Incremento de inventario por recepción**  
La cantidad de un producto existente debe incrementarse mediante compras/recepciones (entradas de inventario), no creando duplicados en catálogo.

**RB-34. Búsqueda operativa en POS**  
El POS deberá permitir búsqueda por SKU/código y por nombre, incluyendo coincidencias parciales (no depender de coincidencias exactas únicamente).

### 5.2 Ventas (POS)
**RB-09. Venta confirmada como único disparador**  
Solo ventas confirmadas afectan inventario, métricas y (si aplica) ledger.

**RB-11. No duplicidad de registro**  
Una venta no debe impactar inventario/ledger dos veces por reintentos (ej. impresión fallida).

### 5.3 Comisiones por tarjeta (vigentes)
**RB-02. Comisión tarjeta**  
- Tarjeta normal: 2.00%  
- Tarjeta a 3 MSI: 5.58%  
Solo aplica a pagos con tarjeta.

### 5.4 Inversionistas / Ledger (modelo económico)
**RB-25. Separación de conceptos**  
El ledger distingue al menos: **capital líquido**, **inventario (dinero en inventario)** y **utilidad**.

**RB-21. Alta inversionista con capital inicial**  
Se registra inversionista con capital inicial como movimiento trazable.

**RB-22. Aportación adicional de capital**  
Se permite agregar capital con movimiento trazable.

**RB-24. Retiro de capital solo desde capital líquido**  
Los retiros/disminuciones solo pueden ejecutarse sobre capital líquido disponible (no sobre inventario comprometido).

**RB-26. Compra con capital mueve capital → inventario**  
Compras/asignaciones con capital del inversionista deben reflejar salida de capital líquido y entrada a inventario del inversionista.

**RB-01. Venta con afectación automática a inversionista**  
Al vender un producto asociado a inversionista, el sistema genera automáticamente movimientos de ledger (sin captura manual posterior).

**RB-03. Cálculo de utilidad**  
- Utilidad bruta = Precio final de venta − Costo  
- Utilidad neta distribuible = Utilidad bruta − Comisión (si pago tarjeta)  
Precios se manejan como finales (incluyen IVA 16%) en v1; revisión fiscal detallada queda para etapa posterior.

**RB-04. Reparto de utilidad/pérdida**  
La utilidad neta (o pérdida/impacto por descuento) se reparte 50/50 entre inversionista y Moto Isla.

**RB-05. Devolución de capital**  
En venta de producto de inversionista, el costo se devuelve como **capital recuperado** (movimiento separado de utilidad).  
Ejemplo: costo 10, venta 15 ⇒ utilidad 5; capital devuelto 10; utilidad se reparte 50/50.

**RB-06. Reinversión utilidad → capital**  
Debe existir acción para transferir utilidad a capital (movimiento trazable).

**RB-07. Asignación de productos a inversionista**  
Debe existir forma de marcar/asignar productos (por lote/compra) a inversionista para no perder control y automatizar cálculos.

**RB-08. Trazabilidad cronológica**  
Todo movimiento relevante queda en historial cronológico (capital, compras, ventas, comisiones, utilidad, reinversión, ajustes autorizados).

### 5.5 Apartados y saldo a favor
**RB-12. Apartado con anticipo**  
Se permite apartado con anticipo (ej. 30%) sin considerarlo venta final.

**RB-13. Reserva de inventario**  
El producto apartado queda reservado y no disponible para venta general durante vigencia.

**RB-14. Vigencia**  
Vigencia actual: 15 días.

**RB-15. Liquidación convierte a venta final**  
Al pagar el restante, se convierte en venta final, se entrega producto y se emite ticket.

**RB-16. Vencimiento convierte a saldo a favor**  
Si vence sin liquidar, el producto se libera y el anticipo se convierte en saldo a favor del cliente.

**RB-19. Política: no reembolso en efectivo**  
Anticipos vencidos no se reembolsan en efectivo; se conservan como saldo a favor.

**RB-18. Uso de saldo a favor**  
Saldo a favor puede aplicarse a compras futuras; si el nuevo producto cuesta más, el cliente paga diferencia. (Saldo remanente a definir; por defecto se conserva).

**RB-20. Apartados no afectan ledger hasta venta final**  
Apartados no generan reparto ni devolución de capital a inversionistas hasta liquidación/entrega.

### 5.6 Gastos y estados internos
**RB-28. Registro de gastos fijos**  
Se registran gastos fijos (monto, categoría, periodo/frecuencia) para análisis interno.

**RB-29. Gastos en reportes**  
Reportes internos consideran gastos registrados para estado de resultados gerencial.

**RB-30. No equivale a contabilidad fiscal completa**  
El módulo de gastos es para control interno; contabilidad fiscal completa queda fuera de v1.

---

## 6) Flujos operativos v1 (sin técnico)

### F1) Compra / recepción de mercancía
1) Recibir mercancía.  
2) Registrar productos, cantidades y costos.  
3) Actualizar inventario.  
4) Registrar movimiento de entrada.  
5) Si es capital de inversionista, reflejar movimiento capital→inventario y asignación (según política).

### F2) Asignación de productos a inversionista (si aplica)
1) Identificar inversionista y capital disponible.  
2) Seleccionar productos/lote.  
3) Asignar productos al inversionista.  
4) Registrar asignación trazable y actualizar su inventario/posición.

### F3) Venta normal (sin inversionista)
1) Buscar producto por SKU/nombre (parcial permitido).  
2) Agregar al ticket.  
3) Seleccionar método de pago.  
4) Confirmar pago.  
5) Registrar venta confirmada, descontar inventario, generar ticket, actualizar métricas.

### F4) Venta con afectación automática a inversionista
Disparador: venta confirmada de producto asignado.  
1) Detectar inversionista asociado.  
2) Calcular utilidad (precio−costo) y comisión (si tarjeta).  
3) Repartir 50/50 utilidad/pérdida.  
4) Registrar devolución de capital (costo) como movimiento separado.  
5) Actualizar inventario/posición del inversionista.  
6) Registrar movimientos cronológicos y reflejar en su estado.

### F5) Apartado con anticipo
1) Identificar cliente (datos mínimos).  
2) Registrar anticipo (ej. 30%) y vigencia (15 días).  
3) Reservar producto.  
4) Guardar apartado vigente con trazabilidad.

### F6) Liquidación de apartado
1) Localizar apartado vigente.  
2) Cobrar restante.  
3) Convertir a venta final, emitir ticket, entregar producto.  
4) Si aplica, afectar ledger de inversionista como venta final.

### F7) Vencimiento de apartado → saldo a favor
1) Marcar apartado vencido.  
2) Liberar producto para venta.  
3) Convertir anticipo a saldo a favor del cliente con trazabilidad.

### F8) Uso de saldo a favor
1) Identificar cliente con saldo.  
2) Aplicar saldo a la compra.  
3) Cobrar diferencia si aplica.  
4) Emitir ticket y registrar aplicación del saldo.

### F9) Consulta inversionista
1) Inversionista accede.  
2) Ve métricas/estado/historial propio (solo lectura).

### F10) Reinversión utilidad → capital
1) Ver utilidad disponible.  
2) Registrar transferencia utilidad→capital.  
3) Generar movimientos trazables y actualizar saldos.

---

## 7) Estrategia de adopción (migración gradual)

Se adopta el sistema nuevo de forma incremental:
- Iniciar con **nuevas compras/facturas/productos** (datos nacen en el sistema nuevo).
- Operar ventas de esos productos en el **nuevo POS**, en entorno real y controlado.
- Mantener el POS anterior en paralelo para inventario/ventas históricas previas durante transición.
- Detectar y corregir bugs/problemas operativos con bajo riesgo.
- Ampliar progresivamente hasta reemplazar el POS anterior.

---

## 8) Criterios de aceptación (v1)

### 8.1 Generales
- **CA-G1** Fuente central operativa para los productos en el sistema nuevo.
- **CA-G2** Trazabilidad completa de operaciones relevantes.
- **CA-G3** No duplicidad de ventas/movimientos.
- **CA-G4** Control por roles (admin/cajero/inversionista).
- **CA-G5** Coherencia entre inventario, ventas, métricas y ledger.

### 8.2 Por módulo

**Catálogo**
- **CA-CAT1** Alta/edición de productos con info mínima de venta.
- **CA-CAT2** Localización por SKU y nombre.
- **CA-CAT5** Bloqueo de SKU duplicado.
- **CA-CAT8** Búsqueda por coincidencia parcial (SKU o nombre).
- **CA-CAT4** Identificación de productos asignados a inversionista.

**Inventario**
- **CA-INV1** Entradas por compras/recepciones.
- **CA-INV2** Salidas por venta confirmada.
- **CA-INV3** Ajustes con trazabilidad y permisos.
- **CA-INV4** Reserva por apartado.
- **CA-INV5** Liberación al vencer apartado.

**Compras/Recepciones**
- **CA-COM1** Registro de compras con costo.
- **CA-COM2** Actualiza inventario y deja historial.
- **CA-COM4** Queda listo para vender desde POS nuevo.

**POS**
- **CA-POS1** Ticket con productos agregados por búsqueda.
- **CA-POS2** Pago efectivo/tarjeta.
- **CA-POS3** Venta confirmada descuenta inventario.
- **CA-POS4** Ticket emitido.
- **CA-POS6** Venta de inversionista afecta ledger automáticamente (sin captura manual).

**Apartados / Saldo a favor**
- **CA-APA1** Apartado con anticipo y cliente identificado.
- **CA-APA2** Vigencia (15 días) y estado.
- **CA-APA4** Liquidación convierte en venta final con ticket.
- **CA-APA5** Vencimiento convierte anticipo a saldo a favor y libera producto.
- **CA-APA6** Saldo a favor aplicable a compras futuras y trazable.
- **CA-APA7** No afecta ledger hasta venta final.

**Inversionistas/Ledger**
- **CA-LED1** Alta con capital inicial.
- **CA-LED2** Agregar capital con trazabilidad.
- **CA-LED3** Retirar capital solo de capital líquido.
- **CA-LED4** Separación visible capital líquido / inventario / utilidad.
- **CA-LED6** Venta calcula utilidad, comisión, reparto 50/50 y devolución de capital con movimientos separados.
- **CA-LED7** Reinversión utilidad→capital trazable.
- **CA-LED8** Acceso inversionista solo a su información.

**Gastos**
- **CA-GAS1** Registro de gastos fijos (monto, categoría, periodo/frecuencia).
- **CA-GAS2** Consulta por periodo.
- **CA-GAS3** Integración en reportes internos (estado de resultados gerencial).
- **CA-GAS4** Solo admin modifica gastos.

**Usuarios/Roles**
- **CA-ROL1** Crear usuarios y asignar rol.
- **CA-ROL2** Restricción por rol a módulos/datos.
- **CA-ROL4** Inversionista: solo lectura de panel propio.

**Catálogo Web (solo visualización)**
- **CA-WEB1** Catálogo sincronizado desde base central.
- **CA-WEB3** Sin checkout/pagos en v1.

### 8.3 Criterios de transición (migración)
- **CA-T1** Operación paralela controlada (POS anterior + sistema nuevo).
- **CA-T2** Alta gradual por nuevas compras/facturas en sistema nuevo.
- **CA-T3** Ventas reales de productos nuevos con ticket, inventario y ledger (si aplica).
- **CA-T4** Corrección de incidencias sin detener operación del negocio.
- **CA-T6** Punto de salida definido para dejar POS anterior cuando v1 esté estable.

---

## 9) Riesgos y mitigaciones (iniciales, v1)

- **R1: Duplicidad de SKUs/productos** → *Mitigación:* RB-31 + flujo de recepción para sumar stock.  
- **R2: Búsqueda lenta o imprecisa en caja** → *Mitigación:* RB-34 como requisito de primer nivel en POS.  
- **R3: Cálculo incorrecto de comisiones/utilidad** → *Mitigación:* reglas explícitas (2% / 5.58%) + movimientos separados (capital/utilidad/commission).  
- **R4: Asignación incorrecta de productos a inversionista** → *Mitigación:* RB-07 + trazabilidad RB-08 + control de permisos.  
- **R5: Doble afectación del ledger por reintentos** → *Mitigación:* RB-11 + CA-G3 + trazabilidad.  
- **R6: Apartados sin identificación de cliente** → *Mitigación:* CA-APA1 (datos mínimos obligatorios).  
- **R7: Confusión durante transición con dos POS** → *Mitigación:* estrategia incremental + criterios CA-T + reglas operativas internas de identificación.  
- **R8: Gastos incompletos o mal clasificados** → *Mitigación:* categorías mínimas, control por rol y revisión periódica.

---

## 10) Próximo paso (a partir de este documento)
A partir de este Plan Maestro funcional v1, el siguiente trabajo es definir lo técnico:
- modelo de datos (entidades y relaciones)
- arquitectura de módulos y API
- estrategia de impresión de tickets
- estrategia de migración de datos y convivencia
- planes de prueba operativa (caja, apartados, ledger)
- monitoreo y control de incidencias
