# Informe de Test de Intrusión — ACME Corp

| | |
| :--- | :--- |
| **Cliente** | ACME Corp |
| **Engagement** | ACME-2026-001 |
| **Tipo** | Pentest web externo + infraestructura perimetral |
| **Ventana de pruebas** | 2026-06-01 – 2026-06-09 |
| **Autorización** | SOW-2026-0042 |
| **Autor** | (tester) · **Revisado por**: (pendiente) |
| **Clasificación** | CONFIDENCIAL |

> ⚠️ Borrador asistido. Requiere revisión humana antes de la entrega al cliente.

> _Este es un informe de MUESTRA generado desde `contracts/examples/engagement.sample.json`
> para ilustrar el formato y el tono de salida del agente `reporting`._

---

## 1. Resumen ejecutivo

Entre el 1 y el 9 de junio de 2026 evaluamos la aplicación pública de ACME
(`app.acme.example`) y su concentrador VPN perimetral, con autorización del contrato
SOW-2026-0042.

El riesgo actual es **crítico**. Dos de los problemas encontrados permiten a un atacante
externo, sin credenciales, acceder a datos de clientes y a la red interna.

| Severidad | Nº |
| :--- | :---: |
| Crítico | 2 |
| Alto | 0 |
| Medio | 0 |
| Bajo | 0 |

**Lo más urgente, en términos de negocio:**

1. La búsqueda de la web filtra la base de datos completa de clientes. Cualquiera con un
   navegador puede recuperar unos 50.000 registros con sus contraseñas. Es una brecha de
   datos personales con impacto regulatorio directo (RGPD).
2. El acceso VPN de Fortinet tiene una vulnerabilidad pública con exploit conocido y
   explotación activa en el mundo real. Permite robar credenciales válidas y entrar en la
   red interna como si fueras un empleado.

**Recomendaciones estratégicas.** Cerrar primero los dos puntos de entrada (parchear el
Fortinet y corregir la búsqueda); después rotar todas las credenciales VPN, que deben
considerarse comprometidas. A medio plazo, revisar el código en busca de más consultas sin
parametrizar y establecer un proceso de parcheo del perímetro con plazos.

## 2. Alcance y reglas de enganche

- **En scope:** `app.acme.example` y el rango perimetral autorizado (incluye `203.0.113.10`).
- **Fuera de scope:** infraestructura de correo y la cuenta de AWS compartida.
- **Límites:** sin denegación de servicio; ventana de pruebas nocturna.

## 3. Metodología

Seguimos PTES, la OWASP WSTG para la parte web y NIST SP 800-115, con las técnicas mapeadas
a MITRE ATT&CK. El trabajo fue por fases: reconocimiento, enumeración, explotación y
confirmación. La priorización de los hallazgos no se basa solo en el CVSS: pesa también si
hay exploit público y explotación activa conocida.

## 4. Hallazgos

### F-001. Inyección SQL no autenticada en el parámetro `id` de `/buscar`

| | |
| :--- | :--- |
| **Severidad** | Crítico |
| **CVSS 3.1** | 9.8 (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`) |
| **Clasificación** | CWE-89 · A03:2021-Injection · T1190 |
| **Activos afectados** | https://app.acme.example |
| **Estado** | Explotado |
| **Referencias** | OWASP Top 10 A03:2021 |

**Descripción.** El parámetro `id` de `/buscar` se concatena directamente en una consulta
SQL. No hay validación de tipo ni consulta parametrizada, así que el atacante controla parte
de la sentencia que ejecuta la base de datos.

**Impacto de negocio.** Un atacante no autenticado puede leer toda la base de datos de
clientes —unos 50.000 registros con sus hashes de contraseña— desde el navegador. Es una
fuga de datos personales notificable y un riesgo directo de toma de cuentas.

**Pasos de reproducción.**
1. Abrir `https://app.acme.example/buscar?id=1`.
2. Inyectar `' UNION SELECT usuario,password,3 FROM usuarios-- -`.
3. La respuesta incluye el volcado de usuarios y hashes.

**Evidencia.**
```
GET /buscar?id=1' UNION SELECT usuario,password,3 FROM usuarios-- -
-> 50.123 filas devueltas (hashes bcrypt redactados)
```

**Remediación.** Pasar la consulta a *prepared statements* con parámetros vinculados, y
validar que `id` es numérico antes de usarlo. Revisar el resto de endpoints por el mismo
patrón.

---

### F-002. FortiOS SSL-VPN vulnerable a path traversal (CVE-2018-13379)

| | |
| :--- | :--- |
| **Severidad** | Crítico |
| **CVSS 3.1** | 9.1 (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:L/A:L`) |
| **Clasificación** | CWE-22 · T1190 |
| **Activos afectados** | 203.0.113.10:10443 (FortiOS 6.0.4) |
| **Estado** | Confirmado |
| **Referencias** | CVE-2018-13379 · CISA KEV · EPSS 0.945 · exploit público (ExploitDB) |

**Descripción.** La versión 6.0.4 de FortiOS expone el SSL-VPN a una lectura de ficheros
por path traversal. Está en el catálogo KEV de CISA (explotación activa confirmada), tiene
exploit público y CISA la marca como automatizable.

**Impacto de negocio.** Un atacante puede leer el fichero de sesiones del VPN y obtener
credenciales válidas en texto claro. Con ellas entra en la red interna como un empleado
legítimo, sin levantar sospechas. Este fallo es uno de los más usados por grupos de
ransomware para el acceso inicial.

**Pasos de reproducción.**
1. Petición a `/remote/fgt_lang?lang=/../../../..//////////dev/cmdb/sslvpn_websession`.
2. Recuperar `sslvpn_websession` con usuarios y contraseñas.

**Evidencia.**
```
GET /remote/fgt_lang?lang=/../../../..//////////dev/cmdb/sslvpn_websession
-> credenciales de sesión en texto claro (redactadas)
```

**Remediación.** Actualizar FortiOS a una versión parcheada (6.0.5 o 6.2.0 en adelante) de
inmediato. Después, rotar todas las credenciales VPN: dalas por comprometidas.

## 5. Hoja de ruta de remediación

| Prioridad | Acción | Hallazgos | Plazo sugerido |
| :--- | :--- | :--- | :--- |
| 1 (inmediata) | Parchear FortiOS y rotar credenciales VPN | F-002 | 48 h |
| 1 (inmediata) | Parametrizar la consulta de `/buscar` | F-001 | 48 h |
| 2 | Revisar el resto de endpoints por SQLi | F-001 | 2 semanas |
| 3 (estratégica) | Proceso de parcheo del perímetro con SLA | F-002 | 1 mes |

## 6. Anexos

- A. Evidencia extendida y salida de herramientas.
- B. Referencias: CVE-2018-13379, CISA KEV, OWASP A03:2021.
- C. Glosario para lectores no técnicos.
