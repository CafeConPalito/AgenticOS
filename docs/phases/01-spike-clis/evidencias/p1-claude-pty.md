# Claude Code en ConPTY (P1–P3)

argv: `claude --model haiku --strict-mcp-config Responde solo con la palabra UNO` · cwd: sandbox · ventana 120×40

## Diálogo de confianza en la carpeta (t=3.7s)

```text
u
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Accessing workspace:

 C:\Users\usuario\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554

 Quick safety check: Is this a project you created or one you trust? (Like your own code, a well-known open source
 project, or work from your team). If not, take a moment to review what's in this folder first.

 Claude Code'll be able to read, edit, and execute files here.

 Security guide

 ❯ No, exit
   Yes, I trust this folder

 Enter to confirm · Esc to cancel
```

## a) Respuesta al prompt inicial ✅ (t=10.6s)

```text
u
 ▐▛███▛█   Claude Code v2.1.296
▝▜██████▀  Haiku 5.5 · Claude Pro
 ▝▝   ▝▝   ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554


❯ Responde solo con la palabra UNO

● UNO

✻ Worked for 1s · done 19:26























                                                                                                    ◐ medium · /effort
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 18%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## b) Segundo prompt escrito desde fuera ✅ (t=18.2s)

```text
u
 ▐▛███▛█   Claude Code v2.1.296
▝▜██████▀  Haiku 5.5 · Claude Pro
 ▝▝   ▝▝   ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554


❯ Responde solo con la palabra UNO

● UNO

✻ Worked for 1s · done 19:26

❯ Responde solo con la palabra DOS

● DOS

✻ Churned for 1s · done 19:26


















────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 18%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## c1) Turno largo en curso (antes de Esc) (t=20.1s)

```text
u
 ▐▛███▛█   Claude Code v2.1.296
▝▜██████▀  Haiku 5.5 · Claude Pro
 ▝▝   ▝▝   ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554


❯ Responde solo con la palabra UNO

● UNO

✻ Worked for 1s · done 19:26

❯ Responde solo con la palabra DOS

● DOS

✻ Churned for 1s · done 19:26

❯ Escribe los números del 1 al 300, uno por línea, sin ningún otro texto













✶ Mustering… (1s · ↓ 40 tokens)
  ⎿  Tip: Run /install-slack-app to use Claude in Slack

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 18%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## c2) Tras pulsar Esc ✅ (t=22.3s)

```text
u 104
  105
  106
  107
  108
  109
  110
  111
  112
  113
  114
  115
  116
  117
  118
  119
  120
  121
  122
  123
  124
  125
  126
  127
  128
  129
  130
  131
  132
  133
  134
  135
  136
  ⎿  Interrupted · What should Claude do instead?

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 18%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## c3) La sesión sigue viva y responde tras la interrupción ✅ (t=28.1s)

```text
u 110
  111
  112
  113
  114
  115
  116
  117
  118
  119
  120
  121
  122
  123
  124
  125
  126
  127
  128
  129
  130
  131
  132
  133
  134
  135
  136
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

● TRES

✻ Worked for 1s · done 19:26

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯ Escribe los números del 1 al 300
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 18%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## e) Tras redimensionar a 90×30 (t=30.2s)

```text
  120
  121
  122
  123
  124
  125
  126
  127
  128
  129
  130
  131
  132
  133
  134
  135
  136
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

● TRES

✻ Worked for 1s · done 19:26

──────────────────────────────────────────────────────────────────────────────────────────
❯ Escribe los números del 1 al 300
──────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554 | Haiku 5.5 | medi…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## d1) Tras un Ctrl+C (sin turno en curso) ✅ (t=31.7s)

```text
  120
  121
  122
  123
  124
  125
  126
  127
  128
  129
  130
  131
  132
  133
  134
  135
  136
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

● TRES

✻ Worked for 1s · done 19:26

──────────────────────────────────────────────────────────────────────────────────────────
❯ Escribe los números del 1 al 300
──────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554 | Haiku 5.5 | medi…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## d2) Tras un segundo Ctrl+C ❌ (t=41.7s)

```text
  120
  121
  122
  123
  124
  125
  126
  127
  128
  129
  130
  131
  132
  133
  134
  135
  136
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

● TRES

✻ Worked for 1s · done 19:26

──────────────────────────────────────────────────────────────────────────────────────────
❯ Escribe los números del 1 al 300
──────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-192554 | Haiku 5.5 | medi…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## d3) Tras escribir /exit ✅ (t=43.0s)

```text
  120
  121
  122
  123
  124
  125
  126
  127
  128
  129
  130
  131
  132
  133
  134
  135
  136
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

  ❯ /exit                       Exit the CLI
    /context                    Visualize current context usage as a colored grid
    /usage-credits              Configure usage credits or request them from your admin
                                when you hit a limit
──────────────────────────────────────────────────────────────────────────────────────────
❯ /exituuu
Resume this session with:─────────────────────────────────────────────────────────────────
claude --resume 3da83603-1b12-4842-a32b-d73fde5fe6e3-20261009-192554 | Haiku 5.5 | medi…
  ⏵⏵ auto mode on (shift+tab to cycle)
```

Proceso vivo al final: False

Configuración global: SIN CAMBIOS
