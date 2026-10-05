import React from "react";
import { api } from "../api.js";
import { Card, Loading, ErrorBox, useApi } from "../components/ui.jsx";

function PatternBadge({ pattern, windowId, index }) {
  return (
    <div className="flex items-center gap-2">
      <div className="min-w-[170px] rounded-lg border border-border bg-panel px-3 py-2">
        <div className="text-xs text-muted">
          Window {windowId ?? "—"}
        </div>

        <div className="text-sm font-semibold mt-1">
          {String(pattern || "").replaceAll("_", " ")}
        </div>
      </div>

      {index !== undefined && (
        <div className="text-xs text-muted">
          {index + 1}
        </div>
      )}
    </div>
  );
}

function Stage({ pattern }) {
  const p = String(pattern || "").toLowerCase();

  let label = "Suspicious activity";
  let description = "Observed suspicious transaction behaviour.";

  if (p === "fan_in") {
    label = "Aggregation";
    description =
      "Multiple accounts send funds toward a common account.";
  } else if (p === "fan_out") {
    label = "Distribution";
    description =
      "Funds move from one account toward multiple recipients.";
  } else if (p === "layering") {
    label = "Layering";
    description =
      "Funds move through intermediary accounts, increasing flow complexity.";
  } else if (p === "split_merge") {
    label = "Split / Merge";
    description =
      "Transaction flows divide and subsequently converge.";
  } else if (p === "rapid_pass_through") {
    label = "Rapid Movement";
    description =
      "Funds pass through an account within a short time interval.";
  } else if (p === "repeated_intermediary") {
    label = "Repeated Intermediary";
    description =
      "The same intermediary behaviour occurs repeatedly.";
  } else if (p === "circular_flow") {
    label = "Circular Flow";
    description =
      "Funds follow a path that returns toward an originating account.";
  } else if (p === "escalating_connectivity") {
    label = "Connectivity Escalation";
    description =
      "The account's transaction-network connectivity increases over time.";
  }

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="text-xs text-muted uppercase tracking-wide">
        Pattern interpretation
      </div>

      <div className="text-sm font-semibold mt-2">
        {label}
      </div>

      <p className="text-xs text-muted mt-1 leading-relaxed">
        {description}
      </p>
    </div>
  );
}

export default function TemporalEvolution() {
  const { data: rings, loading: ringsLoading, error: ringsError } =
    useApi(() => api.rings({ limit: 142 }), []);

  const [selected, setSelected] = React.useState(null);

  React.useEffect(() => {
    if (rings?.length && !selected) {
      setSelected(rings[0].candidate_ring_id);
    }
  }, [rings, selected]);

  const {
    data: timeline,
    loading,
    error,
  } = useApi(
    () =>
      selected
        ? api.ringTimeline(selected)
        : Promise.resolve(null),
    [selected]
  );

  if (ringsLoading) return <Loading />;
  if (ringsError) return <ErrorBox error={ringsError} />;

  const patterns = timeline?.pattern_sequence || [];
  const windows = timeline?.event_window_ids || [];

  const transitions = patterns
    .map((pattern, index) => {
      if (index === 0) return null;

      return {
        from: patterns[index - 1],
        to: pattern,
        fromWindow: windows[index - 1],
        toWindow: windows[index],
      };
    })
    .filter(Boolean);

  const diversity = new Set(patterns).size;

  return (
    <div className="space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold">
          Temporal Evolution
        </h1>

        <p className="text-sm text-muted mt-1">
          Track how suspicious transaction behaviour evolves across
          temporal graph windows.
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

      {timeline && (
        <div className="space-y-5">

          {/* Summary */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">

            <Card title="Candidate">
              <div className="text-xl font-bold">
                {selected}
              </div>
            </Card>

            <Card title="Pattern Events">
              <div className="text-3xl font-bold">
                {patterns.length}
              </div>

              <div className="text-xs text-muted mt-1">
                suspicious events in trajectory
              </div>
            </Card>

            <Card title="Pattern Diversity">
              <div className="text-3xl font-bold">
                {diversity}
              </div>

              <div className="text-xs text-muted mt-1">
                distinct pattern types
              </div>
            </Card>

            <Card title="Transitions">
              <div className="text-3xl font-bold">
                {transitions.length}
              </div>

              <div className="text-xs text-muted mt-1">
                behavioural transitions
              </div>
            </Card>

          </div>

          {/* Main sequence */}
          <Card title="Suspicious Behaviour Trajectory">

            {patterns.length > 0 ? (
              <div className="space-y-3">

                {patterns.map((pattern, index) => (
                  <div
                    key={`${pattern}-${index}`}
                    className="flex items-center gap-3"
                  >

                    <div className="w-8 h-8 rounded-full border border-accent/40 flex items-center justify-center text-xs text-accent">
                      {index + 1}
                    </div>

                    <PatternBadge
                      pattern={pattern}
                      windowId={windows[index]}
                      index={index}
                    />

                    {index < patterns.length - 1 && (
                      <div className="text-accent text-lg">
                        →
                      </div>
                    )}

                  </div>
                ))}

              </div>
            ) : (
              <div className="text-sm text-muted">
                No temporal pattern sequence is available.
              </div>
            )}

          </Card>

          {/* Transition analysis */}
          <Card title="Pattern Transitions">

            {transitions.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">

                {transitions.map((t, index) => (
                  <div
                    key={`${t.from}-${t.to}-${index}`}
                    className="rounded-lg border border-border p-4"
                  >

                    <div className="text-xs text-muted">
                      Transition {index + 1}
                    </div>

                    <div className="flex items-center gap-2 mt-2">

                      <span className="text-sm font-medium">
                        {String(t.from).replaceAll("_", " ")}
                      </span>

                      <span className="text-accent">
                        →
                      </span>

                      <span className="text-sm font-medium">
                        {String(t.to).replaceAll("_", " ")}
                      </span>

                    </div>

                    <div className="text-xs text-muted mt-2">
                      Window {t.fromWindow ?? "—"} → Window{" "}
                      {t.toWindow ?? "—"}
                    </div>

                  </div>
                ))}

              </div>
            ) : (
              <div className="text-sm text-muted">
                No transitions available for this candidate.
              </div>
            )}

          </Card>

          {/* Current pattern interpretation */}
          {patterns.length > 0 && (
            <Stage pattern={patterns[patterns.length - 1]} />
          )}

          {/* Research interpretation */}
          <Card title="Temporal Interpretation">

            <div className="space-y-3 text-sm">

              <p className="text-muted leading-relaxed">
                Temporal evolution represents the sequence in which
                suspicious transaction patterns emerge across the
                candidate's activity windows. Multiple pattern types
                provide stronger behavioural context than a single
                isolated transaction pattern.
              </p>

              {patterns.length >= 2 && (
                <div className="rounded-md border border-border p-3">

                  <div className="text-xs font-semibold uppercase tracking-wide">
                    Observed evolution
                  </div>

                  <div className="text-sm mt-2">
                    {patterns
                      .map((p) =>
                        String(p).replaceAll("_", " ")
                      )
                      .join(" → ")}
                  </div>

                </div>
              )}

              <p className="text-xs text-muted leading-relaxed">
                These transitions represent analytical evidence of
                changing transaction behaviour. They should be interpreted
                together with transaction-level evidence, network structure
                and the candidate risk score.
              </p>

            </div>

          </Card>

          {/* Disclaimer */}
          <div className="rounded-lg border border-border px-4 py-3">

            <div className="text-xs font-semibold uppercase tracking-wide">
              Important
            </div>

            <p className="text-xs text-muted mt-1 leading-relaxed">
              Temporal pattern evolution indicates suspicious behavioural
              progression within the detected candidate. It does not by
              itself establish intent, criminal activity or confirmed money
              laundering.
            </p>

          </div>

        </div>
      )}

    </div>
  );
}