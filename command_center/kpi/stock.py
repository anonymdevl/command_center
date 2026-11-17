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
        label="Stock Value",
        fact="fact_stock_balance",
        measure="stock_value",
        unit="currency",
        direction="neutral",
        filters=ALL,
        note="across {stock_lines} Bin records (item and warehouse)",
        drill_filters=ALL,
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_lines",
        label="Bin Records",
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
        label="Reserved Qty",
        fact="fact_stock_balance",
        measure="reserved_qty",
        unit="quantity",
        direction="neutral",
        filters=ALL,
        note="on submitted Sales Orders",
        drill_filters={"reserved_qty": [">", 0]},
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_available_qty",
        label="Actual Qty Less Reserved Qty",
        fact="fact_stock_balance",
        measure="available_qty",
        unit="quantity",
        direction="neutral",
        filters=ALL,
        note="Actual Qty less Reserved Qty",
        drill_filters=ALL,
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_on_order_qty",
        label="Ordered Qty",
        fact="fact_stock_balance",
        measure="ordered_qty",
        unit="quantity",
        direction="neutral",
        filters=ALL,
        note="on Purchase Orders not yet received",
        drill_filters={"ordered_qty": [">", 0]},
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_unvalued_lines",
        label="Stock with No Valuation Rate",
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
        note="Actual Qty with no Valuation Rate",
        drill_filters={"has_valuation": 0, "actual_qty": [">", 0]},
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_valued_value",
        label="Stock with a Valuation Rate",
        fact="fact_stock_balance",
        measure="stock_value",
        unit="currency",
        direction="neutral",
        filters=VALUED,
        note="{stock_valued_value_share} of Stock Value",
        drill_filters=VALUED,
        as_of_basis="data_horizon",
        subset_of="all Stock Value",
        share_of="stock_value",
    ),

    # 18 Oct 2026.
    Kpi(
        key="stock_worst_shortfall",
        label="Worst Shortfall",
        fact="fact_stock_balance",
        measure="available_qty",
        agg="top",
        group_by="item_code",
        order="asc",
        negate=True,
        unit="quantity",
        direction="higher_is_worse",
        # Available is on hand less reserved, so a negative figure is promised stock
        # that is not there. The item with the most negative total, written as the
        # positive number short.
        filters={"available_qty": ["<", 0]},
        note="{group}",
        drill_filters={"available_qty": ["<", 0]},
        as_of_basis="data_horizon",
        subset_of="one item, across warehouses",
    ),
    Kpi(
        key="stock_lines_promised",
        label="Lines with Reserved Qty",
        fact="fact_stock_balance",
        measure="*",
        agg="count",
        unit="count",
        direction="neutral",
        filters={"reserved_qty": [">", 0]},
        note="with Reserved Qty",
        drill_filters={"reserved_qty": [">", 0]},
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_short_products",
        label="Items Reserved Above Actual Qty",
        fact="fact_stock_balance",
        measure="*",
        agg="count_distinct",
        distinct_on="item_code",
        unit="count",
        direction="higher_is_worse",
        filters={"available_qty": ["<", 0]},
        note="Reserved Qty above Actual Qty",
        drill_filters={"available_qty": ["<", 0]},
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="stock_lines_covered",
        label="Reserved Lines Covered by Actual Qty",
        fact="fact_stock_balance",
        measure="*",
        agg="count",
        unit="count",
        filters={"reserved_qty": [">", 0], "available_qty": [">=", 0]},
        note="of {stock_lines_promised} promised",
        drill_filters={"reserved_qty": [">", 0], "available_qty": [">=", 0]},
        as_of_basis="data_horizon",
    ),
    Kpi(
        key="score_deliver",
        label="Can we deliver what we sold?",
        fact="fact_stock_balance",
        measure="*",
        agg="ratio",
        numerator="stock_lines_covered",
        denominator="stock_lines_promised",
        unit="percent",
        direction="higher_is_better",
        note="of {stock_lines_promised} Bin records with Reserved Qty have the Actual Qty",
        as_of_basis="data_horizon",
        subset_of="Bin records with Reserved Qty",
    ),
)
