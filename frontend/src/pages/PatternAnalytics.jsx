import React from "react";
import { api } from "../api.js";
import { Card, Loading, ErrorBox, useApi } from "../components/ui.jsx";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";

const PATTERN_LABELS = {
  fan_in: "Fan-in",
  fan_out: "Fan-out",
  layering: "Layering",
  split_merge: "Split / Merge",
  circular_flow: "Circular Flow",
  rapid_pass_through: "Rapid Pass-through",
  repeated_intermediary: "Repeated Intermediary",
  escalating_connectivity: "Escalating Connectivity",
};

function labelFor(type) {
  return (
    PATTERN_LABELS[type] ||
    String(type || "Unknown")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

export default function PatternAnalytics() {
  const {
    data,
    loading,
    error,
  } = useApi(() => api.patterns({ limit: 50000 }), []);

  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;

  const events = Array.isArray(data) ? data : [];

  const counts = {};

  events.forEach((p) => {
    const type = p?.pattern_type || "unknown";
    counts[type] = (counts[type] || 0) + 1;
  });

  const chartData = Object.entries(counts)
    .map(([type, count]) => ({
      type,
      label: labelFor(type),
      count,
    }))
    .sort((a, b) => b.count - a.count);

  const totalEvents = events.length;

  const uniqueTypes = chartData.length;

  const mostCommon = chartData[0];

  const structuralTypes = [
    "fan_in",
    "fan_out",
    "layering",
    "split_merge",
  ];

  const temporalTypes = [
    "circular_flow",
    "rapid_pass_through",
    "repeated_intermediary",
    "escalating_connectivity",
  ];

  const structuralCount = events.filter((p) =>
    structuralTypes.includes(p?.pattern_type)
  ).length;

  const temporalCount = events.filter((p) =>
    temporalTypes.includes(p?.pattern_type)
  ).length;

  return (
    <div className="space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold">
          Pattern Analytics
        </h1>

        <p className="text-sm text-muted mt-1">
          Distribution of suspicious transaction patterns detected by the
          temporal pattern engine.
        </p>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">

        <div className="rounded-lg border border-border p-4">
          <div className="text-xs text-muted uppercase tracking-wide">
            Pattern Events
          </div>

          <div className="text-2xl font-bold mt-1">
            {totalEvents.toLocaleString("en-IN")}
          </div>

          <div className="text-xs text-muted mt-1">
            returned by pattern API
          </div>
        </div>

        <div className="rounded-lg border border-border p-4">
          <div className="text-xs text-muted uppercase tracking-wide">
            Pattern Types
          </div>

          <div className="text-2xl font-bold mt-1">
            {uniqueTypes}
          </div>

          <div className="text-xs text-muted mt-1">
            distinct suspicious behaviours
          </div>
        </div>

        <div className="rounded-lg border border-border p-4">
          <div className="text-xs text-muted uppercase tracking-wide">
            Most Frequent
          </div>

          <div className="text-lg font-bold mt-1">
            {mostCommon
              ? mostCommon.label
              : "—"}
          </div>

          <div className="text-xs text-muted mt-1">
            {mostCommon
              ? `${mostCommon.count.toLocaleString("en-IN")} events`
              : ""}
          </div>
        </div>

        <div className="rounded-lg border border-border p-4">
          <div className="text-xs text-muted uppercase tracking-wide">
            Structural / Temporal
          </div>

          <div className="text-lg font-bold mt-1">
            {structuralCount.toLocaleString("en-IN")}
            {" / "}
            {temporalCount.toLocaleString("en-IN")}
          </div>

          <div className="text-xs text-muted mt-1">
            event categories
          </div>
        </div>

      </div>

      {/* Main chart */}
      <Card title="Pattern Distribution">

        <div className="h-[360px]">

          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
                margin={{
                  top: 10,
                  right: 20,
                  left: 0,
                  bottom: 50,
                }}
              >

                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="#232838"
                />

                <XAxis
                  dataKey="label"
                  angle={-25}
                  textAnchor="end"
                  interval={0}
                  height={70}
                  tick={{
                    fill: "#8b93a7",
                    fontSize: 11,
                  }}
                />

                <YAxis
                  tick={{
                    fill: "#8b93a7",
                    fontSize: 11,
                  }}
                />

                <Tooltip
                  formatter={(value) => [
                    Number(value).toLocaleString("en-IN"),
                    "Events",
                  ]}
                  contentStyle={{
                    background: "#131722",
                    border: "1px solid #232838",
                    borderRadius: "6px",
                  }}
                  labelStyle={{
                    color: "#ffffff",
                  }}
                />

                <Bar
                  dataKey="count"
                  name="Pattern Events"
                  radius={[4, 4, 0, 0]}
                >
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.type}
                      fill="#3b82f6"
                    />
                  ))}
                </Bar>

              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-sm text-muted">
              No pattern events available.
            </div>
          )}

        </div>

        <p className="text-xs text-muted mt-3">
          Distribution is calculated from all pattern records returned by
          the API, rather than displaying only the first 500 events.
        </p>

      </Card>

      {/* Detailed table */}
      <Card title="Pattern Breakdown">

        <div className="overflow-x-auto">

          <table className="w-full text-sm">

            <thead className="text-muted text-left bg-muted/5">
              <tr>
                <th className="px-3 py-3">
                  Pattern
                </th>

                <th className="px-3 py-3">
                  Events
                </th>

                <th className="px-3 py-3">
                  Share
                </th>

                <th className="px-3 py-3">
                  Category
                </th>
              </tr>
            </thead>

            <tbody>

              {chartData.map((item) => {

                const percentage =
                  totalEvents > 0
                    ? (item.count / totalEvents) * 100
                    : 0;

                const category = structuralTypes.includes(item.type)
                  ? "Structural"
                  : temporalTypes.includes(item.type)
                  ? "Temporal"
                  : "Other";

                return (
                  <tr
                    key={item.type}
                    className="border-t border-border"
                  >

                    <td className="px-3 py-3 font-medium">
                      {item.label}
                    </td>

                    <td className="px-3 py-3">
                      {item.count.toLocaleString("en-IN")}
                    </td>

                    <td className="px-3 py-3">
                      {percentage.toFixed(2)}%
                    </td>

                    <td className="px-3 py-3">
                      <span className="rounded-md border border-border px-2 py-1 text-xs">
                        {category}
                      </span>
                    </td>

                  </tr>
                );
              })}

            </tbody>

          </table>

        </div>

      </Card>

      {/* Research interpretation */}
      <Card title="Pattern Interpretation">

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

          <div className="rounded-lg border border-border p-4">

            <div className="text-sm font-semibold">
              Structural patterns
            </div>

            <p className="text-xs text-muted mt-2 leading-relaxed">
              Fan-in, fan-out, layering and split/merge patterns describe
              how accounts are structurally connected through transaction
              flows.
            </p>

          </div>

          <div className="rounded-lg border border-border p-4">

            <div className="text-sm font-semibold">
              Temporal patterns
            </div>

            <p className="text-xs text-muted mt-2 leading-relaxed">
              Circular flows, rapid pass-through, repeated intermediaries
              and connectivity escalation capture suspicious behaviour
              that evolves over time.
            </p>

          </div>

        </div>

      </Card>

      {/* Disclaimer */}
      <div className="rounded-lg border border-border px-4 py-3">

        <div className="text-xs font-semibold uppercase tracking-wide">
          Interpretation
        </div>

        <p className="text-xs text-muted mt-1 leading-relaxed">
          Pattern detection identifies transaction behaviours associated
          with suspicious activity. Individual patterns are not proof of
          money laundering and should be interpreted together with temporal,
          network and transaction-level evidence.
        </p>

      </div>

    </div>
  );
}