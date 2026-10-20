"""S4c: the same questions among ~150 passages, 120 of them near-duplicates with other identifiers."""

import random
import re
import sqlite3
import sys

import numpy as np
from facts import FACTS
from s4_embed_eval import STOP, OnnxEmbedder, metrics, strip_accents

sys.stdout.reconfigure(encoding="utf-8")
random.seed(7)

reasons = [
    "el NIF del cliente no supera la validación",
    "la serie de numeración está bloqueada",
    "falta el domicilio fiscal",
    "el importe no coincide con el desglose",
    "la fecha de la factura es anterior al cierre",
    "el cliente está dado de baja",
    "el certificado de firma ha caducado",
    "el tipo de IVA no es válido para el país",
    "el formato del fichero no es correcto",
]
actions = [
    "que no tiene espacios ni guiones",
    "que los datos del cliente están completos",
    "la configuración en Ajustes",
    "que el periodo no está cerrado",
    "que el certificado está vigente",
    "el formato indicado en la documentación",
]
extra = []
for n in random.sample(range(4000, 6000), 45):
    extra.append(
        (
            "error",
            f"Error ERR_{n}",
            f"El código ERR_{n} aparece cuando {random.choice(reasons)}. Compruebe {random.choice(actions)}. "
            f"Si el problema continúa, contacte con soporte indicando el código.",
        )
    )
for res in [
    "customers",
    "payments",
    "taxes",
    "series",
    "reports",
    "products",
    "contacts",
    "refunds",
    "templates",
    "users",
]:
    for verb in ["GET", "PUT", "DELETE"]:
        extra.append(
            (
                "api",
                f"API: endpoint /v2/{res}",
                f"El endpoint {verb} /v2/{res} gestiona los recursos de tipo {res}. Requiere la cabecera Authorization "
                f"con un token Bearer y admite hasta {random.choice([30, 60, 120])} peticiones por minuto.",
            )
        )
for ev in [
    "invoice.created",
    "invoice.sent",
    "invoice.overdue",
    "customer.created",
    "payment.failed",
    "payment.refunded",
    "series.closed",
]:
    extra.append(
        (
            "event",
            f"Webhook: evento {ev}",
            f"El evento {ev} se envía cuando se produce el cambio correspondiente. Cada petición lleva la cabecera "
            f"X-Aurora-Signature para verificar el origen y se reintenta hasta cinco veces.",
        )
    )
for v in [
    "AURORA_HOME",
    "AURORA_LOG",
    "AURORA_DEBUG",
    "AURORA_TIMEOUT",
    "AURORA_CACHE",
    "AURORA_LANG",
    "AURORA_TOKEN",
    "AURORA_PORT",
]:
    extra.append(
        (
            "env",
            f"Variable de entorno {v}",
            f"La variable {v} permite ajustar el comportamiento de la versión de escritorio. Si no se define se usa "
            f"el valor predeterminado y la configuración del sistema.",
        )
    )
for t in [
    "PLT-FACTURA-EN",
    "PLT-FACTURA-FR",
    "PLT-PRESUPUESTO-ES",
    "PLT-ALBARAN-ES",
    "PLT-RECIBO-ES",
    "PLT-ABONO-ES",
    "PLT-PROFORMA-ES",
]:
    extra.append(
        (
            "tpl",
            f"Plantilla {t}",
            f"La plantilla {t} es una de las plantillas incluidas. Incluye logotipo, datos fiscales y un pie legal. "
            f"Se puede duplicar para crear variantes sin tocar la original.",
        )
    )
print("distractors:", len(extra))

passages = [f"{f['title']}\n{f['body']}" for f in FACTS] + [f"{t}\n{b}" for _, t, b in extra]
queries = [f["q"] for f in FACTS]
kinds = [f["kind"] for f in FACTS]
gold = list(range(len(FACTS)))

db = sqlite3.connect(":memory:")
db.execute("create virtual table t using fts5(body, tokenize='unicode61 remove_diacritics 2')")
for i, p in enumerate(passages):
    db.execute("insert into t(rowid, body) values (?, ?)", (i, p))


def is_ident(t):
    return bool(re.search(r"[\d_/.\-+]", t)) or (t.isupper() and len(t) > 2)


def words(q, only_ident):
    terms = re.findall(r"[\w./+\-]+", q)
    terms = [
        t
        for t in terms
        if strip_accents(t.lower()) not in STOP and (len(t) > 2 or any(c.isdigit() for c in t))
    ]
    if only_ident:
        terms = [t for t in terms if is_ident(t)]
    if not terms:
        return []
    expr = " OR ".join('"' + t.replace('"', "") + '"' for t in terms)
    return [
        r[0]
        for r in db.execute(
            "select rowid from t where t match ? order by bm25(t) limit 50", (expr,)
        )
    ]


def rrf(lists, weights):
    sc = {}
    for lst, w in zip(lists, weights):
        for pos, d in enumerate(lst):
            sc[d] = sc.get(d, 0) + w / (60 + pos + 1)
    return sorted(sc, key=sc.get, reverse=True)


for name, f in (
    ("e5-small", "model_quantized"),
    ("gemma2", "model_q4"),
    ("bge-m3", "model_quantized"),
):
    e = OnnxEmbedder(name, f)
    pm, qm = e.encode(passages, "passage"), e.encode(queries, "query")
    modes = {"vector": [], "words_ident": [], "rrf_ident": [], "rrf_all": []}
    for qi, q in enumerate(queries):
        vec = list(np.argsort(-(pm @ qm[qi]))[:50])
        wi, wa = words(q, True), words(q, False)
        modes["vector"].append(vec)
        modes["words_ident"].append(wi)
        modes["rrf_ident"].append(rrf([vec, wi], [1, 2]))
        modes["rrf_all"].append(rrf([vec, wa], [1, 1]))
    print(f"\n### {name} among {len(passages)} passages")
    for m, ranks in modes.items():
        row = []
        for label, sel in (
            ("all", range(30)),
            ("para", [i for i, k in enumerate(kinds) if k == "paraphrase"]),
            ("exact", [i for i, k in enumerate(kinds) if k == "exact"]),
        ):
            t1, t5, mrr = metrics([ranks[i] for i in sel], [gold[i] for i in sel])
            row.append(f"{label}: t1={t1:.2f} t5={t5:.2f}")
        print(f"  {m:12} " + "  ".join(row))
