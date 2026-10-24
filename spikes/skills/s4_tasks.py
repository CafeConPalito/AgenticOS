"""Phase 17 · spike S4 data: own skills (as an Agentic OS user would write them) and test tasks.

Each task is what the selector sees: title, description, stage and agent role. `expected` lists
the skill names that count as a hit (near-duplicates of the same family are accepted only when
the task does not single one out). Tasks with `expected = []` have no fitting skill: they
calibrate the threshold (nothing should be offered).
"""

from __future__ import annotations

OWN_SKILLS = [
    {
        "name": "migraciones-alembic",
        "description": "Cómo escribir y revisar migraciones de Alembic con SQLAlchemy: "
        "autogenerate, revisar el script, datos existentes, downgrade y migraciones en SQLite "
        "con batch_alter_table. Úsala al cambiar modelos o el esquema de la base de datos.",
    },
    {
        "name": "propuesta-comercial",
        "description": "Redactar propuestas comerciales y presupuestos para clientes: "
        "estructura, alcance, precios, plazos y condiciones. Úsala cuando haya que preparar una "
        "oferta o responder a una petición de presupuesto.",
    },
    {
        "name": "notas-de-version",
        "description": "Escribir notas de versión y changelogs a partir de los commits y de "
        "las tareas cerradas, agrupadas por novedades, mejoras y correcciones, en español.",
    },
    {
        "name": "pruebas-e2e-playwright",
        "description": "Escribir y depurar pruebas de extremo a extremo con Playwright: "
        "selectores estables, esperas, fixtures y capturas al fallar.",
    },
    {
        "name": "atencion-cliente",
        "description": "Responder a correos e incidencias de clientes con un tono cercano y "
        "profesional: entender el problema, pedir datos que falten y proponer solución.",
    },
    {
        "name": "seguridad-owasp",
        "description": "Revisar una aplicación web en busca de vulnerabilidades OWASP Top 10: "
        "inyección, XSS, autenticación rota, control de acceso y secretos en el código.",
    },
]

# (title, description, stage, role, expected)
TASKS = [
    # --- own skills, Spanish
    (
        "Añadir columna 'telefono' a clientes",
        "Hay que añadir el campo teléfono al modelo "
        "Cliente y crear la migración de la base de datos sin perder datos.",
        "Desarrollo",
        "Desarrollador backend",
        ["migraciones-alembic"],
    ),
    (
        "Renombrar la tabla pedidos",
        "Renombra la tabla pedidos a orders en SQLite y deja el downgrade funcionando.",
        "Desarrollo",
        "Desarrollador",
        ["migraciones-alembic"],
    ),
    (
        "Presupuesto para Ferretería López",
        "El cliente pide un presupuesto para una tienda "
        "online con pasarela de pago. Prepara la oferta con alcance, precio y plazos.",
        "Redacción",
        "Comercial",
        ["propuesta-comercial"],
    ),
    (
        "Oferta de mantenimiento anual",
        "Redacta una propuesta de contrato de mantenimiento "
        "para la clínica dental con tres niveles de servicio.",
        "Redacción",
        "Comercial",
        ["propuesta-comercial"],
    ),
    (
        "Changelog de la versión 2.3",
        "Resume en el changelog lo que entra en la 2.3 a partir de los commits desde la v2.2.",
        "Publicación",
        "Redactor técnico",
        ["notas-de-version"],
    ),
    (
        "Notas de la release de octubre",
        "Escribe las notas de versión para los usuarios con "
        "las novedades y correcciones de este mes.",
        "Publicación",
        "Redactor",
        ["notas-de-version"],
    ),
    (
        "Test e2e del login",
        "Crea una prueba end to end que entre con usuario y contraseña y "
        "compruebe que llega al panel. Usamos Playwright.",
        "QA",
        "QA",
        ["pruebas-e2e-playwright"],
    ),
    (
        "El test de checkout falla a veces",
        "La prueba de Playwright del carrito es inestable: "
        "a veces no encuentra el botón de pagar. Arréglala.",
        "QA",
        "QA",
        ["pruebas-e2e-playwright", "diagnosing-bugs"],
    ),
    (
        "Responder a la queja de María",
        "Una clienta dice que su pedido llegó roto y pide el reembolso. Contéstale.",
        "Soporte",
        "Atención al cliente",
        ["atencion-cliente"],
    ),
    (
        "Incidencia: no puedo iniciar sesión",
        "Un usuario escribe que no puede entrar desde ayer. Respóndele pidiendo lo que falte.",
        "Soporte",
        "Soporte",
        ["atencion-cliente"],
    ),
    (
        "Auditoría de seguridad de la API",
        "Revisa la API en busca de inyección SQL, XSS y "
        "problemas de autenticación antes de salir a producción.",
        "QA",
        "Seguridad",
        ["seguridad-owasp"],
    ),
    (
        "¿Hay secretos en el repo?",
        "Comprueba que no hay claves ni contraseñas en el código y "
        "que el control de acceso de los endpoints de admin es correcto.",
        "Revisión",
        "Seguridad",
        ["seguridad-owasp"],
    ),
    # --- registry skills, Spanish tasks (cross-language)
    (
        "Revisar la rama de la tarea T-142",
        "Revisa los cambios de la rama frente a main: que "
        "sigan los estándares del repo y lo que pedía la tarea.",
        "Revisión de código",
        "Revisor",
        ["code-review"],
    ),
    (
        "Error intermitente en producción",
        "El endpoint de facturas a veces tarda 30 s y no sabemos por qué. Encuentra la causa.",
        "Desarrollo",
        "Desarrollador",
        ["diagnosing-bugs"],
    ),
    (
        "Nueva pantalla de onboarding",
        "Diseña e implementa una pantalla de bienvenida con un "
        "estilo visual cuidado y distinto, no genérico.",
        "Desarrollo",
        "Frontend",
        ["frontend-design", "web-design-guidelines"],
    ),
    (
        "Revisar la accesibilidad de la UI",
        "Comprueba que el formulario de alta cumple las "
        "guías de interfaz web: foco, contraste, etiquetas.",
        "QA",
        "QA",
        ["web-design-guidelines"],
    ),
    (
        "Implementar con TDD el cálculo de IVA",
        "Haz la función de IVA escribiendo primero los tests en rojo y luego el código.",
        "Desarrollo",
        "Desarrollador",
        ["tdd"],
    ),
    (
        "Prepara el traspaso a otro agente",
        "Resume esta conversación en un documento para que otro agente pueda seguir el trabajo.",
        "Desarrollo",
        "Desarrollador",
        ["handoff"],
    ),
    (
        "Desplegar la app en Azure",
        "La app ya está preparada con azd; despliégala en Azure.",
        "Despliegue",
        "DevOps",
        ["azure-deploy"],
    ),
    (
        "Crear un clúster AKS",
        "Necesitamos un clúster de Kubernetes en Azure para producción, "
        "con su configuración de red.",
        "Infraestructura",
        "DevOps",
        ["azure-kubernetes"],
    ),
    (
        "Consultar logs en Kusto",
        "Saca con KQL las peticiones fallidas de la última semana del Data Explorer.",
        "Análisis",
        "Analista",
        ["azure-kusto"],
    ),
    (
        "Subir a Prisma 7",
        "Migra el proyecto de Prisma ORM 6 a 7 con todos los cambios que rompen.",
        "Desarrollo",
        "Desarrollador",
        ["prisma-upgrade-v7"],
    ),
    (
        "Consulta con filtros en Prisma",
        "Escribe la consulta de Prisma Client que filtra pedidos por fecha e incluye el cliente.",
        "Desarrollo",
        "Desarrollador",
        ["prisma-client-api"],
    ),
    (
        "Optimizar consultas de Postgres",
        "Las consultas a Postgres en Supabase van lentas; revisa índices y buenas prácticas.",
        "Desarrollo",
        "Backend",
        ["supabase-postgres-best-practices"],
    ),
    (
        "Vídeo promocional con Remotion",
        "Crea un vídeo nuevo de 30 segundos con Remotion para presentar el producto.",
        "Contenido",
        "Creativo",
        ["remotion-create", "remotion-best-practices"],
    ),
    (
        "Subtítulos animados en el vídeo",
        "Transcribe el audio y añade subtítulos animados al vídeo de Remotion.",
        "Contenido",
        "Creativo",
        ["remotion-captions"],
    ),
    (
        "Exportar el vídeo final",
        "Renderiza y exporta el vídeo de Remotion a MP4.",
        "Contenido",
        "Creativo",
        ["remotion-render"],
    ),
    (
        "Mejorar el rendimiento de la web en Next.js",
        "La página de producto en Next.js tarda en cargar; aplica optimizaciones de React.",
        "Desarrollo",
        "Frontend",
        ["vercel-react-best-practices"],
    ),
    (
        "App móvil con Expo",
        "Construye la pantalla de pedidos de la app React Native con Expo, que vaya fluida.",
        "Desarrollo",
        "Móvil",
        ["vercel-react-native-skills", "design-mobile-apps"],
    ),
    (
        "Rellenar el formulario de la web del proveedor",
        "Entra en la web del proveedor, rellena el formulario de pedido y descarga la factura.",
        "Compras",
        "Asistente",
        ["agent-browser"],
    ),
    (
        "Generar imágenes para el blog",
        "Crea tres ilustraciones con IA para el artículo del blog.",
        "Contenido",
        "Creativo",
        ["ai-image-generation"],
    ),
    (
        "Publicar en X el lanzamiento",
        "Publica un tuit anunciando la versión nueva.",
        "Marketing",
        "Community manager",
        ["twitter-automation"],
    ),
    (
        "Registrar la app en Entra ID",
        "Configura el inicio de sesión con Microsoft (OAuth y MSAL) para la intranet.",
        "Desarrollo",
        "Backend",
        ["entra-app-registration"],
    ),
    (
        "¿Hay alguna skill para hacer facturas?",
        "Busca si existe alguna skill que ayude con facturación electrónica.",
        "Desarrollo",
        "Asistente",
        ["find-skills"],
    ),
    # --- registry skills, English tasks
    (
        "Review PR #88",
        "Review the changes on this branch since main against the repo's standards and the spec.",
        "Code review",
        "Reviewer",
        ["code-review"],
    ),
    (
        "Flaky memory leak",
        "The worker's memory grows until it is killed; diagnose the leak.",
        "Development",
        "Developer",
        ["diagnosing-bugs"],
    ),
    (
        "Design the module boundaries",
        "Help me design a deep module interface for the payments package.",
        "Design",
        "Architect",
        ["codebase-design", "improve-codebase-architecture"],
    ),
    (
        "Stress-test my plan",
        "Grill me about my plan to migrate to microservices.",
        "Planning",
        "Architect",
        ["grill-me", "grilling", "grill-with-docs"],
    ),
    (
        "Quick prototype of the search UX",
        "Build a throwaway prototype to check whether instant search feels right.",
        "Design",
        "Developer",
        ["prototype"],
    ),
    (
        "Instrument with Application Insights",
        "Add telemetry to the web app with Azure Application Insights.",
        "Development",
        "Developer",
        ["appinsights-instrumentation"],
    ),
    (
        "Upload files to Blob Storage",
        "Store the user uploads in Azure Blob Storage.",
        "Development",
        "Backend",
        ["azure-storage"],
    ),
    (
        "Service Bus messages are lost",
        "Troubleshoot why messages sent with the Azure Service Bus SDK never arrive.",
        "Development",
        "Backend",
        ["azure-messaging"],
    ),
    (
        "Set up a Prisma Postgres database",
        "Get a Prisma Postgres database and connect the app to it.",
        "Development",
        "Backend",
        ["prisma-postgres-setup", "prisma-postgres"],
    ),
    (
        "View transitions between pages",
        "Add smooth native animations between routes with React's View Transition API.",
        "Development",
        "Frontend",
        ["vercel-react-view-transitions"],
    ),
    (
        "Avatar video for the course",
        "Make a talking head avatar video that reads the lesson script.",
        "Content",
        "Creative",
        ["ai-avatar-video"],
    ),
    (
        "Find Reddit threads to answer",
        "Find Reddit threads where people ask for a tool like ours and draft helpful replies.",
        "Marketing",
        "Growth",
        ["reddit-automation"],
    ),
    (
        "HyperFrames intro video",
        "Make a short animated intro video with HyperFrames.",
        "Content",
        "Creative",
        ["hyperframes", "hyperframes-animation", "hyperframes-core"],
    ),
    (
        "Triage the open issues",
        "Go through the open issues, label them and move them to the right triage state.",
        "Triage",
        "Maintainer",
        ["triage"],
    ),
    # --- no fitting skill (threshold calibration)
    (
        "Traducir el manual al francés",
        "Traduce el manual de usuario al francés.",
        "Redacción",
        "Traductor",
        [],
    ),
    (
        "Calcular las nóminas de octubre",
        "Calcula las nóminas con las horas extra.",
        "Administración",
        "Administrativo",
        [],
    ),
    (
        "Reservar el viaje a Bilbao",
        "Busca vuelo y hotel para la feria del día 12.",
        "Viajes",
        "Asistente",
        [],
    ),
    (
        "Write a haiku about autumn",
        "Write a short haiku for the newsletter.",
        "Content",
        "Writer",
        [],
    ),
    (
        "Ordenar el almacén",
        "Haz el inventario de las cajas del almacén y propón un orden.",
        "Logística",
        "Operario",
        [],
    ),
    (
        "Plan the team offsite",
        "Plan the agenda for a two-day team offsite.",
        "Planning",
        "Manager",
        [],
    ),
    (
        "Responder a la Agencia Tributaria",
        "Prepara la respuesta al requerimiento de Hacienda sobre el IVA del segundo trimestre.",
        "Administración",
        "Gestor",
        [],
    ),
    (
        "Corregir la ortografía del folleto",
        "Revisa la ortografía del folleto de la feria.",
        "Redacción",
        "Redactor",
        [],
    ),
    (
        "Excel de gastos",
        "Pasa los tickets de gastos a una hoja de cálculo por categorías.",
        "Administración",
        "Administrativo",
        [],
    ),
    (
        "Mover el servidor de correo",
        "Migra las cuentas de correo del hosting viejo al nuevo.",
        "Sistemas",
        "Sistemas",
        [],
    ),
]
