# Auditoría web de protección de datos personales

Proyecto académico basado en `catalogo`. Consulta un sitio web y organiza los resultados según 44 criterios de la Ley chilena N.º 19.628 modificada por la Ley N.º 21.719. Cada auditoría registra el alcance y cada resultado conserva su artículo, evidencia, observación, estado y acciones pendientes.

## Ejecutar en local

Usa **Python 3.11.0**, **Django 3.2.25** y el módulo estándar **sqlite3**. Ejecuta los comandos desde la carpeta que contiene `manage.py`. Comprueba la versión de Python antes de crear el entorno.

### Windows PowerShell

```powershell
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m django --version
.\.venv\Scripts\python.exe -c "import sqlite3; print(sqlite3.sqlite_version)"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
$env:DJANGO_DEBUG = "1"
.\.venv\Scripts\python.exe manage.py runserver
```

Si ejecutas el proyecto en Windows sin entorno virtual, instala la actualización desde la carpeta que contiene `manage.py`:

```powershell
py -3.11 -m pip install --user -r requirements.txt
py -3.11 -m playwright install chromium
```

Usa `py -3.11 manage.py` para los comandos de Django.

### macOS o Linux

```bash
python3.11 --version
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m django --version
.venv/bin/python -c 'import sqlite3; print(sqlite3.sqlite_version)'
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
DJANGO_DEBUG=1 .venv/bin/python manage.py runserver
```

Abre [la aplicación local](http://127.0.0.1:8000/). Las migraciones crean `db.sqlite3` con el esquema. Usa cuentas ficticias. Django 3.2.25 funciona en la combinación probada para este piloto y carece de soporte oficial sobre Python 3.11 y de actualizaciones de seguridad vigentes.

## Configurar los roles

1. Para el rol **Usuario**, elige **Crear cuenta** en la pantalla de inicio de sesión. Crea una cuenta ficticia e inicia sesión. El registro asigna el rol automáticamente.
2. Para el rol **Administrador**, entra con la cuenta creada por `createsuperuser`. Desde **Administración → Usuarios** puedes gestionar las cuentas.

El administrador gestiona cuentas y consulta todas las auditorías y sus reportes. Los usuarios consultan solo sus registros. Ambos roles pueden crear auditorías y editar o eliminar aquellas de las que son propietarios. Las vistas comprueban el rol y el propietario aunque se introduzca la URL directa.

## Evaluar, guardar y compartir

1. Abre **Nueva auditoría**, pega una URL pública y pulsa **Auditar sitio**.
2. Lee el resumen. La aplicación comprueba si la página se sirve por HTTPS y busca enlaces públicos de privacidad del mismo dominio. Si encuentra una política, busca su fecha, versión, canal de privacidad y menciones a derechos, conservación y cookies.
3. Revisa los estados por punto. **Cumple** significa que se pudo comprobar ese punto. **No cumple** indica un problema observado. **No verificable** significa que la revisión encontró una mención insuficiente, no pudo leer la página o requiere información interna. Puedes adjuntar una referencia depurada al criterio si consigues evidencia posterior. **No aplica** exige una justificación.
4. Abre **Ver reporte** y selecciona **Imprimir / Guardar como PDF** para exportar el documento y adjuntarlo por correo.

La primera revisión lee HTML y sigue hasta dos enlaces públicos de privacidad. Una página puede declarar su política en otro dominio mediante un enlace seguro con la relación `privacy-policy`. Para YouTube, si no encuentra la política en la página leída, consulta la política de Google enlazada en la ayuda oficial de YouTube. Consulta HTTP o HTTPS en sus puertos habituales, valida la dirección en cada redirección y usa destinos públicos IPv4. Admite HTML normal y comprimido con gzip. Si una página es extensa, se revisan hasta 2 MiB de contenido. Cuando la página no puede leerse, el reporte explica el motivo y conserva lo que pudo observar de la conexión. Se guardan hallazgos resumidos y sus páginas de referencia.

Cuando la primera lectura no encuentra una política y hay indicios de JavaScript, Playwright abre Chromium de forma aislada. La aplicación consulta recursos públicos del sitio con lectura acotada y no usa la sesión del auditor. Una página que requiera inicio de sesión, CAPTCHA, scripts indispensables de otro dominio, PDF o un destino solo IPv6 puede quedar sin verificar.

La vista se genera con los resultados guardados al momento de abrirla. Una copia de PDF exportada queda en manos de quien la guarda o comparte. El sistema limita el acceso a la vista original.

## Datos propios y tareas del responsable

| Datos | Origen y finalidad | Medida aplicada |
|---|---|---|
| Nombre de usuario, hash de contraseña, rol, estado de cuenta y fechas de alta y acceso | Registro del usuario o alta administrativa. Autenticación y autorización. El panel de Django puede almacenar datos de contacto o nombre si el operador los ingresa. Mantén esos campos vacíos cuando sean innecesarios. | Hash estándar de Django y acceso administrativo restringido. |
| Datos de sesión, cookie de sesión, token CSRF y actividad administrativa | Acceso autenticado, integridad de formularios y operaciones sobre cuentas en el panel de Django. | Sesiones de Django, protección CSRF y peticiones POST para cambios. La clave se toma del entorno si se configura o se genera para la ejecución. |
| Propietario, URL, fechas, alcance, artículos, evidencia, observaciones y acciones | URL y notas del auditor, hallazgos resumidos de páginas públicas y evidencia adicional si se registra. Sirve para generar el reporte. | Aislamiento por propietario, acceso de consulta del administrador, campos acotados y confirmación para borrar. |
| Reportes exportados | Datos de la auditoría seleccionada. | Vista autenticada y sin almacenamiento de PDF en el servidor. El reporte omite la identidad de la cuenta. El auditor debe revisar los campos libres para excluir identificadores antes de exportar. |

El aviso público está en `/privacidad/` y explica las cookies técnicas, su finalidad y su duración. Las variables `PRIVACIDAD_RESPONSABLE` y `PRIVACIDAD_CONTACTO` muestran la identidad y el canal configurados. Antes de usar datos reales, el responsable debe verificar y completar el aviso con representante cuando proceda, finalidades y bases, fuentes, destinatarios, seguridad y períodos de conservación efectivos y las menciones condicionadas del art. 14 ter.

El responsable debe acreditar el inventario y sus bases, gestionar solicitudes con acuse y cómputo de plazos, documentar rectificaciones, supresión y bloqueo, mantener evidencia de prevención y contar con un protocolo de incidentes. Debe fijar plazos de cuentas, auditorías, registros del panel, sesiones, copias y respaldos. Django admite desactivar o eliminar cuentas en el panel y limpiar sesiones vencidas con `python manage.py clearsessions`. El borrado de una auditoría elimina sus resultados. El borrado de una cuenta elimina sus auditorías y resultados asociados. Revisa las obligaciones de conservación antes de borrar y gestiona aparte las copias compartidas.

El entorno real debe acreditar seguridad según el riesgo, incluida gestión de la clave, almacenamiento y respaldos de SQLite, restauración, confidencialidad y seguridad del despliegue. Verifica encargados, cesiones, transferencias y evaluación de impacto cuando se activen. El piloto está configurado para ejecución local.

## Verificación

Ejecuta con el mismo Python del entorno:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Las pruebas recorren el inicio de sesión con ambos roles, creación, edición, estados y validación de evidencia, consulta del reporte, exclusión de datos de cuenta del reporte y denegación de lecturas y cambios ajenos, incluso cuando se manipula la URL. También comprueban el rechazo de solicitudes de escritura sin token CSRF, el cierre de sesión y el borrado confirmado.

## Explicación para la defensa

> La autorización se comprueba en el servidor. Cada auditoría guarda su propietario y una copia de los criterios aplicados en ese momento. Cada resultado apunta a un artículo y a evidencia concreta. Si la web publica un plazo de conservación, puedo registrar lo que publicó. Para comprobar si efectivamente borra a tiempo, necesito evidencia del proceso. El PDF muestra las dos conclusiones por separado y los puntos pendientes.

## Fuentes oficiales

El catálogo conserva el texto legal de referencia y su fecha de corte. Al 22 de noviembre de 2026, LeyChile indicaba el 1 de diciembre de 2026 como fecha de vigencia diferida. El boletín 18.623-07, despachado al Ejecutivo, preveía el 15 de octubre de 2027. Comprueba la versión publicada y su vigencia al fechar cada evaluación de uso real.

- [Ley N.º 19.628 con texto consolidado diferido en LeyChile](https://www.bcn.cl/leychile/Navegar/imprimir?idNorma=141599&idVersion=2026-12-01)
- [Ley N.º 21.719 publicada en el Diario Oficial](https://www.diariooficial.interior.gob.cl/publicaciones/2024/12/13/44023/01/2583630.pdf)
- [Tramitación del boletín 18.623-07 en la Cámara](https://camara.cl/legislacion/ProyectosDeLey/tramitacion.aspx?prmBOLETIN=18623-07&prmID=19307)
