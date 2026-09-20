"""Stock KPIs.

The figure a manager means by "stock" is what can actually be sold, not what is on
the shelf. Those differ by whatever is reserved against orders already taken, and
reporting the larger number as though it were available is how a business promises
goods twice.

So on-hand, reserved and free-to-sell are three separate figures here, and the one
labelled plainly is the one that can be sold.
"""

from command_center.kpi.registry import Kpi, register

ALL = {}
VALUED = {"has_valuation": 1}

register(
    Kpi(
        key="stock_value",
        label="Stock on hand",
        fact="fact_stock_balance",
        measure="stock_value",
        unit="currency",
        direction="neutral",
        filters=ALL,
        note="across {stock_lines} item and warehouse combinations",
        drill_filters=ALL,
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_lines",
        label="Item and warehouse lines",
        fact="fact_stock_balance",
        measure="*",
        agg="count",
        unit="count",
        filters=ALL,
        note="worth {stock_value}",
        drill_filters=ALL,
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_reserved_qty",
        label="Reserved against orders",
        fact="fact_stock_balance",
        measure="reserved_qty",
        unit="quantity",
        direction="neutral",
        filters=ALL,
        note="units already promised to customers",
        drill_filters={"reserved_qty": [">", 0]},
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_available_qty",
        label="Free to sell",
        fact="fact_stock_balance",
        measure="available_qty",
        unit="quantity",
        direction="neutral",
        filters=ALL,
        note="on hand less what is reserved",
        drill_filters=ALL,
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_on_order_qty",
        label="On order from suppliers",
        fact="fact_stock_balance",
        measure="ordered_qty",
        unit="quantity",
        direction="neutral",
        filters=ALL,
        note="units bought but not yet received",
        drill_filters={"ordered_qty": [">", 0]},
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_unvalued_lines",
        label="Stock with no valuation",
        fact="fact_stock_balance",
        measure="*",
        agg="count",
        unit="count",
        direction="higher_is_worse",
        filters={"has_valuation": 0, "actual_qty": [">", 0]},
        # Not "worthless stock". ERPNext holds no rate for it, so its value is
        # unknown and it contributes nothing to the total above -- which means the
        # stock figure is an understatement by an unknown amount, and saying so is
        # the only honest way to present it.
        note="held, but with no value recorded against it",
        drill_filters={"has_valuation": 0, "actual_qty": [">", 0]},
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_valued_value",
        label="Valued stock",
        fact="fact_stock_balance",
        measure="stock_value",
        unit="currency",
        direction="neutral",
        filters=VALUED,
        note="{stock_valued_value_share} of stock value",
        drill_filters=VALUED,
        as_of_basis="data_horizon",
        subset_of="all stock on hand",
        share_of="stock_value",
    ),
)
