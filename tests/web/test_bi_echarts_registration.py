"""Source-level guard: every ECharts type used by bi-cockpit must be registered.

Rationale: ``EChart.tsx`` switched from ``import * as echarts from 'echarts'``
(full bundle, 309KB brotli) to ``echarts/core`` + an explicit ``echarts.use([...])``
list (173KB brotli, -43.9% measured). The tradeoff is that an unregistered chart
type **fails silently** — echarts renders nothing and throws no build error, so
neither tsc nor eslint catches it. A future panel adding ``type: 'scatter'``
would ship a blank chart to the BI console.

This closes that hole at the source level: any series type or option component
used anywhere under ``web/components/bi-cockpit`` must appear in the registration
list. Adding a chart type without registering it trips CI.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COCKPIT_ROOT = REPO_ROOT / "web" / "components" / "bi-cockpit"
ECHART_WRAPPER = COCKPIT_ROOT / "EChart.tsx"

# ECharts series types (stable public API). Only these require a chart class;
# `type: 'value'` / `'category'` (axes), `'text'` (graphic), `'shadow'`
# (axisPointer) are not series and are ignored.
SERIES_TYPE_TO_CHART = {
    "line": "LineChart",
    "bar": "BarChart",
    "pie": "PieChart",
    "scatter": "ScatterChart",
    "effectScatter": "EffectScatterChart",
    "radar": "RadarChart",
    "tree": "TreeChart",
    "treemap": "TreemapChart",
    "sunburst": "SunburstChart",
    "boxplot": "BoxplotChart",
    "candlestick": "CandlestickChart",
    "heatmap": "HeatmapChart",
    "map": "MapChart",
    "parallel": "ParallelChart",
    "lines": "LinesChart",
    "graph": "GraphChart",
    "sankey": "SankeyChart",
    "funnel": "FunnelChart",
    "gauge": "GaugeChart",
    "pictorialBar": "PictorialBarChart",
    "themeRiver": "ThemeRiverChart",
    "custom": "CustomChart",
}

# Option keys that need a component installed. `xAxis`/`yAxis` are served by
# GridComponent, and axisPointer ships inside TooltipComponent's install.
#
# Known limitation (stated rather than papered over): this is a line-oriented
# regex, so it cannot tell a top-level option key from a same-named key nested
# inside a series. `title` is deliberately absent — gauge series carry their own
# `title` block (Charts.tsx:177), which would flag TitleComponent on every run
# even though no chart here uses a top-level title. A future top-level `title:`
# would therefore go uncaught; that costs a missing chart heading, not a blank
# chart, which is why the series check above is the load-bearing one.
OPTION_KEY_TO_COMPONENT = {
    "tooltip": "TooltipComponent",
    "legend": "LegendComponent",
    "grid": "GridComponent",
    "xAxis": "GridComponent",
    "yAxis": "GridComponent",
    "radar": "RadarComponent",
    "graphic": "GraphicComponent",
    "dataZoom": "DataZoomComponent",
    "visualMap": "VisualMapComponent",
    "toolbox": "ToolboxComponent",
    "polar": "PolarComponent",
    "dataset": "DatasetComponent",
}

TYPE_LITERAL = re.compile(r"""type:\s*['"]([A-Za-z]+)['"]""")
# Option-level component keys sit at the start of a line inside an option
# object literal; series-nested ones (e.g. a series' own `tooltip`) need the
# same component, so matching both is intentional.
# A trailing quote means the value is a string, not an option block — `theme.ts`
# has `grid: 'rgba(...)'` as a palette colour, which needs no component.
OPTION_KEY = re.compile(
    r"^\s+(" + "|".join(OPTION_KEY_TO_COMPONENT) + r"):\s*(?!['\"])",
    re.MULTILINE,
)


def _registered_symbols() -> set[str]:
    source = ECHART_WRAPPER.read_text(encoding="utf-8")
    match = re.search(r"echarts\.use\(\[(.*?)\]\)", source, re.DOTALL)
    assert match, "EChart.tsx must register components via echarts.use([...])"
    return {token.strip() for token in match.group(1).split(",") if token.strip()}


def _cockpit_sources() -> list[Path]:
    files = sorted(p for p in COCKPIT_ROOT.rglob("*") if p.suffix in {".ts", ".tsx"})
    assert files, f"no bi-cockpit sources found under {COCKPIT_ROOT}"
    return files


def test_every_series_type_has_a_registered_chart() -> None:
    registered = _registered_symbols()
    missing: list[str] = []
    for path in _cockpit_sources():
        for raw_type in TYPE_LITERAL.findall(path.read_text(encoding="utf-8")):
            chart = SERIES_TYPE_TO_CHART.get(raw_type)
            if chart and chart not in registered:
                missing.append(f"{path.relative_to(REPO_ROOT)}: type '{raw_type}' needs {chart}")
    assert not missing, (
        "ECharts series used without registration in EChart.tsx — these render blank "
        "with no build error:\n  " + "\n  ".join(sorted(set(missing)))
    )


def test_every_option_component_is_registered() -> None:
    registered = _registered_symbols()
    missing: list[str] = []
    for path in _cockpit_sources():
        for key in OPTION_KEY.findall(path.read_text(encoding="utf-8")):
            component = OPTION_KEY_TO_COMPONENT[key]
            if component not in registered:
                missing.append(f"{path.relative_to(REPO_ROOT)}: '{key}' needs {component}")
    assert not missing, (
        "ECharts option components used without registration in EChart.tsx:\n  "
        + "\n  ".join(sorted(set(missing)))
    )


def test_wrapper_does_not_reintroduce_the_full_bundle() -> None:
    source = ECHART_WRAPPER.read_text(encoding="utf-8")
    assert "from 'echarts/core'" in source, "EChart.tsx must import from echarts/core"
    offenders = re.findall(r"^import\s+\*\s+as\s+\w+\s+from\s+'echarts'", source, re.MULTILINE)
    assert not offenders, (
        "`import * as echarts from 'echarts'` pulls the full bundle (echarts' "
        "sideEffects whitelist covers index.js, so it cannot be tree-shaken): "
        "measured 309KB brotli vs 173KB on-demand."
    )
