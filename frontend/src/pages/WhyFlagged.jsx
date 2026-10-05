import React from "react";
import { api } from "../api.js";
import {
  Card,
  Loading,
  ErrorBox,
  RiskBadge,
  useApi,
} from "../components/ui.jsx";

function formatLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function ScoreBar({ label, value, weight }) {
  const score = Number(value);

  return (
    <div className="space-y-2">

      <div className="flex items-center justify-between">
        <span className="text-sm">
          {formatLabel(label)}
        </span>

        <span className="text-sm font-semibold">
          {Number.isFinite(score) ? score.toFixed(1) : "—"}
        </span>
      </div>

      <div className="h-2 rounded-full bg-border overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{
            width: `${Math.min(
              100,
              Math.max(0, Number.isFinite(score) ? score : 0)
            )}%`,
          }}
        />
      </div>

      {weight && (
        <div className="text-xs text-muted">
          Contribution weight: {weight}
        </div>
      )}

    </div>
  );
}

export default function WhyFlagged() {
  const {
    data: rings,
    loading: ringsLoading,
    error: ringsError,
  } = useApi(() => api.rings({ limit: 142 }), []);

  const [selected, setSelected] = React.useState(null);

  React.useEffect(() => {
    if (rings?.length && !selected) {
      setSelected(rings[0].candidate_ring_id);
    }
  }, [rings, selected]);

  const {
    data: exp,
    loading,
    error,
  } = useApi(
    () =>
      selected
        ? api.ringExplanation(selected)
        : Promise.resolve(null),
    [selected]
  );

  if (ringsLoading) return <Loading />;
  if (ringsError) return <ErrorBox error={ringsError} />;

  const components = exp?.score_components || {};
  const factors = Array.isArray(exp?.top_factors)
    ? exp.top_factors
    : [];

  return (
    <div className="space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold">
          Why Flagged?
        </h1>

        <p className="text-sm text-muted mt-1">
          Explainable breakdown of the evidence contributing to a
          candidate's risk score.
        </p>
      </div>

      {/* Candidate selector */}
      <div className="rounded-lg border border-border p-3">

        <div className="text-xs text-muted uppercase tracking-wide mb-2">
          Candidate ring
        </div>

        <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">

          {(rings || []).map((r) => (
            <button
              key={r.candidate_ring_id}
              onClick={() =>
                setSelected(r.candidate_ring_id)
              }
              className={`px-3 py-1.5 rounded-md text-xs border ${
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

      {exp && (
        <div className="space-y-5">

          {/* Risk summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

            <Card title="Overall Risk Score">

              <div className="text-4xl font-bold">
                {Number.isFinite(Number(exp.risk_score))
                  ? Number(exp.risk_score).toFixed(1)
                  : "—"}
                <span className="text-lg text-muted">
                  /100
                </span>
              </div>

              <div className="mt-3">
                <RiskBadge
                  level={
                    exp.risk_level ||
                    (
                      Number(exp.risk_score) >= 75
                        ? "CRITICAL"
                        : Number(exp.risk_score) >= 50
                        ? "HIGH"
                        : Number(exp.risk_score) >= 25
                        ? "MODERATE"
                        : "LOW"
                    )
                  }
                />
              </div>

            </Card>

            <Card title="Candidate">

              <div className="text-2xl font-bold">
                {selected}
              </div>

              <div className="text-xs text-muted mt-2">
                Suspicious-ring candidate under investigation
              </div>

            </Card>

            <Card title="Explanation Status">

              <div className="text-lg font-semibold">
                Evidence-linked
              </div>

              <div className="text-xs text-muted mt-2">
                Behavioural, network, fund-flow and persistence
                signals are considered by the scoring framework.
              </div>

            </Card>

          </div>

          {/* Score components */}
          <Card title="Risk Score Components">

            <div className="space-y-5">

              <ScoreBar
                label="Behavioural"
                value={
                  components.behavioural ??
                  components.behavioral
                }
                weight="35%"
              />

              <ScoreBar
                label="Network"
                value={components.network}
                weight="20%"
              />

              <ScoreBar
                label="Fund Flow"
                value={
                  components.fund_flow ??
                  components.fundFlow
                }
                weight="25%"
              />

              <ScoreBar
                label="Persistence"
                value={components.persistence}
                weight="20%"
              />

            </div>

            <div className="mt-5 rounded-md border border-border p-3">

              <div className="text-xs font-semibold uppercase tracking-wide">
                Scoring framework
              </div>

              <p className="text-xs text-muted mt-2 leading-relaxed">
                The overall risk score combines four evidence dimensions:
                behavioural evidence, transaction-network structure,
                suspicious fund-flow patterns and persistence of suspicious
                activity across time.
              </p>

            </div>

          </Card>

          {/* Top factors */}
          <Card title="Top Contributing Factors">

            {factors.length > 0 ? (
              <div className="space-y-3">

                {factors.map((factor, index) => (
                  <div
                    key={index}
                    className="flex gap-3 rounded-lg border border-border p-3"
                  >

                    <div className="flex-shrink-0 w-7 h-7 rounded-full border border-accent/30 flex items-center justify-center text-xs text-accent">
                      {index + 1}
                    </div>

                    <div className="text-sm leading-relaxed">
                      {typeof factor === "string"
                        ? factor
                        : factor?.description ||
                          factor?.name ||
                          JSON.stringify(factor)}
                    </div>

                  </div>
                ))}

              </div>
            ) : (
              <div className="text-sm text-muted">
                No top-factor explanation was returned by the backend.
              </div>
            )}

          </Card>

          {/* How to interpret */}
          <Card title="How to Interpret This Score">

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">

              <div className="rounded-lg border border-border p-4">
                <div className="text-sm font-semibold">
                  Behavioural
                </div>

                <p className="text-xs text-muted mt-2 leading-relaxed">
                  Captures account-level transaction behaviour and
                  predictive model signals.
                </p>
              </div>

              <div className="rounded-lg border border-border p-4">
                <div className="text-sm font-semibold">
                  Network
                </div>

                <p className="text-xs text-muted mt-2 leading-relaxed">
                  Captures structural characteristics of the transaction
                  network surrounding the candidate.
                </p>
              </div>

              <div className="rounded-lg border border-border p-4">
                <div className="text-sm font-semibold">
                  Fund Flow + Persistence
                </div>

                <p className="text-xs text-muted mt-2 leading-relaxed">
                  Captures suspicious flow patterns and whether suspicious
                  behaviour persists across temporal windows.
                </p>
              </div>

            </div>

          </Card>

          {/* Decision support */}
          <div className="rounded-lg border border-border p-4">

            <div className="text-xs font-semibold uppercase tracking-wide">
              Investigator guidance
            </div>

            <p className="text-sm mt-2 leading-relaxed">
              Use the risk score to prioritize investigation, then verify
              the underlying transaction evidence, temporal pattern
              trajectory and network relationships before making a decision.
            </p>

          </div>

          {/* Disclaimer */}
          <div className="rounded-lg border border-border px-4 py-3">

            <div className="text-xs font-semibold uppercase tracking-wide">
              Important
            </div>

            <p className="text-xs text-muted mt-1 leading-relaxed">
              A risk score is an analytical prioritization signal. A high
              score does not establish that money laundering occurred and
              should not be treated as a legal or regulatory conclusion.
            </p>

            {exp.disclaimer && (
              <p className="text-xs text-muted mt-2">
                {exp.disclaimer}
              </p>
            )}

          </div>

        </div>
      )}

    </div>
  );
}