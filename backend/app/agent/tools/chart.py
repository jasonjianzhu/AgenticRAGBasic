"""Chart tool — generates ECharts configuration from data."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChartAxis:
    label: str = ""
    data: list[Any] = field(default_factory=list)


@dataclass
class ChartSeries:
    name: str = ""
    data: list[Any] = field(default_factory=list)
    type: str | None = None  # override chart_type per series if needed


@dataclass
class ChartConfig:
    """ECharts-compatible chart configuration."""
    chart_type: str = "bar"  # line, bar, pie, table, area, stacked_bar
    title: str = ""
    x_axis: ChartAxis = field(default_factory=ChartAxis)
    y_axis: ChartAxis = field(default_factory=ChartAxis)
    series: list[ChartSeries] = field(default_factory=list)

    def to_echarts_option(self) -> dict[str, Any]:
        """Convert to ECharts option JSON."""
        if self.chart_type == "pie":
            return self._to_pie()
        if self.chart_type == "table":
            return self._to_table()
        return self._to_cartesian()

    def _to_cartesian(self) -> dict[str, Any]:
        """Line, bar, area, stacked_bar."""
        series_list = []
        for s in self.series:
            series_type = s.type or ("line" if self.chart_type == "area" else self.chart_type.replace("stacked_", ""))
            item: dict[str, Any] = {"name": s.name, "type": series_type, "data": s.data}
            if self.chart_type == "area":
                item["areaStyle"] = {}
            if self.chart_type == "stacked_bar":
                item["stack"] = "total"
            series_list.append(item)

        return {
            "title": {"text": self.title},
            "tooltip": {"trigger": "axis"},
            "legend": {"data": [s.name for s in self.series]},
            "xAxis": {"type": "category", "name": self.x_axis.label, "data": self.x_axis.data},
            "yAxis": {"type": "value", "name": self.y_axis.label},
            "series": series_list,
        }

    def _to_pie(self) -> dict[str, Any]:
        data = []
        if self.series:
            s = self.series[0]
            for i, name in enumerate(self.x_axis.data):
                val = s.data[i] if i < len(s.data) else 0
                data.append({"name": str(name), "value": val})
        return {
            "title": {"text": self.title},
            "tooltip": {"trigger": "item"},
            "series": [{"type": "pie", "data": data}],
        }

    def _to_table(self) -> dict[str, Any]:
        """Table type — just pass through columns and rows."""
        return {
            "chart_type": "table",
            "title": self.title,
            "columns": self.x_axis.data,
            "rows": [s.data for s in self.series],
        }
