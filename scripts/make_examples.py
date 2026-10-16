"""Original, small workflow fixtures. Not an unbiased notebook corpus."""

import csv
import json
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1] / "examples"
ROOT.mkdir(exist_ok=True)
with (ROOT / "orders.csv").open("w") as f:
    writer = csv.writer(f)
    writer.writerow(["id", "region", "revenue"])
    writer.writerows([(1, "east", 120), (2, "west", 80), (3, "east", 40)])

CASES = [
    (
        "category-loss",
        "An empty region vanishes",
        "changed",
        """import pandas as pd
orders = pd.read_csv('orders.csv')
orders['region'] = pd.Categorical(orders['region'], categories=['east', 'west', 'north'])""",
        "revenue = orders.groupby('region')['revenue'].sum().reset_index()\nprint('Revenue report generated')",
        "revenue",
        {},
        ["orders.csv"],
    ),
    (
        "category-fixed",
        "Explicit group semantics preserve the report",
        "match",
        """import pandas as pd
orders = pd.read_csv('orders.csv')
orders['region'] = pd.Categorical(orders['region'], categories=['east', 'west', 'north'])""",
        "revenue = orders.groupby('region', observed=False)['revenue'].sum().reset_index()\nprint('Revenue report generated')",
        "revenue",
        {},
        ["orders.csv"],
    ),
    (
        "copy-on-write",
        "The price update no longer reaches its table",
        "changed",
        """import pandas as pd
prices = pd.DataFrame({'id': [1, 2, 3], 'price': [10, 20, 30]})""",
        "selected = prices['price']\nselected.iloc[0] = 99\nprint('Price correction processed')",
        "prices",
        {"keys": ["id"]},
        [],
    ),
    (
        "copy-fixed",
        "Explicit parent-table assignment survives the upgrade",
        "match",
        """import pandas as pd
prices = pd.DataFrame({'id': [1, 2, 3], 'price': [10, 20, 30]})""",
        "prices.loc[0, 'price'] = 99\nprint('Price correction processed')",
        "prices",
        {"keys": ["id"]},
        [],
    ),
    (
        "string-schema",
        "The text schema changes without printed output",
        "changed",
        "import pandas as pd",
        "labels = pd.DataFrame({'label': ['east', 'west']})\nprint('Labels ready')",
        "labels",
        {},
        [],
    ),
    (
        "string-policy",
        "Accept an intentional string dtype migration",
        "match",
        "import pandas as pd",
        "labels = pd.DataFrame({'label': ['east', 'west']})\nprint('Labels ready')",
        "labels",
        {"check_dtype": False},
        [],
    ),
    (
        "removed-alias",
        "A removed frequency alias stops execution",
        "execution_failure",
        "import pandas as pd",
        "months = pd.date_range('2025-01-01', periods=3, freq='M')\nresult = list(months.astype(str))",
        "result",
        {},
        [],
    ),
    (
        "stable-numeric",
        "An unchanged numerical result stays green",
        "match",
        "import numpy as np",
        "result = np.array([[1., 2.], [3., 4.]]) @ np.array([2., 3.])",
        "result",
        {"atol": 1e-12, "rtol": 1e-10},
        [],
    ),
    (
        "unstable",
        "A fresh random result cannot indict an upgrade",
        "inconclusive",
        "import secrets",
        "result = secrets.randbits(64)",
        "result",
        {},
        [],
    ),
    (
        "row-order",
        "Unordered keyed rows remain comparable",
        "match",
        "import pandas as pd\nimport secrets",
        "rows = [(1, 10), (2, 20), (3, 30)]\nif secrets.randbits(1): rows.reverse()\nresult = pd.DataFrame(rows, columns=['id', 'value'])",
        "result",
        {"keys": ["id"]},
        [],
    ),
    (
        "duplicate-keys",
        "Ambiguous row identity never passes",
        "inconclusive",
        "import pandas as pd",
        "result = pd.DataFrame({'id': [1, 1], 'value': [10, 20]})",
        "result",
        {"keys": ["id"]},
        [],
    ),
    (
        "baseline-error",
        "An already broken reference cannot certify an upgrade",
        "inconclusive",
        "import pandas as pd",
        "result = undefined_input + 1",
        "result",
        {},
        [],
    ),
]

manifest = []
for slug, title, expected, setup, calculate, variable, policy, inputs in CASES:
    nb = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(f"# {title}\nOriginal Floe validation fixture."),
            nbformat.v4.new_code_cell(setup, id="prepare"),
            nbformat.v4.new_code_cell(calculate, id="calculate"),
        ]
    )
    nb.cells[0].id = "description"
    nbformat.write(nb, ROOT / f"{slug}.ipynb")
    contract = {
        "schema": 1,
        "title": title,
        "inputs": inputs,
        "observations": [
            {"name": variable, "variable": variable, "cell": "calculate", "policy": policy}
        ],
    }
    (ROOT / f"{slug}.json").write_text(json.dumps(contract, indent=2) + "\n")
    manifest.append({"id": slug, "title": title, "expected": expected})
(ROOT / "cases.json").write_text(json.dumps(manifest, indent=2) + "\n")
