import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
from facts import FACTS

print("sqlite", sqlite3.sqlite_version, "python", sys.version.split()[0])
db = sqlite3.connect(":memory:")
print(
    "compile options with FTS:",
    [r[0] for r in db.execute("pragma compile_options") if "FTS" in r[0]],
)
db.execute(
    "create virtual table t using fts5(title, body, tokenize='unicode61 remove_diacritics 2')"
)
for f in FACTS:
    db.execute(
        "insert into t(rowid,title,body) values (?,?,?)", (int(f["id"][1:]), f["title"], f["body"])
    )


def q(s):
    terms = [w for w in __import__("re").findall(r"\w+", s)]
    expr = " OR ".join(f'"{w}"' for w in terms)
    return [
        r[0]
        for r in db.execute("select rowid from t where t match ? order by bm25(t) limit 3", (expr,))
    ]


tests = {
    "cancelacion suscripcion (sin tildes)": "cancelacion suscripcion",
    "cancelación (con tilde)": "cancelación suscripción",
    "plural facturas rectificativas": "factura rectificativa",
    "ERR_4012": "ERR_4012",
    "puerto 587 STARTTLS": "puerto 587 STARTTLS",
    "prefijo imp*": "impuest*",
}
for k, v in tests.items():
    print(
        f"{k:42} -> {q(v) if '*' not in v else [r[0] for r in db.execute('select rowid from t where t match ? limit 3', (v,))]}"
    )
