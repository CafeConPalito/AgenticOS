# Claude Code en ConPTY (P1–P3)

argv: `claude --model haiku --strict-mcp-config Responde solo con la palabra UNO` · cwd: sandbox · ventana 120×40

## Diálogo de confianza en la carpeta (t=4.1s)

```text
u
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
 Accessing workspace:

 C:\Users\usuario\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949

 Quick safety check: Is this a project you created or one you trust? (Like your own code, a well-known open source
 project, or work from your team). If not, take a moment to review what's in this folder first.

 Claude Code'll be able to read, edit, and execute files here.

 Security guide

 ❯ No, exit
   Yes, I trust this folder

 Enter to confirm · Esc to cancel
```

## a) Respuesta al prompt inicial ✅ (t=11.0s)

```text
u
 ▐▛███▛█   Claude Code v2.1.296
▝▜██████▀  Haiku 5.5 · Claude Pro
 ▝▝   ▝▝   ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949


❯ Responde solo con la palabra UNO

● UNO

✻ Cogitated for 1s · done 20:09























                                                                                                    ◐ medium · /effort
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 58%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## b) Segundo prompt escrito desde fuera ✅ (t=15.4s)

```text
u
 ▐▛███▛█   Claude Code v2.1.296
▝▜██████▀  Haiku 5.5 · Claude Pro
 ▝▝   ▝▝   ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949


❯ Responde solo con la palabra UNO

● UNO

✻ Cogitated for 1s · done 20:09

❯ Responde solo con la palabra DOS

● DOS

✻ Cooked for 0s · done 20:10

















                                                                                                    ◐ medium · /effort
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 58%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## c1) Turno largo en curso (antes de Esc) (t=17.3s)

```text
u
 ▐▛███▛█   Claude Code v2.1.296
▝▜██████▀  Haiku 5.5 · Claude Pro
 ▝▝   ▝▝   ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949


❯ Responde solo con la palabra UNO

● UNO

✻ Cogitated for 1s · done 20:09

❯ Responde solo con la palabra DOS

● DOS

✻ Cooked for 0s · done 20:10

❯ Escribe los números del 1 al 300, uno por línea, sin ningún otro texto













✻ Creating… (1s · ↓ 58 tokens)
  ⎿  Tip: Use /voice to enable push-to-talk dictation

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 58%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## c2) Tras pulsar Esc ✅ (t=19.5s)

```text
u 148
  149
  150
  151
  152
  153
  154
  155
  156
  157
  158
  159
  160
  161
  162
  163
  164
  165
  166
  167
  168
  169
  170
  171
  172
  173
  174
  175
  176
  177
  178
  179
  180
  ⎿  Interrupted · What should Claude do instead?

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 58%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## c3) La sesión sigue viva y responde tras la interrupción ✅ (t=24.8s)

```text
u 154
  155
  156
  157
  158
  159
  160
  161
  162
  163
  164
  165
  166
  167
  168
  169
  170
  171
  172
  173
  174
  175
  176
  177
  178
  179
  180
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

● TRES

✻ Baked for 0s · done 20:10

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯ Escribe los números del 1 al 300
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949 | Haiku 5.5 | medium+thinking | ctx 95% | 5h 58%…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## e) Tras redimensionar a 90×30 (t=26.8s)

```text
  164
  165
  166
  167
  168
  169
  170
  171
  172
  173
  174
  175
  176
  177
  178
  179
  180
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

● TRES

✻ Baked for 0s · done 20:10

──────────────────────────────────────────────────────────────────────────────────────────
❯ Escribe los números del 1 al 300
──────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949 | Haiku 5.5 | medi…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## d1) Tras un Ctrl+C (sin turno en curso) ✅ (t=28.3s)

```text
  164
  165
  166
  167
  168
  169
  170
  171
  172
  173
  174
  175
  176
  177
  178
  179
  180
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

● TRES

✻ Baked for 0s · done 20:10

──────────────────────────────────────────────────────────────────────────────────────────
❯ Escribe los números del 1 al 300
──────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949 | Haiku 5.5 | medi…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## d2) Tras un segundo Ctrl+C ❌ (t=38.3s)

```text
  164
  165
  166
  167
  168
  169
  170
  171
  172
  173
  174
  175
  176
  177
  178
  179
  180
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

● TRES

✻ Baked for 0s · done 20:10

──────────────────────────────────────────────────────────────────────────────────────────
❯ Escribe los números del 1 al 300
──────────────────────────────────────────────────────────────────────────────────────────
  ~\AppData\Local\AgenticOS-spike\sandbox\claude-pty-20261009-200949 | Haiku 5.5 | medi…
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

## d3) Tras escribir /exit ✅ (t=39.8s)

```text
  164
  165
  166
  167
  168
  169
  170
  171
  172
  173
  174
  175
  176
  177
  178
  179
  180
  ⎿  Interrupted · What should Claude do instead?

❯ Responde solo con la palabra TRES

  ❯ /exit                       Exit the CLI
    /context                    Visualize current context usage as a colored grid
    /usage-credits              Configure usage credits or request them from your admin
                                when you hit a limit
──────────────────────────────────────────────────────────────────────────────────────────
❯ /exituuu
Resume this session with:─────────────────────────────────────────────────────────────────
claude --resume d5bc3870-3386-434f-bea0-a426ed38c02f-20261009-200949 | Haiku 5.5 | medi…
  ⏵⏵ auto mode on (shift+tab to cycle)
```

Proceso vivo al final: False

Configuración global: SIN CAMBIOS
