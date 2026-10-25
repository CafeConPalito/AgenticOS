"""A fake Agentic OS installation for spikes S3 (quality) and S4 (size of tool answers).

`installation(scale)` returns the catalog the Architect's tools read: CLIs with accounts and
models, teams, agents, skills, knowledge documents, MCP connections, registry suggestions,
templates and projects with their pipelines. With `scale > 0`, filler skills, documents and
connections are added (S4: 200 skills, 300 documents, 50 connections).
"""

from __future__ import annotations

CLIS = [
    {
        "cli": "claude",
        "accounts": [
            {"id": "acc-personal", "name": "personal"},
            {"id": "acc-empresa", "name": "empresa"},
        ],
        "models": ["haiku", "sonnet", "opus"],
    },
    {
        "cli": "agy",
        "accounts": [{"id": "acc-trabajo", "name": "trabajo"}],
        "models": ["gemini-3.8-flash-low", "gemini-3.8-flash-high", "gemini-3.8-pro"],
    },
]

TOOLS = ["read", "edit", "terminal", "git", "web", "browser"]

TEAMS = [
    {"name": "Desarrollo", "description": "Equipo que construye la tienda online."},
    {"name": "Marketing", "description": "Contenidos y campañas."},
]

AGENTS = [
    {
        "name": "Dev",
        "role": "Desarrollador",
        "team": "Desarrollo",
        "cli": "claude",
        "model": "sonnet",
        "permission_mode": "autonomous",
        "allowed_tools": ["read", "edit", "terminal", "git"],
        "skills": [
            {"name": "commits-convencionales", "mode": "always"},
            {"name": "api-rest-diseno", "mode": "auto"},
        ],
        "connections": [{"name": "github"}],
        "instructions": "Eres el desarrollador del equipo. Lee los requisitos y el código antes de cambiar nada. Escribe tests.",
    },
    {
        "name": "QA",
        "role": "QA",
        "team": "Desarrollo",
        "cli": "agy",
        "model": "gemini-3.8-flash-high",
        "permission_mode": "restricted",
        "allowed_tools": ["read", "terminal", "git", "browser"],
        "skills": [{"name": "tests-e2e-playwright", "mode": "auto"}],
        "connections": [{"name": "playwright"}],
        "instructions": "Eres el responsable de calidad. Comprueba cada criterio de aceptación. No corrijas el código.",
    },
    {
        "name": "Analista",
        "role": "Analista de requisitos",
        "team": "Desarrollo",
        "cli": "claude",
        "model": "sonnet",
        "permission_mode": "restricted",
        "allowed_tools": ["read", "edit", "web"],
        "skills": [],
        "connections": [],
        "instructions": "Conviertes peticiones en requisitos claros con criterios de aceptación.",
    },
]

SKILLS = [
    ("tono-de-marca", "Guía de tono y estilo de la marca para cualquier texto público."),
    ("seo-basico", "Títulos, metadescripciones, encabezados y enlaces internos para posts."),
    ("revision-codigo", "Checklist para revisar un cambio de código antes de aprobarlo."),
    ("tests-e2e-playwright", "Cómo escribir y ejecutar tests end-to-end con Playwright."),
    ("propuestas-comerciales", "Plantilla de propuesta: resumen, alcance, plazos y precio."),
    ("glosario-producto", "Términos del producto y cómo se escriben."),
    ("guia-estilo-ingles", "Estilo para textos en inglés: ortografía americana, tono directo."),
    ("commits-convencionales", "Mensajes de commit con Conventional Commits."),
    ("seguridad-owasp", "Revisión de seguridad con el OWASP Top 10."),
    ("redaccion-tecnica", "Documentación técnica clara: tareas, referencia y conceptos."),
    ("api-rest-diseno", "Convenciones para diseñar APIs REST."),
    ("accesibilidad-web", "Pautas WCAG 2.2 para revisar interfaces."),
]

DOCS = [
    ("doc-marca", "Guía de marca 2026", "general", "", "guia-de-marca.pdf"),
    ("doc-catalogo", "Catálogo de productos", "general", "", "catalogo-productos.xlsx"),
    ("doc-tarifas", "Tarifas 2026", "general", "", "tarifas-2026.pdf"),
    (
        "doc-arquitectura",
        "Arquitectura de la tienda",
        "project",
        "Tienda online",
        "docs/arquitectura.md",
    ),
    ("doc-api", "Manual de la API", "project", "Tienda online", "manual-api.pdf"),
    (
        "doc-calendario",
        "Calendario editorial",
        "project",
        "Blog corporativo",
        "calendario-editorial.xlsx",
    ),
]

CONNECTIONS = [
    (
        "github",
        "GitHub: issues, pull requests y código.",
        ["get_issue", "list_issues", "create_pull_request", "get_file_contents"],
    ),
    (
        "playwright",
        "Navegador controlado por Playwright.",
        ["browser_navigate", "browser_click", "browser_snapshot"],
    ),
    (
        "postgres-tienda",
        "Base de datos PostgreSQL de la tienda.",
        ["query", "list_tables", "describe_table"],
    ),
    ("fetch", "Descarga una URL como Markdown.", ["fetch"]),
    (
        "context7",
        "Documentación actualizada de librerías.",
        ["resolve_library_id", "get_library_docs"],
    ),
]

REGISTRY = [
    ("notion", "Notion oficial (remoto, OAuth).", "official"),
    ("linear", "Linear oficial (remoto, OAuth).", "official"),
    ("slack", "Slack: leer y enviar mensajes.", "third_party"),
    ("google-drive", "Google Drive: buscar y leer ficheros.", "third_party"),
    ("wordpress", "WordPress: crear y editar entradas.", "third_party"),
]

TEMPLATES = [
    ("analyst", "Analista", "Analista de requisitos"),
    ("developer", "Desarrollador", "Desarrollador"),
    ("qa", "QA", "QA"),
    ("writer", "Redactor", "Redactor"),
    ("sales", "Comercial", "Comercial"),
]

PROJECTS = [
    {
        "name": "Tienda online",
        "pipeline": {
            "stages": [
                {"name": "Requisitos", "agent": "Analista", "requires_review": True},
                {"name": "Desarrollo", "agent": "Dev"},
                {"name": "QA", "agent": "QA", "reject_to": 1},
            ],
            "links": [{"source": 0, "target": 1}, {"source": 1, "target": 2}],
        },
    },
    {"name": "Blog corporativo", "pipeline": None},
]


def installation(scale: int = 0) -> dict:
    skills = [{"name": n, "description": d, "scope": "general"} for n, d in SKILLS]
    docs = [
        {"id": i, "title": t, "scope": s, "project": p, "source": src} for i, t, s, p, src in DOCS
    ]
    connections = [
        {"name": n, "description": d, "tools": t, "enabled": True} for n, d, t in CONNECTIONS
    ]
    if scale:
        skills += [
            {
                "name": f"skill-relleno-{i:03d}",
                "description": f"Skill de relleno {i} sobre un tema concreto con una descripción de longitud realista para medir el tamaño.",
                "scope": "general",
            }
            for i in range(200 - len(skills))
        ]
        docs += [
            {
                "id": f"doc-{i:03d}",
                "title": f"Documento de relleno {i}",
                "scope": "general",
                "project": "",
                "source": f"carpeta/documento-{i:03d}.pdf",
            }
            for i in range(300 - len(docs))
        ]
        connections += [
            {
                "name": f"conexion-{i:02d}",
                "description": f"Conexión de relleno {i}.",
                "tools": [f"tool_{j}" for j in range(8)],
                "enabled": True,
            }
            for i in range(50 - len(connections))
        ]
    return {
        "clis": CLIS,
        "tools": TOOLS,
        "teams": TEAMS,
        "agents": AGENTS,
        "skills": skills,
        "docs": docs,
        "connections": connections,
        "registry": [{"ref": r, "description": d, "kind": k} for r, d, k in REGISTRY],
        "templates": [{"id": i, "name": n, "role": r} for i, n, r in TEMPLATES],
        "projects": PROJECTS,
    }
