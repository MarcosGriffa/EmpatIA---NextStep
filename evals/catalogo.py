"""
catalogo.py — El "universo" del que salen los CVs y ofertas sintéticos.

8 rubros × 3 roles. Cada rol tiene:
  - titulos:  variantes de cómo se publica el puesto (para que no todas
              las ofertas digan exactamente lo mismo).
  - skills:   (español, inglés). Las primeras 6 son el núcleo del rol —
              las ofertas las piden más seguido.
  - tareas:   frases de responsabilidades, se usan en CVs (pasado) y en
              ofertas (presente).
  - estudios: lo que pondría un CV real de ese rol.

POR QUÉ IMPORTA: la etiqueta "correcta" de cada par CV–oferta se calcula
a partir de estos campos (rol, seniority, skills) en etiquetas.py — NO
la decide un LLM. Así el sistema que se evalúa nunca es el que corrige.
"""

from __future__ import annotations

SENIORITIES = ["jr", "ssr", "sr"]
SENIORITY_LABEL = {"jr": "Junior", "ssr": "Semi Senior", "sr": "Senior"}
SENIORITY_LABEL_EN = {"jr": "Junior", "ssr": "Mid-level", "sr": "Senior"}
SENIORITY_YEARS = {"jr": (0, 2), "ssr": (2, 5), "sr": (6, 12)}

ROLES: dict[str, dict] = {
    # ── Tecnología ────────────────────────────────────────────────
    "analista_datos": {
        "rubro": "tecnologia",
        "nombre": "Analista de Datos",
        "titulos": ["Analista de Datos", "Data Analyst", "Analista BI", "Analista de Business Intelligence"],
        "titulos_en": ["Data Analyst", "BI Analyst", "Business Intelligence Analyst"],
        "skills": [
            ("SQL", "SQL"), ("Power BI", "Power BI"), ("Python", "Python"), ("Excel avanzado", "Advanced Excel"),
            ("modelado de datos", "data modeling"), ("pandas", "pandas"), ("Tableau", "Tableau"),
            ("estadística", "statistics"), ("DAX", "DAX"), ("ETL", "ETL pipelines"),
        ],
        "tareas": [
            "construir tableros de indicadores para el área comercial",
            "escribir consultas SQL sobre la base de ventas",
            "automatizar reportes semanales con Python",
            "limpiar y validar datos de distintas fuentes",
            "presentar hallazgos a gerencia",
        ],
        "estudios": ["Lic. en Ciencia de Datos (en curso)", "Lic. en Economía", "Ing. en Sistemas (en curso)"],
    },
    "dev_backend": {
        "rubro": "tecnologia",
        "nombre": "Desarrollador/a Backend",
        "titulos": ["Desarrollador Backend", "Backend Developer", "Programador Python", "Desarrollador/a de APIs"],
        "titulos_en": ["Backend Developer", "Python Developer", "Backend Engineer"],
        "skills": [
            ("Python", "Python"), ("APIs REST", "REST APIs"), ("PostgreSQL", "PostgreSQL"), ("Docker", "Docker"),
            ("Git", "Git"), ("FastAPI", "FastAPI"), ("Django", "Django"), ("testing automatizado", "automated testing"),
            ("AWS", "AWS"), ("Node.js", "Node.js"),
        ],
        "tareas": [
            "desarrollar y mantener APIs REST",
            "diseñar esquemas de base de datos",
            "escribir tests automatizados",
            "hacer code review con el equipo",
            "desplegar servicios en contenedores",
        ],
        "estudios": ["Ing. en Sistemas", "Tecnicatura en Programación", "Lic. en Informática (en curso)"],
    },
    "soporte_it": {
        "rubro": "tecnologia",
        "nombre": "Soporte IT",
        "titulos": ["Soporte Técnico IT", "Help Desk", "Técnico de Soporte", "Mesa de Ayuda"],
        "titulos_en": ["IT Support Technician", "Help Desk Analyst", "IT Support Specialist"],
        "skills": [
            ("Windows", "Windows"), ("redes", "networking"), ("Active Directory", "Active Directory"),
            ("hardware", "hardware troubleshooting"), ("Office 365", "Office 365"), ("ticketing", "ticketing systems"),
            ("impresoras", "printers"), ("Linux básico", "basic Linux"), ("VPN", "VPN"), ("backups", "backups"),
        ],
        "tareas": [
            "resolver incidentes de usuarios por mesa de ayuda",
            "instalar y configurar puestos de trabajo",
            "administrar usuarios y permisos",
            "mantener el inventario de equipos",
            "documentar procedimientos de soporte",
        ],
        "estudios": ["Técnico en Computación", "Tecnicatura en Redes (en curso)", "Secundario técnico"],
    },
    # ── Ventas ────────────────────────────────────────────────────
    "vendedor_salon": {
        "rubro": "ventas",
        "nombre": "Vendedor/a de Salón",
        "titulos": ["Vendedor/a de Salón", "Vendedora para local de indumentaria", "Asesor/a de Ventas", "Vendedor/a de Mostrador"],
        "skills": [
            ("atención al cliente", ""), ("manejo de caja", ""), ("objetivos de venta", ""), ("armado de vidriera", ""),
            ("control de stock", ""), ("cierre de venta", ""), ("fidelización", ""), ("facturación", ""),
            ("reposición", ""), ("trabajo por comisión", ""),
        ],
        "tareas": [
            "asesorar a clientes en el salón",
            "cumplir objetivos mensuales de venta",
            "realizar arqueos de caja",
            "reponer mercadería y armar vidrieras",
            "gestionar cambios y devoluciones",
        ],
        "estudios": ["Secundario completo", "Curso de Técnicas de Venta"],
    },
    "ejecutivo_comercial": {
        "rubro": "ventas",
        "nombre": "Ejecutivo/a Comercial",
        "titulos": ["Ejecutivo/a Comercial", "Ejecutivo de Cuentas", "Representante Comercial B2B", "Key Account"],
        "skills": [
            ("prospección", ""), ("CRM", ""), ("negociación", ""), ("cartera de clientes", ""),
            ("presentaciones comerciales", ""), ("cotizaciones", ""), ("ventas B2B", ""), ("seguimiento de oportunidades", ""),
            ("visitas a clientes", ""), ("licencia de conducir", ""),
        ],
        "tareas": [
            "prospectar nuevas empresas clientes",
            "negociar condiciones comerciales",
            "administrar una cartera de cuentas",
            "registrar oportunidades en el CRM",
            "preparar cotizaciones y propuestas",
        ],
        "estudios": ["Lic. en Comercialización", "Lic. en Administración (en curso)", "Secundario completo"],
    },
    "atencion_cliente": {
        "rubro": "ventas",
        "nombre": "Representante de Atención al Cliente",
        "titulos": ["Representante de Atención al Cliente", "Operador/a de Call Center", "Agente de Contact Center", "Atención al Cliente telefónica"],
        "skills": [
            ("atención telefónica", ""), ("resolución de reclamos", ""), ("CRM", ""), ("chat y mail", ""),
            ("empatía", ""), ("retención de clientes", ""), ("tipeo rápido", ""), ("trabajo por turnos", ""),
            ("venta telefónica", ""), ("manejo de PC", ""),
        ],
        "tareas": [
            "atender consultas por teléfono, chat y mail",
            "resolver reclamos de clientes",
            "registrar casos en el CRM",
            "ofrecer productos en llamadas salientes",
            "cumplir indicadores de calidad de atención",
        ],
        "estudios": ["Secundario completo", "Curso de Atención al Cliente"],
    },
    # ── Salud ─────────────────────────────────────────────────────
    "enfermero": {
        "rubro": "salud",
        "nombre": "Enfermero/a",
        "titulos": ["Enfermero/a", "Licenciado/a en Enfermería", "Enfermero/a de Internación", "Enfermero/a para Guardia"],
        "skills": [
            ("administración de medicación", ""), ("control de signos vitales", ""), ("curaciones", ""), ("matrícula vigente", ""),
            ("terapia intensiva", ""), ("RCP", ""), ("historia clínica", ""), ("extracciones", ""),
            ("bioseguridad", ""), ("trabajo por guardias", ""),
        ],
        "tareas": [
            "administrar medicación según indicación médica",
            "controlar signos vitales de pacientes internados",
            "realizar curaciones y extracciones",
            "registrar evolución en la historia clínica",
            "asistir en emergencias de guardia",
        ],
        "estudios": ["Lic. en Enfermería", "Enfermería Profesional (Cruz Roja)"],
    },
    "admin_salud": {
        "rubro": "salud",
        "nombre": "Recepcionista / Administrativo/a de Salud",
        "titulos": ["Recepcionista de Consultorio", "Administrativo/a de Clínica", "Secretaria Médica", "Admisión de Pacientes"],
        "skills": [
            ("gestión de turnos", ""), ("obras sociales", ""), ("autorizaciones", ""), ("atención al paciente", ""),
            ("facturación médica", ""), ("terminología médica", ""), ("manejo de agenda", ""), ("Excel", ""),
            ("cobro de coseguros", ""), ("sistema de historia clínica", ""),
        ],
        "tareas": [
            "otorgar y confirmar turnos",
            "gestionar autorizaciones con obras sociales",
            "recibir pacientes y verificar coberturas",
            "facturar prestaciones médicas",
            "organizar la agenda de los profesionales",
        ],
        "estudios": ["Secretariado Médico", "Secundario completo"],
    },
    "tecnico_laboratorio": {
        "rubro": "salud",
        "nombre": "Técnico/a de Laboratorio",
        "titulos": ["Técnico/a de Laboratorio", "Técnico/a en Análisis Clínicos", "Extraccionista", "Técnico/a de Laboratorio Bioquímico"],
        "skills": [
            ("extracciones", ""), ("procesamiento de muestras", ""), ("hematología", ""), ("química clínica", ""),
            ("bioseguridad", ""), ("control de calidad de laboratorio", ""), ("autoanalizadores", ""), ("microbiología", ""),
            ("registro de resultados", ""), ("matrícula vigente", ""),
        ],
        "tareas": [
            "realizar extracciones de sangre",
            "procesar muestras en autoanalizadores",
            "aplicar controles de calidad internos",
            "cargar resultados en el sistema del laboratorio",
            "mantener normas de bioseguridad",
        ],
        "estudios": ["Técnico en Laboratorio", "Tecnicatura en Análisis Clínicos"],
    },
    # ── Logística ─────────────────────────────────────────────────
    "operario_deposito": {
        "rubro": "logistica",
        "nombre": "Operario/a de Depósito",
        "titulos": ["Operario/a de Depósito", "Auxiliar de Logística", "Preparador/a de Pedidos", "Operario de Almacén"],
        "skills": [
            ("picking", ""), ("autoelevador", ""), ("carga y descarga", ""), ("control de inventario", ""),
            ("lector de código de barras", ""), ("armado de pedidos", ""), ("WMS", ""), ("disponibilidad horaria", ""),
            ("recepción de mercadería", ""), ("normas de seguridad", ""),
        ],
        "tareas": [
            "preparar pedidos con lector de código de barras",
            "operar autoelevador",
            "realizar carga y descarga de camiones",
            "participar en inventarios rotativos",
            "recepcionar y ubicar mercadería",
        ],
        "estudios": ["Secundario completo", "Carnet de autoelevadorista"],
    },
    "chofer_reparto": {
        "rubro": "logistica",
        "nombre": "Chofer de Reparto",
        "titulos": ["Chofer de Reparto", "Conductor/a de Utilitario", "Repartidor/a con Vehículo", "Chofer Profesional"],
        "skills": [
            ("licencia profesional", ""), ("conocimiento de AMBA", ""), ("entrega de mercadería", ""), ("hoja de ruta", ""),
            ("cobranza", ""), ("cuidado del vehículo", ""), ("GPS", ""), ("puntualidad", ""),
            ("carga de camioneta", ""), ("disponibilidad horaria", ""),
        ],
        "tareas": [
            "realizar entregas según hoja de ruta",
            "cobrar y rendir a clientes",
            "cargar y descargar la camioneta",
            "controlar el estado del vehículo",
            "coordinar entregas con el depósito",
        ],
        "estudios": ["Secundario completo", "Licencia profesional de conducir"],
    },
    "analista_logistica": {
        "rubro": "logistica",
        "nombre": "Analista de Logística",
        "titulos": ["Analista de Logística", "Analista de Supply Chain", "Planificador/a de Distribución", "Analista de Abastecimiento"],
        "skills": [
            ("Excel avanzado", ""), ("SAP", ""), ("planificación de distribución", ""), ("indicadores logísticos", ""),
            ("gestión de stock", ""), ("negociación con transportes", ""), ("comercio exterior", ""), ("WMS", ""),
            ("Power BI", ""), ("ruteo", ""),
        ],
        "tareas": [
            "planificar la distribución semanal",
            "controlar indicadores de nivel de servicio",
            "coordinar con transportes tercerizados",
            "analizar niveles de stock en SAP",
            "preparar reportes logísticos para la gerencia",
        ],
        "estudios": ["Lic. en Logística", "Ing. Industrial (en curso)", "Tecnicatura en Logística"],
    },
    # ── Administración ────────────────────────────────────────────
    "asistente_admin": {
        "rubro": "administracion",
        "nombre": "Asistente Administrativo/a",
        "titulos": ["Asistente Administrativo/a", "Auxiliar Administrativo", "Administrativo/a", "Asistente de Oficina"],
        "skills": [
            ("Excel", ""), ("facturación", ""), ("archivo y documentación", ""), ("atención a proveedores", ""),
            ("pagos y cobranzas", ""), ("Tango Gestión", ""), ("manejo de agenda", ""), ("redacción", ""),
            ("conciliaciones bancarias", ""), ("Word", ""),
        ],
        "tareas": [
            "emitir facturas y notas de crédito",
            "registrar pagos a proveedores",
            "organizar el archivo de documentación",
            "atender llamados y correos de proveedores",
            "colaborar con conciliaciones bancarias",
        ],
        "estudios": ["Perito Mercantil", "Lic. en Administración (en curso)"],
    },
    "analista_contable": {
        "rubro": "administracion",
        "nombre": "Analista Contable",
        "titulos": ["Analista Contable", "Contador/a Jr", "Analista de Cuentas a Pagar", "Asistente Contable"],
        "skills": [
            ("asientos contables", ""), ("conciliaciones bancarias", ""), ("impuestos", ""), ("balances", ""),
            ("Excel avanzado", ""), ("Tango Gestión", ""), ("SAP", ""), ("IVA e Ingresos Brutos", ""),
            ("cierres mensuales", ""), ("cuentas a pagar", ""),
        ],
        "tareas": [
            "registrar asientos contables",
            "liquidar IVA e Ingresos Brutos",
            "preparar conciliaciones bancarias",
            "participar en cierres mensuales",
            "colaborar con la preparación del balance",
        ],
        "estudios": ["Contador Público (en curso)", "Contador Público"],
    },
    "liquidador_sueldos": {
        "rubro": "administracion",
        "nombre": "Liquidador/a de Sueldos",
        "titulos": ["Liquidador/a de Sueldos", "Analista de Liquidación de Haberes", "Analista de Payroll", "Asistente de RRHH - Liquidación"],
        "skills": [
            ("liquidación de sueldos", ""), ("convenios colectivos", ""), ("F931", ""), ("cargas sociales", ""),
            ("Excel avanzado", ""), ("Bejerman", ""), ("legajos", ""), ("SICOSS", ""),
            ("vacaciones y licencias", ""), ("libro de sueldos digital", ""),
        ],
        "tareas": [
            "liquidar sueldos mensuales y quincenales",
            "presentar el F931",
            "aplicar convenios colectivos",
            "mantener legajos del personal",
            "calcular vacaciones, licencias y finales",
        ],
        "estudios": ["Lic. en RRHH (en curso)", "Curso de Liquidación de Sueldos"],
    },
    # ── Gastronomía ───────────────────────────────────────────────
    "cocinero": {
        "rubro": "gastronomia",
        "nombre": "Cocinero/a",
        "titulos": ["Cocinero/a", "Cocinero de Línea", "Ayudante de Cocina", "Cocinero/a para Restaurante"],
        "skills": [
            ("cocina a la plancha", ""), ("mise en place", ""), ("manipulación de alimentos", ""), ("parrilla", ""),
            ("pastas", ""), ("control de mercadería", ""), ("trabajo bajo presión", ""), ("carnet de manipulador", ""),
            ("pastelería básica", ""), ("limpieza de cocina", ""),
        ],
        "tareas": [
            "preparar la mise en place del servicio",
            "cocinar platos a la plancha y parrilla",
            "controlar la mercadería que ingresa",
            "mantener la cocina limpia y ordenada",
            "respetar normas de manipulación de alimentos",
        ],
        "estudios": ["Cocinero Profesional (IGA)", "Curso de Cocina", "Secundario completo"],
    },
    "mozo": {
        "rubro": "gastronomia",
        "nombre": "Mozo/a",
        "titulos": ["Mozo/a", "Camarero/a", "Mozo para Restaurante", "Personal de Salón"],
        "skills": [
            ("atención en salón", ""), ("toma de pedidos", ""), ("manejo de bandeja", ""), ("cobro con posnet", ""),
            ("buena presencia", ""), ("conocimiento de vinos", ""), ("trabajo en equipo", ""), ("disponibilidad fines de semana", ""),
            ("armado de mesas", ""), ("inglés básico", ""),
        ],
        "tareas": [
            "tomar pedidos y servir mesas",
            "recomendar platos y vinos",
            "cobrar con efectivo y posnet",
            "armar y desarmar el salón",
            "atender a turistas en inglés básico",
        ],
        "estudios": ["Secundario completo", "Curso de Sommelier básico"],
    },
    "encargado_local": {
        "rubro": "gastronomia",
        "nombre": "Encargado/a de Local Gastronómico",
        "titulos": ["Encargado/a de Local", "Encargado de Turno", "Supervisor/a de Restaurante", "Gerente de Local"],
        "skills": [
            ("manejo de personal", ""), ("control de costos", ""), ("arqueo de caja", ""), ("pedidos a proveedores", ""),
            ("armado de turnos", ""), ("atención de reclamos", ""), ("normas bromatológicas", ""), ("Excel", ""),
            ("apertura y cierre", ""), ("capacitación de personal", ""),
        ],
        "tareas": [
            "coordinar al equipo de salón y cocina",
            "armar los cronogramas de turnos",
            "hacer pedidos a proveedores",
            "controlar costos y arqueos de caja",
            "abrir y cerrar el local",
        ],
        "estudios": ["Lic. en Gastronomía (en curso)", "Secundario completo"],
    },
    # ── Marketing ─────────────────────────────────────────────────
    "community_manager": {
        "rubro": "marketing",
        "nombre": "Community Manager",
        "titulos": ["Community Manager", "Social Media Manager", "Responsable de Redes Sociales", "Content Creator"],
        "titulos_en": ["Social Media Manager", "Community Manager", "Content Creator"],
        "skills": [
            ("Instagram", "Instagram"), ("calendario de contenidos", "content calendar"), ("copywriting", "copywriting"),
            ("Canva", "Canva"), ("Meta Business Suite", "Meta Business Suite"), ("TikTok", "TikTok"),
            ("métricas de redes", "social media analytics"), ("edición de video", "video editing"),
            ("atención de comunidad", "community engagement"), ("pauta en Meta Ads", "Meta Ads"),
        ],
        "tareas": [
            "planificar el calendario de contenidos",
            "redactar copys para Instagram y TikTok",
            "responder mensajes y comentarios",
            "medir el rendimiento de las publicaciones",
            "editar reels y videos cortos",
        ],
        "estudios": ["Lic. en Comunicación (en curso)", "Curso de Community Manager"],
    },
    "disenador_grafico": {
        "rubro": "marketing",
        "nombre": "Diseñador/a Gráfico/a",
        "titulos": ["Diseñador/a Gráfico/a", "Diseñador Gráfico Jr", "Diseñador/a de Piezas Digitales", "Diseñador Visual"],
        "titulos_en": ["Graphic Designer", "Visual Designer", "Digital Designer"],
        "skills": [
            ("Illustrator", "Illustrator"), ("Photoshop", "Photoshop"), ("identidad de marca", "brand identity"),
            ("diseño editorial", "editorial design"), ("Figma", "Figma"), ("piezas para redes", "social media assets"),
            ("After Effects", "After Effects"), ("tipografía", "typography"), ("portfolio", "portfolio"),
            ("InDesign", "InDesign"),
        ],
        "tareas": [
            "diseñar piezas para redes y campañas",
            "desarrollar identidades de marca",
            "maquetar catálogos y folletos",
            "preparar archivos para imprenta",
            "animar piezas cortas",
        ],
        "estudios": ["Diseño Gráfico (UBA)", "Diseño Gráfico (en curso)"],
    },
    "analista_marketing": {
        "rubro": "marketing",
        "nombre": "Analista de Marketing Digital",
        "titulos": ["Analista de Marketing Digital", "Analista de Performance", "Especialista en Google Ads", "Analista SEM/SEO"],
        "titulos_en": ["Digital Marketing Analyst", "Performance Marketing Analyst", "Paid Media Specialist"],
        "skills": [
            ("Google Ads", "Google Ads"), ("Google Analytics", "Google Analytics"), ("SEO", "SEO"),
            ("Meta Ads", "Meta Ads"), ("Excel", "Excel"), ("email marketing", "email marketing"),
            ("Looker Studio", "Looker Studio"), ("tests A/B", "A/B testing"), ("presupuesto de pauta", "ad budget management"),
            ("SQL", "SQL"),
        ],
        "tareas": [
            "gestionar campañas en Google Ads y Meta Ads",
            "analizar el tráfico en Google Analytics",
            "armar reportes de performance",
            "optimizar el presupuesto de pauta",
            "diseñar tests A/B de landings",
        ],
        "estudios": ["Lic. en Marketing", "Lic. en Publicidad (en curso)"],
    },
    # ── Industria ─────────────────────────────────────────────────
    "tecnico_mantenimiento": {
        "rubro": "industria",
        "nombre": "Técnico/a de Mantenimiento",
        "titulos": ["Técnico/a de Mantenimiento", "Mecánico de Mantenimiento", "Electromecánico/a", "Técnico de Mantenimiento Industrial"],
        "skills": [
            ("mantenimiento preventivo", ""), ("electricidad industrial", ""), ("neumática", ""), ("hidráulica", ""),
            ("lectura de planos", ""), ("PLC", ""), ("soldadura", ""), ("tornería", ""),
            ("mantenimiento correctivo", ""), ("trabajo por turnos rotativos", ""),
        ],
        "tareas": [
            "realizar mantenimiento preventivo de máquinas",
            "diagnosticar fallas eléctricas y mecánicas",
            "interpretar planos eléctricos",
            "reparar sistemas neumáticos e hidráulicos",
            "registrar intervenciones en órdenes de trabajo",
        ],
        "estudios": ["Técnico Electromecánico", "Técnico Mecánico"],
    },
    "operario_produccion": {
        "rubro": "industria",
        "nombre": "Operario/a de Producción",
        "titulos": ["Operario/a de Producción", "Operario de Línea", "Operario/a Industrial", "Operador de Máquinas"],
        "skills": [
            ("operación de máquinas", ""), ("trabajo en línea", ""), ("control visual de calidad", ""), ("BPM", ""),
            ("uso de EPP", ""), ("turnos rotativos", ""), ("embalaje", ""), ("5S", ""),
            ("registro de producción", ""), ("orden y limpieza", ""),
        ],
        "tareas": [
            "operar máquinas de la línea de producción",
            "controlar visualmente la calidad del producto",
            "embalar y paletizar producto terminado",
            "registrar la producción del turno",
            "aplicar BPM y normas de seguridad",
        ],
        "estudios": ["Secundario completo", "Secundario técnico"],
    },
    "supervisor_calidad": {
        "rubro": "industria",
        "nombre": "Supervisor/a de Calidad",
        "titulos": ["Supervisor/a de Calidad", "Analista de Calidad", "Inspector de Calidad", "Responsable de Aseguramiento de Calidad"],
        "skills": [
            ("ISO 9001", ""), ("auditorías internas", ""), ("control estadístico de procesos", ""), ("no conformidades", ""),
            ("BPM", ""), ("análisis de causa raíz", ""), ("Excel avanzado", ""), ("procedimientos", ""),
            ("indicadores de calidad", ""), ("liderazgo de equipos", ""),
        ],
        "tareas": [
            "realizar auditorías internas",
            "gestionar no conformidades",
            "aplicar control estadístico de procesos",
            "redactar procedimientos de calidad",
            "seguir indicadores de calidad de planta",
        ],
        "estudios": ["Ing. Industrial", "Ing. Química (en curso)", "Lic. en Tecnología de Alimentos"],
    },
}

RUBROS = sorted({r["rubro"] for r in ROLES.values()})
RUBRO_LABEL = {
    "tecnologia": "Tecnología", "ventas": "Ventas y atención", "salud": "Salud",
    "logistica": "Logística", "administracion": "Administración", "gastronomia": "Gastronomía",
    "marketing": "Marketing", "industria": "Industria",
}

# Pares de roles de DISTINTO rubro que un reclutador consideraría
# relacionados (comparten bastante del trabajo real). Para esos, la
# etiqueta es 1 ("relacionado") en vez de 0. Es una lista corta a
# propósito: el resto de cruces entre rubros es 0.
ROLES_AFINES = {
    frozenset({"analista_datos", "analista_marketing"}),
    frozenset({"analista_datos", "analista_logistica"}),
    frozenset({"analista_contable", "liquidador_sueldos"}),  # mismo rubro, ya da 1
    frozenset({"atencion_cliente", "admin_salud"}),
    frozenset({"vendedor_salon", "mozo"}),
    frozenset({"community_manager", "disenador_grafico"}),  # mismo rubro, ya da 1
}

# Trampas: ofertas de un rol, pero con el vocabulario de OTRO rubro metido
# en el texto. Un buen sistema tiene que entender que el puesto real es el
# del rol, no dejarse llevar por las palabras clave.
TRAMPAS = [
    ("ejecutivo_comercial", "tecnologia",
     "Vendedor/a de Software (SaaS)",
     "Empresa de software de datos busca vendedor/a. Nuestro producto conecta SQL, Python y Power BI; "
     "no necesitás programar, pero sí entender el lenguaje de clientes técnicos (APIs, dashboards, ETL)."),
    ("atencion_cliente", "tecnologia",
     "Atención al Cliente para Fintech",
     "Fintech con stack Python + AWS busca agente para atención a usuarios de la app. "
     "Trabajarás junto al equipo de desarrolladores reportando incidencias de la API."),
    ("asistente_admin", "tecnologia",
     "Administrativo/a para Software Factory",
     "Software factory (Java, Python, Docker, Kubernetes) busca administrativo/a para facturación, "
     "pagos a proveedores y gestión documental del equipo de desarrollo."),
    ("vendedor_salon", "salud",
     "Vendedor/a para Farmacia y Perfumería",
     "Farmacia busca vendedor/a para el salón de perfumería. No se requiere título de enfermería ni matrícula; "
     "valoramos trato con pacientes y conocimientos básicos de medicación de venta libre."),
    ("cocinero", "salud",
     "Cocinero/a para Clínica (servicio de alimentación)",
     "Clínica de internación busca cocinero/a para el servicio de alimentación de pacientes. "
     "Trabajo junto a nutricionistas, respetando dietas y normas de bioseguridad hospitalaria."),
    ("operario_produccion", "logistica",
     "Operario/a de Producción en Centro Logístico",
     "Planta de envasado dentro de un centro logístico busca operario/a de línea. "
     "Convivirás con autoelevadores, picking y WMS, pero el puesto es en la línea de envasado."),
    ("chofer_reparto", "gastronomia",
     "Chofer para Cadena de Restaurantes",
     "Cadena de restaurantes busca chofer para distribuir mercadería entre locales. "
     "Contacto con cocineros y encargados de local; manipulación de alimentos envasados."),
    ("mozo", "ventas",
     "Mozo/a con orientación comercial (objetivos de venta)",
     "Restaurante busca mozo/a con perfil vendedor: objetivos de venta de vinos, fidelización de clientes, "
     "atención al cliente y manejo de caja."),
    ("community_manager", "tecnologia",
     "Community Manager para Startup de IA",
     "Startup de inteligencia artificial (LLMs, Python, machine learning) busca community manager para "
     "LinkedIn e Instagram. No es un puesto técnico: buscamos copy y comunidad."),
    ("analista_contable", "tecnologia",
     "Analista Contable para empresa de tecnología",
     "Empresa de tecnología busca analista contable. Usamos SAP y Power BI para reporting financiero; "
     "el puesto es de contabilidad: asientos, conciliaciones e impuestos."),
    ("operario_deposito", "industria",
     "Operario de Depósito en Planta Industrial",
     "Planta metalúrgica busca operario para depósito de materia prima: carga y descarga, picking e inventario. "
     "No es puesto de mantenimiento ni de línea de producción."),
    ("tecnico_mantenimiento", "tecnologia",
     "Técnico/a de Mantenimiento para Data Center",
     "Data center busca técnico electromecánico para mantenimiento de grupos electrógenos, UPS y aire "
     "acondicionado. No es soporte IT ni administración de servidores."),
    ("admin_salud", "administracion",
     "Administrativo/a de Facturación para Clínica",
     "Clínica busca administrativo/a: facturación a obras sociales, autorizaciones y turnos. "
     "Manejo de Excel y facturación; se valora experiencia administrativa general."),
    ("encargado_local", "ventas",
     "Encargado/a de Heladería",
     "Heladería busca encargado/a de turno: manejo de personal, caja, atención al cliente y objetivos de venta "
     "del local."),
    ("liquidador_sueldos", "tecnologia",
     "Analista de Payroll para empresa de software",
     "Empresa de software (Python, React, AWS) busca analista de liquidación de haberes para su equipo de "
     "People. Puesto 100% administrativo."),
    ("disenador_grafico", "tecnologia",
     "Diseñador/a Gráfico/a para equipo de producto digital",
     "Equipo de desarrollo web (React, Next.js) busca diseñador/a gráfico/a para piezas de marketing. "
     "No es UX ni front-end: es diseño de piezas."),
]

NOMBRES = ["Lucía", "Martín", "Sofía", "Tomás", "Valentina", "Joaquín", "Camila", "Matías", "Julieta", "Nicolás",
           "Agustina", "Facundo", "Florencia", "Santiago", "Milagros", "Lautaro", "Carolina", "Federico",
           "Micaela", "Gonzalo", "Rocío", "Ezequiel", "Antonella", "Franco", "Belén", "Ramiro", "Paula", "Iván"]
APELLIDOS = ["González", "Rodríguez", "Fernández", "López", "Martínez", "Pérez", "Gómez", "Díaz", "Sánchez",
             "Romero", "Sosa", "Álvarez", "Torres", "Ruiz", "Ramírez", "Flores", "Benítez", "Acosta", "Medina",
             "Herrera", "Suárez", "Aguirre", "Giménez", "Molina", "Castro", "Ortiz"]
EMPRESAS = ["Grupo Austral", "Distribuidora Del Plata", "Sur Servicios", "Nexo SA", "Andes Corp", "Rivera & Asociados",
            "Pampa Holdings", "Bahía Group", "Lumen SRL", "Cordillera SA", "Delta Soluciones", "Horizonte SA",
            "Puerto Norte", "Alto Valle SRL", "Ceibo Group", "Litoral SA", "Mirador SRL", "Vértice SA"]
ZONAS = ["CABA", "Zona Norte (GBA)", "Zona Sur (GBA)", "Zona Oeste (GBA)", "Rosario", "Córdoba", "La Plata"]
BENEFICIOS = [
    "Ofrecemos obra social para vos y tu grupo familiar.",
    "Buen clima laboral y posibilidades reales de crecimiento.",
    "Capacitación a cargo de la empresa.",
    "Descuentos en productos y comedor en planta.",
    "Bono anual por desempeño.",
    "Horario de 9 a 18 hs de lunes a viernes.",
    "Incorporación inmediata, relación de dependencia.",
]
