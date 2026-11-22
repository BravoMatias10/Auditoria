"""Criterios de la Ley 19.628 según el texto diferido de la reforma."""

from datetime import date

from .models import Resultado

MARCO = (
    'Ley N.º 19.628, texto modificado por la Ley N.º 21.719. '
    'Fecha de entrada en vigencia que indicaba LeyChile al corte normativo (22-11-2026): '
    '01-12-2026. El boletín 18.623-07 proponía aplazarla al 15-10-2027.'
)
FECHA_CORTE = '22 de noviembre de 2026'
VIGENCIA_DE_REFERENCIA = date(2026, 12, 1)
LEY_CONSOLIDADA = 'https://www.bcn.cl/leychile/Navegar/imprimir?idNorma=141599&idVersion=2026-12-01'
DIARIO_OFICIAL = (
    'https://www.diariooficial.interior.gob.cl/publicaciones/2024/12/13/44023/01/2583630.pdf'
)

PUBLICA = Resultado.Fuente.PUBLICA
INTERNA = Resultado.Fuente.INTERNA
AMBAS = Resultado.Fuente.AMBAS

CRITERIOS = (
    ('1 y 1 bis', 'Ámbito de aplicación', AMBAS,
     'Identifica el operador y documenta qué tratamientos de datos personales tienen vínculo con Chile. '
     'Verifica el establecimiento, la oferta a titulares en Chile, el monitoreo o cualquier excepción invocada.'),
    ('3 a), b), e), 12–14', 'Licitud, fuentes y finalidades', AMBAS,
     'Contrasta los fines informados con el inventario, las fuentes lícitas y la base acreditada de cada tratamiento. '
     'Cuando se alegue interés legítimo, verifica la necesidad y el efecto sobre los titulares.'),
    ('12 y 14 ter k)', 'Obtención y retiro del consentimiento', AMBAS,
     'Si se invoca consentimiento, revisa información previa, acción afirmativa, registros, versión y retiro efectivo. '
     'Justifica la inaplicabilidad con el inventario y la base alternativa.'),
    ('3 c) y 14 quáter', 'Datos necesarios y privacidad por defecto', AMBAS,
     'Relaciona cada campo y cada ajuste por defecto con la finalidad. Contrasta formularios, configuración '
     'y acceso efectivo a los datos.'),
    ('3 c), 14 d) y 14 quáter', 'Conservación, supresión y anonimización', INTERNA,
     'Solicita plazos por finalidad y respaldo de ejecución y de eliminación en copias. Si se obtuvieron datos '
     'para medidas precontractuales, revisa el deber específico de supresión o anonimización.'),
    ('3 d), 6 y 14 c)', 'Calidad y rectificación de datos', INTERNA,
     'Verifica exactitud, actualización y pertinencia con casos depurados. Revisa correcciones y, cuando '
     'proceda, su comunicación a destinatarios.'),
    ('3 g) y 14 ter a)', 'Publicación y versión de la política', PUBLICA,
     'Registra la ubicación, fecha y versión de la política. Revisa si es accesible y comprensible.'),
    ('14 ter b)', 'Identificación del responsable', PUBLICA,
     'Verifica la identificación del responsable, su representante legal y el encargado de prevención si existe.'),
    ('14 ter c)', 'Publicación del canal de privacidad', PUBLICA,
     'Localiza el domicilio, correo electrónico, formulario u otro medio equivalente habilitado para solicitudes.'),
    ('14 ter d)', 'Datos, titulares, destinatarios, fines y bases informados', PUBLICA,
     'Comprueba cada mención exigible. Si se declara interés legítimo, verifica que la política lo identifique.'),
    ('14 ter e)', 'Información sobre seguridad', PUBLICA,
     'Verifica que se publiquen la política y las medidas adoptadas para proteger los datos. La eficacia '
     'de los controles se evalúa en el criterio de seguridad.'),
    ('14 ter f)', 'Información sobre los derechos', PUBLICA,
     'Verifica la información publicada sobre acceso, rectificación, supresión, oposición y portabilidad.'),
    ('14 ter g) y 41', 'Información sobre el recurso ante la Agencia', PUBLICA,
     'Verifica si se explica cuándo acudir a la Agencia ante rechazo o falta de respuesta oportuna.'),
    ('14 ter h)', 'Transparencia de transferencias internacionales', AMBAS,
     'Si hay transferencias, verifica la información publicada sobre destino, adecuación y garantías cuando '
     'procedan. Acredita la existencia o ausencia de transferencias con el inventario.'),
    ('14 ter i)', 'Información sobre el período de conservación', PUBLICA,
     'Registra el período publicado y los tratamientos que cubre. Evalúa la ejecución del plazo en el '
     'criterio de conservación.'),
    ('14 ter j)', 'Información sobre el origen de los datos', PUBLICA,
     'Verifica si se informa el origen y, cuando corresponda, su procedencia de fuentes de acceso público.'),
    ('14 ter k)', 'Información sobre el derecho a retirar el consentimiento', AMBAS,
     'Identifica si se usa consentimiento y comprueba que la política explique su retiro y el efecto '
     'sobre los tratamientos anteriores.'),
    ('14 ter l)', 'Información sobre decisiones automatizadas y perfiles', AMBAS,
     'Contrasta el inventario con lo informado sobre existencia, lógica y consecuencias para el titular.'),
    ('4, 5, 10 y 11', 'Atención de solicitudes y derecho de acceso', AMBAS,
     'Comprueba canal, autenticación, acuse y respuesta escrita con respaldos. Revisa el plazo de 30 días '
     'corridos y su posible prórroga, gratuidad aplicable, denegaciones y aviso sobre reclamación.'),
    ('6–8 y 11', 'Rectificación, supresión y oposición', INTERNA,
     'Revisa casos anonimizados y sus fundamentos. Verifica la ejecución de cambios, supresión u oposición '
     'y las comunicaciones a destinatarios cuando procedan.'),
    ('8 ter y 11', 'Bloqueo del tratamiento', INTERNA,
     'Comprueba el cese del tratamiento afectado mientras se resuelve la solicitud según corresponda, la '
     'respuesta al bloqueo fundado en dos días hábiles y el aviso a la Agencia en caso de rechazo.'),
    ('9–11', 'Portabilidad', INTERNA,
     'Para datos facilitados por el titular y tratados de forma automatizada sobre la base de consentimiento, '
     'revisa formato estructurado, vía de entrega y transmisión directa cuando sea técnicamente posible.'),
    ('3 h) y 14 bis', 'Secreto y confidencialidad', INTERNA,
     'Solicita reglas de acceso, compromisos y su vigencia tras terminar la relación. Verifica que las '
     'personas accedan solo a los datos necesarios.'),
    ('14 quinquies', 'Protección observable de la conexión', PUBLICA,
     'Registra si la navegación ordinaria usa HTTPS y qué cabeceras se observan, si se revisaron. '
     'Evalúa este control público dentro de su alcance.'),
    ('3 f), 14 quáter, 14 quinquies y 14 septies', 'Controles técnicos y organizativos', INTERNA,
     'Revisa riesgos, permisos, cifrado pertinente, integridad, resiliencia, respaldos, restauración, '
     'controles desde el diseño y verificaciones periódicas. Aplica estándares de la Agencia según el perfil.'),
    ('14 sexies', 'Preparación para incidentes', INTERNA,
     'Solicita protocolo, responsables, canales, registro y pruebas de respuesta.'),
    ('14 sexies', 'Registro y notificación de incidentes', INTERNA,
     'Si hubo incidentes, verifica valoración del riesgo, registros, aviso oportuno a la Agencia y aviso a '
     'titulares cuando corresponda. Justifica la ausencia de avisos con el caso o registro de incidentes.'),
    ('3, 8, 12–13 y 14 ter', 'Cookies, rastreo y marketing', AMBAS,
     'Compara avisos, opciones y comportamiento durante navegación pública con el inventario y la configuración. '
     'Evalúa la base, finalidad, necesidad y oposición o retiro según proceda.'),
    ('15', 'Cesiones a otros responsables', INTERNA,
     'Si hay cesiones, comprueba base jurídica, documento, partes, datos, fines y la actuación del receptor. '
     'Usa el inventario para justificar la ausencia de cesiones.'),
    ('15 bis', 'Proveedores que tratan datos por encargo', INTERNA,
     'Si hay encargados, comprueba contrato, instrucciones, seguridad, incidentes, subencargos autorizados y '
     'devolución o supresión al concluir. Solicita inventario de proveedores.'),
    ('27–29', 'Habilitación de transferencias internacionales', INTERNA,
     'Comprueba flujos, destinatarios y destinos. Si hay transferencias, revisa la base, adecuación, '
     'garantías u otra habilitación aplicable y su respaldo.'),
    ('8 bis', 'Garantías ante decisiones automatizadas', INTERNA,
     'Si hay decisiones automatizadas con efectos jurídicos o significativos para titulares, comprueba '
     'supuesto habilitante, explicación, opinión, intervención humana y revisión.'),
    ('15 ter', 'Evaluación previa de impacto', INTERNA,
     'Solicita análisis previo de riesgos y del supuesto legal. Si hay alto riesgo o un caso obligatorio, '
     'revisa la evaluación previa y las medidas adoptadas.'),
    ('16 y 16 bis', 'Datos sensibles, de salud y perfil biológico', INTERNA,
     'Verifica el inventario. Si se tratan estas categorías, solicita habilitación, finalidad y salvaguardas '
     'específicas y revisa las restricciones legales.'),
    ('16 ter', 'Datos biométricos', AMBAS,
     'Si se utilizan, revisa habilitación, salvaguardas e información sobre sistema, finalidad, plazo '
     'y vías de ejercicio de derechos.'),
    ('16 quáter', 'Datos de niños, niñas y adolescentes', INTERNA,
     'Si se tratan, documenta interés superior y autonomía progresiva, edades, bases aplicables y '
     'representación o autorización cuando correspondan.'),
    ('16 sexies', 'Datos de geolocalización', AMBAS,
     'Si se tratan, comprueba habilitación y aviso sobre tipo de datos, finalidad, duración y comunicación '
     'a terceros para servicios de valor añadido cuando proceda.'),
    ('16 quinquies', 'Tratamiento de investigación de interés público', INTERNA,
     'Si se invoca este régimen, verifica finalidad exclusiva, interés público, medidas de calidad y '
     'seguridad y anonimización antes de publicar resultados.'),
    ('17–19', 'Régimen de información económica y financiera', INTERNA,
     'Si hay tratamientos cubiertos por el Título III, verifica habilitación, categorías, restricciones '
     'de comunicación, finalidad y límites temporales.'),
    ('20–26 y 54–55', 'Régimen de órganos públicos y órganos especiales', AMBAS,
     'Si el responsable es un órgano cubierto, verifica competencia, finalidad, derechos, conservación, '
     'comunicaciones, convenios publicados y regímenes especiales aplicables.'),
    ('48', 'Prevención de infracciones', INTERNA,
     'Solicita un inventario, controles, responsables, verificaciones y medidas correctivas acordes '
     'con los riesgos del tratamiento.'),
    ('49–51', 'Programa voluntario de cumplimiento', INTERNA,
     'Si fue adoptado, verifica designación, autonomía, recursos, protocolos y acreditación de certificación '
     'cuando se invoque. Documenta con evidencia si el programa no se adoptó.'),
    ('34 bis–34 quáter y 41–42', 'Requerimientos y resoluciones de la Agencia', INTERNA,
     'Si hubo requerimientos o procedimientos aplicables, revisa comunicaciones, plazos, respuestas '
     'y ejecución de medidas.'),
)
