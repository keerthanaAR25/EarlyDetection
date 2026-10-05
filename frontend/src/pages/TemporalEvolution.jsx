import React from "react";
import { api } from "../api.js";
import {
  Card,
  Loading,
  ErrorBox,
  useApi,
} from "../components/ui.jsx";

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

function patternLabel(value) {
  return (
    PATTERN_LABELS[value] ||
    String(value || "").replaceAll("_", " ")
  );
}

function parsePatterns(value) {
  if (Array.isArray(value)) return value;

  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed;
    } catch (_) {}

    return value
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
  }

  return [];
}

export default function TemporalEvolution() {
  const { data: ringsData, loading: ringsLoading, error: ringsError } =
    useApi(() => api.rings({ limit: 142 }), []);

  const rings = Array.isArray(ringsData)
    ? ringsData
    : Array.isArray(ringsData?.items)
    ? ringsData.items
    : [];

  const [selectedRing, setSelectedRing] = React.useState("");

  React.useEffect(() => {
    if (!selectedRing && rings.length > 0) {
      setSelectedRing(
        rings[0]?.candidate_ring_id ||
          rings[0]?.ring_id ||
          rings[0]?.candidate_id ||
          ""
      );
    }
  }, [rings, selectedRing]);

  const {
    data,
    loading,
    error,
  } = useApi(
    () =>
      selectedRing
        ? api.ringTimeline(selectedRing)
        : Promise.resolve(null),
    [selectedRing]
  );

  if (ringsLoading) {
    return <Loading text="Loading candidate trajectories..." />;
  }

  if (ringsError) {
    return (
      <ErrorBox
        error={ringsError}
        title="Unable to load candidate rings"
      />
    );
  }

  const timeline = data || {};

  const ring =
    rings.find(
      (item) =>
        (item?.candidate_ring_id ||
          item?.ring_id ||
          item?.candidate_id) === selectedRing
    ) || {};

  const riskScore = Number(
    timeline?.risk_score ??
      ring?.risk_score ??
      0
  );

  const formationStage =
    timeline?.formation_stage ||
    ring?.formation_stage ||
    "WATCH";

  const patterns = parsePatterns(
    timeline?.patterns ||
      timeline?.pattern_sequence ||
      ring?.patterns
  );

  const patternTransitions = parsePatterns(
    timeline?.pattern_transitions
  );

  const windowSpan =
    timeline?.window_span ??
    timeline?.time_span ??
    (
      Array.isArray(timeline?.event_window_ids) &&
      timeline.event_window_ids.length > 0
        ? [
            Math.min(...timeline.event_window_ids),
            Math.max(...timeline.event_window_ids),
          ]
        : "—"
    );

  const firstPattern =
    timeline?.first_suspicious_pattern ||
    patterns[0] ||
    "—";

  const latestPattern =
    timeline?.latest_suspicious_pattern ||
    patterns[patterns.length - 1] ||
    "—";

  const patternCount =
    timeline?.pattern_count ??
    patterns.length ??
    0;

  const patternDiversity =
    timeline?.pattern_diversity ??
    new Set(patterns).size ??
    0;

  if (loading) {
    return <Loading text="Loading temporal evolution..." />;
  }

  if (error) {
    return (
      <ErrorBox
        error={error}
        title="Unable to load temporal evolution"
      />
    );
  }

  return (
    <div className="space-y-6">

      {/* HEADER */}
      <div>
        <h1 className="text-xl font-bold">
          Temporal Evolution
        </h1>

        <p className="text-sm text-muted mt-1">
          Track how suspicious transaction patterns appear and combine
          across temporal graph windows.
        </p>
      </div>

      {/* SELECTOR */}
      <div className="rounded-lg border border-border p-4">
        <label className="block text-xs font-medium text-muted mb-2">
          Candidate Ring
        </label>

        <select
          className="bg-panel border border-border rounded-md px-3 py-2 text-sm w-full"
          value={selectedRing}
          onChange={(e) => setSelectedRing(e.target.value)}
        >
          {rings.map((item, index) => {
            const id =
              item?.candidate_ring_id ||
              item?.ring_id ||
              item?.candidate_id ||
              `candidate-${index}`;

            return (
              <option key={id} value={id}>
                {id} — Risk{" "}
                {Number(item?.risk_score ?? 0).toFixed(1)}
              </option>
            );
          })}
        </select>
      </div>

      {/* SUMMARY */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">

        <div className="rounded-lg border border-border p-4">
          <div className="text-xs text-muted uppercase tracking-wide">
            Candidate
          </div>

          <div className="text-lg font-bold mt-1">
            {selectedRing || "—"}
          </div>
        </div>

        <div className="rounded-lg border border-border p-4">
          <div className="text-xs text-muted uppercase tracking-wide">
            Risk Score
          </div>

          <div className="text-2xl font-bold mt-1">
            {riskScore.toFixed(1)}
          </div>

          <div className="text-xs text-muted mt-1">
            / 100
          </div>
        </div>

        <div className="rounded-lg border border-border p-4">
          <div className="text-xs text-muted uppercase tracking-wide">
            Pattern Events
          </div>

          <div className="text-2xl font-bold mt-1">
            {patternCount}
          </div>
        </div>

        <div className="rounded-lg border border-border p-4">
          <div className="text-xs text-muted uppercase tracking-wide">
            Pattern Diversity
          </div>

          <div className="text-2xl font-bold mt-1">
            {patternDiversity}
          </div>

          <div className="text-xs text-muted mt-1">
            distinct pattern types
          </div>
        </div>

      </div>

      {/* FORMATION */}
      <Card title="Formation Stage">
        <div className="flex items-center gap-3">
          <span className="font-semibold">
            {formationStage}
          </span>

          <span className="text-xs text-muted">
            Analytical evidence maturity
          </span>
        </div>

        <p className="text-xs text-muted mt-3 leading-relaxed">
          Formation stage describes the maturity of detected suspicious
          evidence within the analytical pipeline. It is not legal
          confirmation of a money-laundering ring.
        </p>
      </Card>

      {/* SUSPICIOUS PATTERN SEQUENCE */}
      <Card title="Suspicious Pattern Sequence">

        {patterns.length === 0 ? (
          <div className="py-6 text-sm text-muted">
            No temporal pattern sequence is available for this candidate.
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">

            {patterns.map((pattern, index) => (
              <React.Fragment key={`${pattern}-${index}`}>

                <div className="rounded-lg border border-border bg-panel px-4 py-3">
                  <div className="text-sm font-semibold">
                    {patternLabel(pattern)}
                  </div>

                  <div className="text-xs text-muted mt-1">
                    Pattern {index + 1}
                  </div>
                </div>

                {index < patterns.length - 1 && (
                  <span className="text-muted text-lg">
                    →
                  </span>
                )}

              </React.Fragment>
            ))}

          </div>
        )}

        <p className="text-xs text-muted mt-4 leading-relaxed">
          The sequence represents the chronological ordering of detected
          suspicious pattern events. Multiple patterns may occur within the
          same temporal graph window, so a repeated window identifier does
          not by itself represent a time gap.
        </p>

      </Card>

      {/* PATTERN DETAILS */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        <Card title="First Suspicious Pattern">
          <div className="text-lg font-semibold">
            {patternLabel(firstPattern)}
          </div>

          <p className="text-xs text-muted mt-2">
            Earliest suspicious pattern represented in the candidate
            trajectory.
          </p>
        </Card>

        <Card title="Latest Suspicious Pattern">
          <div className="text-lg font-semibold">
            {patternLabel(latestPattern)}
          </div>

          <p className="text-xs text-muted mt-2">
            Most recent suspicious pattern represented in the candidate
            trajectory.
          </p>
        </Card>

      </div>

      {/* WINDOW SPAN */}
      <Card title="Temporal Window Span">
        <div className="text-lg font-semibold">
          {Array.isArray(windowSpan)
            ? windowSpan.join(" → ")
            : String(windowSpan)}
        </div>

        <p className="text-xs text-muted mt-2">
          Analytical graph-window range associated with the candidate.
          Window identifiers should not automatically be interpreted as
          calendar days.
        </p>
      </Card>

      {/* RESEARCH INTERPRETATION */}
      <Card title="Research Interpretation">

        <p className="text-sm text-muted leading-6">
          Temporal evolution is used to study how suspicious transaction
          behaviours emerge and combine rather than treating each suspicious
          transaction independently. A candidate may contain aggregation,
          pass-through, layering or circular-flow behaviour within the same
          or neighbouring temporal windows.
        </p>

        <p className="text-sm text-muted leading-6 mt-3">
          The objective is to identify formation-stage behavioural evidence
          that can support investigator prioritization before the complete
          financial activity is understood.
        </p>

      </Card>

      {/* DISCLAIMER */}
      <div className="rounded-lg border border-border px-4 py-3">
        <div className="text-xs font-semibold uppercase tracking-wide">
          Important interpretation
        </div>

        <p className="text-xs text-muted mt-1 leading-relaxed">
          Temporal pattern sequences represent analytical evidence generated
          by the detection pipeline. They do not establish that a candidate
          represents confirmed money laundering.
        </p>
      </div>

    </div>
  );
}