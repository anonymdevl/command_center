/**
 * Apache ECharts, only the parts the platform draws with.
 *
 * Loaded on demand by viz.js (a dynamic import, so it is its own chunk and the first
 * paint never waits for it). Importing from echarts/core and registering each chart
 * keeps the chunk to what is used; adding a chart type means adding it here.
 */
import * as echarts from "echarts/core";
import {
  BarChart, LineChart, PieChart, ScatterChart, FunnelChart, GaugeChart, HeatmapChart,
  TreemapChart, RadarChart, CustomChart,
} from "echarts/charts";
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  VisualMapContinuousComponent, RadarComponent,
} from "echarts/components";
import { UniversalTransition, LabelLayout } from "echarts/features";
import { SVGRenderer } from "echarts/renderers";

echarts.use([
  BarChart, LineChart, PieChart, ScatterChart, FunnelChart, GaugeChart, HeatmapChart,
  TreemapChart, RadarChart, CustomChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  VisualMapContinuousComponent, RadarComponent,
  UniversalTransition, LabelLayout, SVGRenderer,
]);

export default echarts;
