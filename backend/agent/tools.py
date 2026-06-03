TOOL_SCHEMAS = {
    "query_tool": {
        "metric":    "order_count | delay_rate | on_time_rate | avg_delivery_days | order_value",
        "group_by":  "carrier | region | product_category | week | month | warehouse",
        "filters": {
            "from_date": "YYYY-MM-DD",
            "to_date":   "YYYY-MM-DD",
            "carrier":   "string",
            "region":    "string",
            "status":    "delivered | delayed | in_transit | exception | canceled",
        },
        "chart_hint": "bar | line | pie | table",
    },
    "forecast_tool": {
        "target":      "SKU code or product category name",
        "target_type": "sku | category",
        "periods":     "integer 1-12",
        "period_unit": "week | month",
    },
}
