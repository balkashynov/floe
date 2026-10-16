"""Small experiment before building the product, using actual pandas releases."""

import json
import warnings

import pandas as pd

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    frame = pd.DataFrame(
        {
            "region": pd.Categorical(
                ["east", "west", "east"], categories=["east", "west", "north"]
            ),
            "revenue": [120, 80, 40],
        }
    )
    groups = frame.groupby("region")["revenue"].sum()
    prices = pd.DataFrame({"price": [10, 20, 30]})
    column = prices["price"]
    column.iloc[0] = 99
    print(
        json.dumps(
            {
                "pandas": pd.__version__,
                "groupby": groups.to_dict(),
                "prices": prices.price.tolist(),
                "strings": str(pd.Series(["a", "b"]).dtype),
            }
        )
    )
