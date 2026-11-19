"""Generates docs/django-db.md: an ERD diagram and text descriptions of the
tables that the 'bmsapp' Django application keeps in the Django database.

Run it again whenever BMON's models change:

    uv run scripts/make_django_docs.py

It combines two sources:
* The database itself (opened read-only) for the real table and column names,
  column types and foreign keys.
* BMON's 'bmsapp/models.py' for the descriptions: the docstring of each model
  class and the comments written above each field. The file is only parsed as
  text; Django is not needed and no BMON code is run.
"""
import ast
import re
from pathlib import Path

import bmon_data
from bmon_data import settings

OUT_PATH = settings.PROJECT_DIR / "docs" / "django-db.md"
MODELS_PATH = settings.BMON_DIR / "bmsapp" / "models.py"
PREFIX = "bmsapp_"

RELATION_FIELDS = ("ForeignKey", "OneToOneField")


# ------------------------- Parsing models.py -------------------------

def clean(text: str) -> str:
    """Collapses whitespace so the text fits in one Markdown table cell."""
    return re.sub(r"\s+", " ", text or "").strip().replace("|", "\\|")


def comment_above(lines: list, lineno: int) -> str:
    """Returns the text of the block of '#' comment lines directly above
    source line 'lineno' (1-based).
    """
    found = []
    i = lineno - 2
    while i >= 0 and lines[i].strip().startswith("#"):
        found.insert(0, lines[i].strip().lstrip("#").strip())
        i -= 1
    return clean(" ".join(found))


def target_name(node) -> str:
    """The model name a ForeignKey / ManyToManyField points to."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        return str(node.value)
    return "?"


def parse_models() -> dict:
    """Returns {ModelName: {'doc': str, 'fields': {field_name: info}}} where
    info has keys 'kind', 'comment', 'label', 'help', 'target' and 'through'.
    """
    source = MODELS_PATH.read_text(encoding="utf-8-sig")
    lines = source.splitlines()
    result = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not any(ast.unparse(b).endswith("Model") for b in node.bases):
            continue
        fields = {}
        for stmt in node.body:
            if not (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call)):
                continue
            func = ast.unparse(stmt.value.func)
            if not func.startswith("models."):
                continue
            kind = func.split(".")[-1]
            call = stmt.value
            kwargs = {k.arg: k.value for k in call.keywords if k.arg}
            info = {
                "kind": kind,
                "comment": comment_above(lines, stmt.lineno),
                "label": "", "help": "", "target": None, "through": None,
            }
            if kind in RELATION_FIELDS or kind == "ManyToManyField":
                info["target"] = target_name(call.args[0])
            elif call.args and isinstance(call.args[0], ast.Constant):
                info["label"] = clean(str(call.args[0].value))
            for key, dest in (("verbose_name", "label"), ("help_text", "help")):
                if key in kwargs and isinstance(kwargs[key], ast.Constant):
                    info[dest] = clean(str(kwargs[key].value))
            if "through" in kwargs:
                info["through"] = target_name(kwargs["through"])
            fields[stmt.targets[0].id] = info
        result[node.name] = {"doc": clean(ast.get_docstring(node)), "fields": fields}
    return result


# ------------------------- Reading the schema -------------------------

def read_schema(conn) -> dict:
    """Returns {table_name: {'columns': [...], 'fks': {column: (table, column)}}}
    for every bmsapp table in the Django database.
    """
    tables = [
        r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE ? ORDER BY name",
            (PREFIX + "%",),
        )
    ]
    schema = {}
    for table in tables:
        columns = [
            {"name": r["name"], "type": r["type"].lower(), "pk": bool(r["pk"]), "notnull": bool(r["notnull"])}
            for r in conn.execute(f'PRAGMA table_info("{table}")')
        ]
        fks = {
            r["from"]: (r["table"], r["to"])
            for r in conn.execute(f'PRAGMA foreign_key_list("{table}")')
        }
        schema[table] = {"columns": columns, "fks": fks}
    return schema


# ------------------------- Writing the document -------------------------

def describe(info: dict) -> str:
    """Builds the description of a column from the model field information."""
    parts = []
    comment = info["comment"]
    if comment:
        comment = comment[0].upper() + comment[1:]
        if comment[-1] not in ".!?:":
            comment += "."
        parts.append(comment)
    if info["label"] and info["label"].lower() not in info["comment"].lower():
        parts.append(f"(Admin label: \"{info['label']}\")")
    if info["help"]:
        parts.append(f"(Help text: \"{info['help']}\")")
    return " ".join(parts)


def mermaid_type(sql_type: str) -> str:
    """A column type as a single word, which Mermaid requires."""
    return re.sub(r"[^a-z]", "", sql_type.split("(")[0]) or "text"


def build() -> str:
    models = parse_models()
    with bmon_data.sqlite_django() as conn:
        schema = read_schema(conn)

    table_of = {name: PREFIX + name.lower() for name in models}
    model_of = {table: name for name, table in table_of.items()}

    # Link tables that Django makes automatically for a ManyToManyField.
    link_tables = {}        # table name -> (model, field name, target model)
    for name, model in models.items():
        for fname, info in model["fields"].items():
            if info["kind"] == "ManyToManyField" and not info["through"]:
                link_tables[f"{table_of[name]}_{fname}"] = (name, fname, info["target"])

    out = []
    w = out.append
    w("# The Django Database (`bmon.sqlite`)\n")
    w("<!-- GENERATED by scripts/make_django_docs.py - do not edit by hand. -->\n")
    w("This database holds BMON's *configuration*: the buildings, the sensors, how sensors are\n"
      "assigned to buildings, alerts, dashboards and so on. It does **not** hold sensor readings;\n"
      "those are in the [sensor reading database](reading-db.md).\n")
    w("The tables below belong to BMON's `bmsapp` Django application and are described by\n"
      "the model classes in BMON's `bmsapp/models.py`. Django names each table\n"
      "`bmsapp_<model name in lower case>`.\n")
    w("In a DuckDB session started as described in the [README](../README.md), the database is\n"
      "attached read-only as `bmon`, so a table is referred to as, for example, `bmon.bmsapp_building`:\n")
    w("```sql\nSELECT id, title, latitude, longitude FROM bmon.bmsapp_building ORDER BY title;\n```\n")

    w("## Things to know\n")
    w("- **Two kinds of sensor ID.** `bmsapp_sensor.id` is an integer row number used only for\n"
      "  links *within this database*. `bmsapp_sensor.sensor_id` is the text ID (for example\n"
      "  `A81758FFFE0526D8_temperature`) that names the sensor's table in the reading database and\n"
      "  appears in BMON's charts and API. Foreign key columns named `sensor_id` in *other* tables\n"
      "  (such as `bmsapp_bldgtosensor.sensor_id`) hold the integer `bmsapp_sensor.id`.\n")
    w("- **Sensors belong to buildings through `bmsapp_bldgtosensor`.** One sensor can be in several\n"
      "  buildings (a weather station, for example), and that table also gives the sensor's group\n"
      "  and sort order within the building. The `sensors` view created by the DuckDB init file\n"
      "  does this join for you.\n")
    w("- **Many-to-many links** are stored in small link tables, listed at the\n"
      "  [end of this page](#link-tables).\n")
    w("- **Booleans** are stored as the integers 0 and 1. The few **times** (such as\n"
      "  `bmsapp_alertcondition.last_notified`) are Unix timestamps; `to_timestamp()` converts them.\n")
    w("- Several text columns hold **YAML** (function parameters, other properties). They need\n"
      "  to be parsed in Python to be used.\n")

    # ---- ERD
    w("## Entity relationship diagram\n")
    w("Only key columns are shown: the primary key (PK), foreign keys (FK) and the main\n"
      "identifying column. Full column lists are in the next section. Read `||--o{` as\n"
      "\"one to many\" and `}o--o{` as \"many to many\" (through a link table).\n")
    w("```mermaid\nerDiagram")
    identifying = ("title", "label", "name", "sensor_id", "description", "widget_type", "script_file_name")
    for name in models:
        table = table_of[name]
        if table not in schema:
            continue
        w(f"    {table} {{")
        fks = schema[table]["fks"]
        shown_ident = False
        for col in schema[table]["columns"]:
            cname = col["name"]
            key = "PK" if col["pk"] else ("FK" if cname in fks else "")
            if not key:
                if shown_ident or cname not in identifying:
                    continue
                shown_ident = True
            w(f"        {mermaid_type(col['type'])} {cname} {key}".rstrip())
        w("    }")
    for name in models:
        table = table_of[name]
        if table not in schema:
            continue
        for col, (ref_table, _) in schema[table]["fks"].items():
            w(f'    {ref_table} ||--o{{ {table} : "{col}"')
    for link, (name, fname, target) in link_tables.items():
        if link in schema and target in table_of:
            w(f'    {table_of[name]} }}o--o{{ {table_of[target]} : "{fname}"')
    w("```\n")

    # ---- Tables
    w("## Tables\n")
    for name, model in models.items():
        table = table_of[name]
        if table not in schema:
            continue
        w(f"### `{table}`\n")
        w(f"Model class `{name}`. {model['doc']}\n")
        w("| Column | Type | Description |")
        w("|---|---|---|")
        fks = schema[table]["fks"]
        for col in schema[table]["columns"]:
            cname = col["name"]
            fname = cname[:-3] if cname in fks and cname.endswith("_id") else cname
            info = model["fields"].get(fname)
            notes = []
            if col["pk"]:
                notes.append("Primary key; a row number assigned by Django.")
            if cname in fks:
                ref_table, ref_col = fks[cname]
                notes.append(f"Links to [`{ref_table}`](#{ref_table}).`{ref_col}`.")
            if info:
                notes.append(describe(info))
            if not col["notnull"] and not col["pk"]:
                notes.append("Can be NULL.")
            w(f"| `{cname}` | {col['type']} | {' '.join(n for n in notes if n)} |")
        w("")
        m2m = [(f, i) for f, i in model["fields"].items() if i["kind"] == "ManyToManyField"]
        for fname, info in m2m:
            via = table_of.get(info["through"]) if info["through"] else f"{table}_{fname}"
            target = table_of.get(info["target"], info["target"])
            text = f"Many-to-many `{fname}`: linked to [`{target}`](#{target}) through `{via}`."
            if describe(info):
                text += " " + describe(info)
            w(text + "\n")

    # ---- Link tables
    w("## Link tables\n")
    w("Django creates one of these for each many-to-many relationship. Each row links one row\n"
      "of the first table to one row of the second.\n")
    w("| Link table | Columns | Meaning |")
    w("|---|---|---|")
    for link, (name, fname, target) in link_tables.items():
        if link not in schema:
            continue
        cols = ", ".join(f"`{c['name']}`" for c in schema[link]["columns"])
        w(f"| `{link}` | {cols} | The `{fname}` of a `{table_of[name]}` row: "
          f"links it to `{table_of.get(target, target)}` rows. |")
    w("")
    w("An example, listing the buildings of each organization:\n")
    w("```sql\n"
      "SELECT org.title AS organization, bldg.title AS building\n"
      "FROM bmon.bmsapp_organization AS org\n"
      "JOIN bmon.bmsapp_organization_buildings AS link ON link.organization_id = org.id\n"
      "JOIN bmon.bmsapp_building AS bldg ON link.building_id = bldg.id\n"
      "ORDER BY organization, building;\n```\n")

    # ---- Anything unexplained
    known = set(table_of.values()) | set(link_tables)
    extra = [t for t in schema if t not in known]
    if extra:
        w("## Other `bmsapp` tables\n")
        w("These tables are in the database but have no model in the current `models.py`\n"
          "(they are probably left over from an earlier version of BMON): "
          + ", ".join(f"`{t}`" for t in extra) + ".\n")

    w("## Other tables in the database\n")
    w("The remaining tables belong to Django itself, not to BMON: `auth_*` (user accounts,\n"
      "groups and permissions), `django_admin_log` (a history of changes made in the Admin\n"
      "site), `django_session`, `django_content_type` and `django_migrations`. Note that\n"
      "`auth_user` holds password hashes and e-mail addresses, and `bmsapp_alertrecipient`\n"
      "holds phone numbers and e-mail addresses; treat query results from them with care.\n")
    return "\n".join(out)


if __name__ == "__main__":
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(build())
    print(f"Wrote {OUT_PATH}")
