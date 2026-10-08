// lib/mock-data.ts — datos de ejemplo usados en el diseño
import type { Agent, InboxRequest, Project, Run, Task } from "./types";

export const AGENTS: Agent[] = [
  { id: "ana", name: "Ana", role: "Analista", color: "#F27FB2", cli: "Claude Code", model: "claude-sonnet-4-5", permission: "Preguntar", status: "running", concurrency: { used: 1, max: 1 }, monthCost: 48.2, description: "Convierte ideas en requisitos claros, historias de usuario y criterios de aceptación." },
  { id: "dev", name: "Dev", role: "Desarrollador", color: "#4FD1C5", cli: "Claude Code", model: "claude-opus-4-1", permission: "Autónomo", status: "running", concurrency: { used: 2, max: 2 }, monthCost: 131.75, description: "Implementa funcionalidades full-stack siguiendo los requisitos y las convenciones de cada proyecto." },
  { id: "quique", name: "Quique", role: "QA", color: "#B5E061", cli: "Antigravity", model: "gemini-2.5-pro", permission: "Restringido", status: "waiting", concurrency: { used: 1, max: 1 }, monthCost: 22.1, description: "Prueba cada entrega, escribe tests E2E y devuelve a Desarrollo lo que no cumple los criterios." },
  { id: "rita", name: "Rita", role: "Redactora", color: "#FFA06B", cli: "Antigravity", model: "gemini-2.5-flash", permission: "Preguntar", status: "idle", concurrency: { used: 0, max: 1 }, monthCost: 9.85, description: "Escribe artículos, fichas de producto y textos de marketing con el tono de la marca." },
  { id: "carla", name: "Carla", role: "Comercial", color: "#8FB4FF", cli: "Claude Code", model: "claude-sonnet-4-5", permission: "Restringido", status: "draft", concurrency: { used: 0, max: 1 }, monthCost: 0, description: "Prepara propuestas comerciales para clientes a partir del catálogo de productos.", draft: true },
];

export const PROJECTS: Project[] = [
  { id: "tienda", name: "Tienda online", color: "#7C9CFF", path: "D:\\proyectos\\tienda-online", branch: "main", pipeline: "Desarrollo web", workspace: "worktree" },
  { id: "reservas", name: "App reservas", color: "#E58AF0", path: "D:\\proyectos\\app-reservas", branch: "feature/login-google", pipeline: "Desarrollo web", workspace: "worktree" },
  { id: "blog", name: "Blog corporativo", color: "#F2C94C", path: "D:\\contenido\\blog-corporativo", branch: null, pipeline: "Contenidos", workspace: "folder" },
];

export const TASKS: Task[] = [
  { id: "t1", code: "T-142", title: "Login con Google", projectId: "reservas", stage: "Desarrollo", agentId: "dev", status: "running", priority: "Alta", subtasks: [3, 5], elapsed: "41 min", cost: 2.84 },
  { id: "t2", code: "T-151", title: "Requisitos del checkout", projectId: "tienda", stage: "Requisitos", agentId: "ana", status: "running", priority: "Alta", subtasks: [1, 4], elapsed: "12 min", cost: 0.62 },
  { id: "t3", code: "T-138", title: "QA carrito de compra", projectId: "tienda", stage: "QA", agentId: "quique", status: "waiting", priority: "Media", subtasks: [6, 8], elapsed: "1 h 05", cost: 1.9 },
  { id: "t4", code: "T-160", title: "Artículo: tendencias eCommerce 2026", projectId: "blog", stage: "Redacción", agentId: "rita", status: "backlog", priority: "Baja", subtasks: [0, 3] },
  { id: "t5", code: "T-147", title: "API de disponibilidad", projectId: "reservas", stage: "Desarrollo", agentId: "dev", status: "queued", priority: "Alta", subtasks: [0, 6] },
  { id: "t6", code: "T-149", title: "Pasarela de pago con Stripe", projectId: "tienda", stage: "Desarrollo", agentId: "dev", status: "queued", priority: "Urgente", subtasks: [0, 5] },
  { id: "t7", code: "T-131", title: "Calendario de reservas", projectId: "reservas", stage: "QA", agentId: "quique", status: "review", priority: "Media", subtasks: [4, 4], elapsed: "2 h 10", cost: 4.12 },
  { id: "t8", code: "T-120", title: "Página de categorías", projectId: "tienda", stage: "QA", agentId: "quique", status: "done", priority: "Media", subtasks: [5, 5], elapsed: "1 h 32", cost: 3.05 },
  { id: "t9", code: "T-118", title: "Guía de estilo editorial", projectId: "blog", stage: "Revisión", agentId: "rita", status: "done", priority: "Baja", subtasks: [3, 3], elapsed: "38 min", cost: 0.74 },
  { id: "t10", code: "T-155", title: "Notificaciones por email", projectId: "reservas", stage: "Requisitos", agentId: "ana", status: "backlog", priority: "Media", subtasks: [0, 0] },
  { id: "t12", code: "T-153", title: "Política de devoluciones", projectId: "tienda", stage: "Requisitos", agentId: "ana", status: "queued", priority: "Media", subtasks: [0, 2] },
  { id: "t13", code: "T-158", title: "Briefing newsletter de octubre", projectId: "blog", stage: "Briefing", agentId: "ana", status: "queued", priority: "Baja", subtasks: [0, 0] },
  { id: "t14", code: "T-150", title: "QA reservas recurrentes", projectId: "reservas", stage: "QA", agentId: "quique", status: "queued", priority: "Alta", subtasks: [0, 4] },
  { id: "t15", code: "T-144", title: "Revisión SEO de la home", projectId: "blog", stage: "Revisión", agentId: "rita", status: "review", priority: "Media", subtasks: [2, 3], elapsed: "24 min", cost: 0.41 },
];

export const QUEUES: Record<string, string[]> = {
  ana: ["t2", "t12", "t13"], dev: ["t1", "t6", "t5"], quique: ["t3", "t14"], rita: [],
};

export const INBOX: InboxRequest[] = [
  { id: "i1", type: "approval", agentId: "quique", projectId: "tienda", taskId: "t3", title: "¿Puedo ejecutar este comando?", command: "npm install -D @playwright/test", context: "Necesito Playwright para los tests E2E del carrito. Se añadirá solo a devDependencies.", when: "hace 4 min", status: "pending" },
  { id: "i2", type: "question", agentId: "dev", projectId: "reservas", taskId: "t5", title: "¿Usamos Postgres o SQLite para las reservas?", context: "Prevemos ~2.000 reservas al día con acceso concurrente desde el panel de administración.", options: ["Postgres", "SQLite"], when: "hace 9 min", status: "pending" },
  { id: "i3", type: "blocked", agentId: "ana", projectId: "tienda", taskId: "t2", title: "Me falta la clave de test de Stripe", context: "No puedo validar los métodos de pago disponibles sin acceso a la cuenta de pruebas.", when: "hace 18 min", status: "pending" },
  { id: "i4", type: "approval", agentId: "dev", projectId: "reservas", taskId: "t1", title: "¿Puedo hacer push de la rama?", command: "git push origin feature/login-google", context: "Los 14 tests de autenticación pasan. Abriré un PR hacia develop.", when: "hace 22 min", status: "pending" },
  { id: "i5", type: "done", agentId: "rita", projectId: "blog", taskId: "t9", title: "Tarea completada", context: "Documento de 6 páginas con tono, vocabulario y ejemplos. Guardado en docs/estilo.md.", when: "hace 31 min", status: "pending" },
];

export const RUN_TREE: Run = {
  id: "main", name: "Dev · ejecución principal", status: "running", durationSec: 2471,
  children: [
    { id: "explore", name: "explorar-auth", status: "done", durationSec: 228 },
    { id: "tests", name: "tests-auth", status: "running", durationSec: 380, children: [
      { id: "fixtures", name: "fixtures-oauth", status: "done", durationSec: 72 },
    ] },
  ],
};

export const agentById = (id: string) => AGENTS.find((a) => a.id === id)!;
export const projectById = (id: string) => PROJECTS.find((p) => p.id === id)!;
