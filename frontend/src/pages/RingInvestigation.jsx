import React from "react";
import { api } from "../api.js";
import {
  Card,
  Loading,
  ErrorBox,
  RiskBadge,
  useApi,
} from "../components/ui.jsx";

function formatNumber(value, digits = 1) {
  const n = Number(value);

  if (!Number.isFinite(n)) return "—";

  return n.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatDate(value) {
  if (!value) return "—";

  const d = new Date(value);

  if (Number.isNaN(d.getTime())) {
    return String(value).slice(0, 10);
  }

  return d.toLocaleDateString("en-IN", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

function PatternBadge({ pattern }) {
  return (
    <span className="inline-flex rounded-md border border-border bg-white/5 px-2 py-1 text-xs">
      {String(pattern || "").replaceAll("_", " ")}
    </span>
  );
}

function ScoreBar({ label, value, weight }) {
  const score = Number(value);

  return (
    <div className="space-y-1">

      <div className="flex justify-between text-xs">
        <span className="text-muted">
          {label}
          {weight ? ` (${weight})` : ""}
        </span>

        <span className="font-medium">
          {Number.isFinite(score) ? formatNumber(score) : "—"}
        </span>
      </div>

      <div className="h-2 rounded-full bg-border overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.min(100, Math.max(0, score || 0))}%`,
          }}
        />
      </div>

    </div>
  );
}

function GraphNode({ node }) {
  const data = node?.data || node || {};

  return (
    <tr className="border-t border-border">
      <td className="px-3 py-2 font-mono text-xs">
        {data.id ?? data.account_id ?? "—"}
      </td>

      <td className="px-3 py-2 text-xs">
        {data.label ?? data.type ?? "Account"}
      </td>

      <td className="px-3 py-2 text-xs">
        {data.risk_score != null
          ? formatNumber(data.risk_score)
          : "—"}
      </td>
    </tr>
  );
}

function GraphEdge({ edge }) {
  const data = edge?.data || edge || {};

  return (
    <tr className="border-t border-border">
      <td className="px-3 py-2 font-mono text-xs">
        {data.source ?? data.sender ?? "—"}
      </td>

      <td className="px-3 py-2 font-mono text-xs">
        {data.target ?? data.receiver ?? "—"}
      </td>

      <td className="px-3 py-2">
        {data.amount != null
          ? formatNumber(data.amount, 2)
          : "—"}
      </td>

      <td className="px-3 py-2 text-xs text-muted">
        {formatDate(data.timestamp)}
      </td>
    </tr>
  );
}

export default function RingInvestigation() {
  const { data: rings, loading: ringsLoading, error: ringsError } =
    useApi(() => api.rings({ limit: 142 }), []);

  const [selected, setSelected] = React.useState(null);

  React.useEffect(() => {
    if (rings?.length && !selected) {
      setSelected(rings[0].candidate_ring_id);
    }
  }, [rings, selected]);

  const {
    data: ring,
    loading,
    error,
  } = useApi(
    () =>
      selected
        ? api.ring(selected)
        : Promise.resolve(null),
    [selected]
  );

  const {
    data: graph,
    loading: graphLoading,
  } = useApi(
    () =>
      selected
        ? api.ringGraph(selected)
        : Promise.resolve(null),
    [selected]
  );

  if (ringsLoading) return <Loading />;
  if (ringsError) return <ErrorBox error={ringsError} />;

  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];

  const riskScore = Number(ring?.risk_score);

  const behavioural =
    ring?.behavioural_score ??
    ring?.risk_components?.behavioural ??
    ring?.risk_breakdown?.behavioural;

  const network =
    ring?.network_score ??
    ring?.risk_components?.network ??
    ring?.risk_breakdown?.network;

  const fundFlow =
    ring?.fund_flow_score ??
    ring?.risk_components?.fund_flow ??
    ring?.risk_breakdown?.fund_flow;

  const persistence =
    ring?.persistence_score ??
    ring?.risk_components?.persistence ??
    ring?.risk_breakdown?.persistence;

  const patterns = Array.isArray(ring?.patterns)
    ? ring.patterns
    : [];

  return (
    <div className="space-y-5">

      {/* PAGE HEADER */}
      <div>
        <h1 className="text-xl font-bold">
          Ring Investigation
        </h1>

        <p className="text-sm text-muted mt-1">
          Examine the temporal, network and transaction evidence
          associated with a suspicious-ring candidate.
        </p>
      </div>

      {/* RING SELECTOR */}
      <div className="rounded-lg border border-border p-3">

        <div className="text-xs text-muted uppercase tracking-wide mb-2">
          Select candidate
        </div>

        <div className="flex gap-2 flex-wrap max-h-32 overflow-y-auto">

          {(rings || []).map((r) => (
            <button
              key={r.candidate_ring_id}
              onClick={() =>
                setSelected(r.candidate_ring_id)
              }
              className={`px-3 py-1.5 rounded-md text-xs border transition-colors ${
                selected === r.candidate_ring_id
                  ? "border-accent text-accent bg-accent/5"
                  : "border-border text-muted hover:text-white"
              }`}
            >
              {r.candidate_ring_id}
            </button>
          ))}

        </div>

      </div>

      {loading && <Loading />}

      {error && <ErrorBox error={error} />}

      {ring && (
        <div className="space-y-5">

          {/* TOP SUMMARY */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">

            <Card title="Risk Score">
              <div className="text-3xl font-bold">
                {Number.isFinite(riskScore)
                  ? riskScore.toFixed(1)
                  : "—"}
              </div>

              <div className="mt-2">
                <RiskBadge
                  level={
                    ring.risk_level ||
                    (riskScore >= 75
                      ? "CRITICAL"
                      : riskScore >= 50
                      ? "HIGH"
                      : riskScore >= 25
                      ? "MODERATE"
                      : "LOW")
                  }
                />
              </div>
            </Card>

            <Card title="Formation Stage">
              <div className="text-lg font-semibold">
                {ring.formation_stage || "—"}
              </div>

              <div className="text-xs text-muted mt-2">
                Evidence maturity indicator
              </div>
            </Card>

            <Card title="Accounts">
              <div className="text-3xl font-bold">
                {ring.n_accounts ?? "—"}
              </div>

              <div className="text-xs text-muted mt-1">
                linked accounts
              </div>
            </Card>

            <Card title="Transactions">
              <div className="text-3xl font-bold">
                {ring.transaction_ids?.length ??
                  ring.n_transactions ??
                  "—"}
              </div>

              <div className="text-xs text-muted mt-1">
                associated transactions
              </div>
            </Card>

          </div>

          {/* TIME + PATTERNS */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

            <Card title="Formation Window">

              <div className="text-sm font-medium">
                {formatDate(ring.time_span?.[0])}
                {" → "}
                {formatDate(ring.time_span?.[1])}
              </div>

              {ring.time_span?.length === 2 && (
                <div className="text-xs text-muted mt-2">
                  Candidate activity period
                </div>
              )}

            </Card>

            <Card title="Detected Patterns">

              {patterns.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {patterns.map((p) => (
                    <PatternBadge
                      key={p}
                      pattern={p}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-sm text-muted">
                  No pattern details available.
                </div>
              )}

            </Card>

          </div>

          {/* RISK BREAKDOWN */}
          <Card title="Explainable Risk Breakdown">

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

              <ScoreBar
                label="Behavioural"
                value={behavioural}
                weight="35%"
              />

              <ScoreBar
                label="Network"
                value={network}
                weight="20%"
              />

              <ScoreBar
                label="Fund Flow"
                value={fundFlow}
                weight="25%"
              />

              <ScoreBar
                label="Persistence"
                value={persistence}
                weight="20%"
              />

            </div>

            <div className="text-xs text-muted mt-4">
              Risk score combines behavioural, network, fund-flow
              and persistence evidence. Component values are shown
              when supplied by the backend.
            </div>

          </Card>

          {/* GRAPH */}
          <Card title="Evidence Network">

            {graphLoading ? (
              <Loading />
            ) : graph ? (
              <div className="space-y-4">

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">

                  <div className="rounded-md border border-border p-3">
                    <div className="text-xs text-muted">
                      Nodes
                    </div>

                    <div className="text-xl font-bold mt-1">
                      {nodes.length}
                    </div>
                  </div>

                  <div className="rounded-md border border-border p-3">
                    <div className="text-xs text-muted">
                      Edges
                    </div>

                    <div className="text-xl font-bold mt-1">
                      {edges.length}
                    </div>
                  </div>

                  <div className="rounded-md border border-border p-3">
                    <div className="text-xs text-muted">
                      Directed flow
                    </div>

                    <div className="text-xl font-bold mt-1">
                      Yes
                    </div>
                  </div>

                  <div className="rounded-md border border-border p-3">
                    <div className="text-xs text-muted">
                      Evidence source
                    </div>

                    <div className="text-sm font-medium mt-1">
                      Candidate subgraph
                    </div>
                  </div>

                </div>

                {/* NODE TABLE */}
                {nodes.length > 0 && (
                  <div>

                    <div className="text-xs font-semibold uppercase tracking-wide mb-2">
                      Accounts in evidence graph
                    </div>

                    <div className="rounded-md border border-border overflow-hidden">

                      <div className="max-h-64 overflow-auto">

                        <table className="w-full text-sm">

                          <thead className="bg-muted/5 text-muted text-left sticky top-0">
                            <tr>
                              <th className="px-3 py-2">
                                Account
                              </th>

                              <th className="px-3 py-2">
                                Type
                              </th>

                              <th className="px-3 py-2">
                                Risk
                              </th>
                            </tr>
                          </thead>

                          <tbody>
                            {nodes.map((node, index) => (
                              <GraphNode
                                key={
                                  node?.data?.id ||
                                  node?.id ||
                                  index
                                }
                                node={node}
                              />
                            ))}
                          </tbody>

                        </table>

                      </div>

                    </div>

                  </div>
                )}

                {/* EDGE TABLE */}
                {edges.length > 0 && (
                  <div>

                    <div className="text-xs font-semibold uppercase tracking-wide mb-2">
                      Transaction flows
                    </div>

                    <div className="rounded-md border border-border overflow-hidden">

                      <div className="max-h-72 overflow-auto">

                        <table className="w-full text-sm">

                          <thead className="bg-muted/5 text-muted text-left sticky top-0">
                            <tr>
                              <th className="px-3 py-2">
                                Sender
                              </th>

                              <th className="px-3 py-2">
                                Receiver
                              </th>

                              <th className="px-3 py-2">
                                Amount
                              </th>

                              <th className="px-3 py-2">
                                Time
                              </th>
                            </tr>
                          </thead>

                          <tbody>
                            {edges.map((edge, index) => (
                              <GraphEdge
                                key={
                                  edge?.data?.id ||
                                  edge?.id ||
                                  index
                                }
                                edge={edge}
                              />
                            ))}
                          </tbody>

                        </table>

                      </div>

                    </div>

                  </div>
                )}

                {nodes.length === 0 &&
                  edges.length === 0 && (
                    <div className="text-sm text-muted">
                      The backend returned no evidence-network
                      elements for this candidate.
                    </div>
                  )}

              </div>
            ) : (
              <div className="text-sm text-muted">
                No evidence graph is available for this candidate.
              </div>
            )}

          </Card>

          {/* TRANSACTION EVIDENCE */}
          <Card title="Transaction Evidence">

            {Array.isArray(ring.transaction_ids) &&
            ring.transaction_ids.length > 0 ? (
              <div>

                <div className="text-xs text-muted mb-3">
                  {ring.transaction_ids.length} transaction IDs
                  associated with this candidate.
                </div>

                <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto">

                  {ring.transaction_ids.map((id) => (
                    <span
                      key={id}
                      className="font-mono text-xs rounded-md border border-border px-2 py-1"
                    >
                      {id}
                    </span>
                  ))}

                </div>

              </div>
            ) : (
              <div className="text-sm text-muted">
                No transaction-level evidence IDs are available.
              </div>
            )}

          </Card>

          {/* INVESTIGATOR INTERPRETATION */}
          <Card title="Investigator Interpretation">

            <div className="space-y-3 text-sm">

              <div>
                <span className="font-medium">
                  Candidate:
                </span>{" "}
                {ring.candidate_ring_id}
              </div>

              <div>
                <span className="font-medium">
                  Observed patterns:
                </span>{" "}
                {patterns.length > 0
                  ? patterns.join(", ")
                  : "None available"}
              </div>

              <div>
                <span className="font-medium">
                  Network evidence:
                </span>{" "}
                {nodes.length} accounts connected through{" "}
                {edges.length} observed transaction flows.
              </div>

              <div className="text-muted leading-relaxed">
                This candidate represents a computationally detected
                suspicious transaction-ring hypothesis. Investigators
                should review the underlying transactions, temporal
                sequence and network relationships before drawing
                conclusions.
              </div>

            </div>

          </Card>

          {/* DISCLAIMER */}
          <div className="rounded-lg border border-border px-4 py-3">

            <div className="text-xs font-semibold uppercase tracking-wide">
              Important
            </div>

            <p className="text-xs text-muted mt-1 leading-relaxed">
              Risk scores and formation stages are analytical decision-support
              outputs. They indicate suspicious behavioural evidence and
              investigation priority; they do not constitute legal proof or
              a confirmed finding of money laundering.
            </p>

          </div>

        </div>
      )}

    </div>
  );
}