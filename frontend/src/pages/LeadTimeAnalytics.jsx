import React from "react";
import { api } from "../api.js";
import {
  Card,
  Loading,
  ErrorBox,
  useApi,
} from "../components/ui.jsx";

function formatNumber(value, digits = 1) {
  const n = Number(value);

  if (!Number.isFinite(n)) return "—";

  return n.toFixed(digits);
}

function formatPercent(value, digits = 1) {
  const n = Number(value);

  if (!Number.isFinite(n)) return "—";

  return `${(n * 100).toFixed(digits)}%`;
}

export default function LeadTimeAnalytics() {
  const { data, loading, error } = useApi(
    () => api.leadTime(),
    []
  );

  if (loading) {
    return <Loading text="Loading early-warning evaluation..." />;
  }

  if (error) {
    return (
      <ErrorBox
        error={error}
        title="Unable to load lead-time evaluation"
      />
    );
  }

  const result = data || {};

  const groundTruthRings =
    Number(result?.ground_truth_rings ?? 100);

  const candidates =
    Number(result?.n_candidates ?? 142);

  const strictMatches =
    Number(result?.n_strong_matches ?? result?.n_matched_to_ground_truth ?? 2);

  const alertedCandidates =
    Number(result?.n_alerted_candidates ?? 89);

  const alertedAndMatched =
    Number(result?.n_alerted_and_matched ?? 1);

  const uniqueDetected =
    Number(result?.unique_ground_truth_rings_detected ?? 1);

  const ringDetectionRate =
    Number(result?.ring_detection_rate ?? 0.01);

  const earlyDetectionRate =
    Number(result?.early_detection_rate ?? 0);

  const meanLeadTime =
    Number(result?.mean_lead_time_windows ?? -23);

  const medianLeadTime =
    Number(result?.median_lead_time_windows ?? -23);

  const falseWarningRate =
    Number(
      result?.false_warning_rate_candidates ??
        result?.extended_false_warning_rate_candidates ??
        0.989
    );

  const completionLeadTime =
    result?.completion_mean_lead_time_windows ??
    result?.extended_mean_lead_time_windows;

  return (
    <div className="space-y-6">

      {/* HEADER */}
      <div>
        <h1 className="text-xl font-bold">
          Early-Warning Evaluation
        </h1>

        <p className="text-sm text-muted mt-1">
          Evaluation of candidate formation and warning timing against
          AMLSim alert events.
        </p>
      </div>

      {/* EVALUATION SCOPE */}
      <Card title="Evaluation Scope">

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">

          <div>
            <div className="text-xs text-muted uppercase tracking-wide">
              AMLSim alerts
            </div>

            <div className="text-2xl font-bold mt-1">
              {groundTruthRings}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted uppercase tracking-wide">
              Candidate rings
            </div>

            <div className="text-2xl font-bold mt-1">
              {candidates}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted uppercase tracking-wide">
              Strict matches
            </div>

            <div className="text-2xl font-bold mt-1">
              {strictMatches}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted uppercase tracking-wide">
              Alerted + matched
            </div>

            <div className="text-2xl font-bold mt-1">
              {alertedAndMatched}
            </div>
          </div>

        </div>

      </Card>

      {/* PRIMARY METRICS */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        <Card title="Ring Detection Rate">
          <div className="text-3xl font-bold">
            {formatPercent(ringDetectionRate)}
          </div>

          <div className="text-xs text-muted mt-2">
            Unique AMLSim ground-truth rings detected under the
            strict matching rule
          </div>
        </Card>

        <Card title="Early Detection Rate">
          <div className="text-3xl font-bold">
            {formatPercent(earlyDetectionRate)}
          </div>

          <div className="text-xs text-muted mt-2">
            Matches where the candidate warning occurred before the
            defined observable event
          </div>
        </Card>

        <Card title="Unmatched Candidate Warning Rate">
          <div className="text-3xl font-bold">
            {formatPercent(falseWarningRate)}
          </div>

          <div className="text-xs text-muted mt-2">
            Candidate-level linkage statistic, not a production ML
            false-positive rate
          </div>
        </Card>

      </div>

      {/* LEAD TIME */}
      <Card title="Warning Lead Time">

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

          <div>
            <div className="text-xs text-muted uppercase tracking-wide">
              Mean lead time
            </div>

            <div className="text-3xl font-bold mt-1">
              {formatNumber(meanLeadTime, 0)}
            </div>

            <div className="text-xs text-muted mt-1">
              temporal graph windows
            </div>
          </div>

          <div>
            <div className="text-xs text-muted uppercase tracking-wide">
              Median lead time
            </div>

            <div className="text-3xl font-bold mt-1">
              {formatNumber(medianLeadTime, 0)}
            </div>

            <div className="text-xs text-muted mt-1">
              temporal graph windows
            </div>
          </div>

        </div>

        <div className="mt-5 rounded-lg border border-border bg-panel px-4 py-4">

          <div className="font-semibold text-sm">
            How to interpret −23 windows
          </div>

          <p className="text-sm text-muted mt-2 leading-6">
            Negative lead time means that, for the matched candidate under
            the current evaluation procedure, the warning occurred after
            the defined AMLSim observable event by 23 analytical graph
            windows.
          </p>

          <p className="text-sm text-muted mt-2 leading-6">
            A graph window is the evaluation unit used by the temporal
            pipeline. It should not automatically be interpreted as one
            calendar day.
          </p>

        </div>

      </Card>

      {/* CURRENT EXPERIMENTAL RESULT */}
      <Card title="Current Experimental Result">

        <div className="rounded-lg border border-border px-4 py-4">

          <div className="font-semibold">
            No positive early-warning detections were established under
            the current strict candidate-to-ground-truth matching rule.
          </div>

          <p className="text-sm text-muted mt-3 leading-6">
            The result indicates that the current ring-candidate
            aggregation does not yet recover enough of the AMLSim alert
            lifecycle to demonstrate reliable advance warning.
          </p>

          <p className="text-sm text-muted mt-3 leading-6">
            This is reported as an experimental limitation rather than
            being presented as successful early-warning performance.
          </p>

        </div>

      </Card>

      {/* LINKAGE */}
      <Card title="Ground-Truth Linkage">

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

          <div>
            <div className="text-xs text-muted uppercase tracking-wide">
              Strict matches
            </div>

            <div className="text-2xl font-bold mt-1">
              {strictMatches}
            </div>

            <div className="text-xs text-muted mt-1">
              candidate / alert linkages
            </div>
          </div>

          <div>
            <div className="text-xs text-muted uppercase tracking-wide">
              Unique ground-truth rings detected
            </div>

            <div className="text-2xl font-bold mt-1">
              {uniqueDetected}
            </div>

            <div className="text-xs text-muted mt-1">
              out of {groundTruthRings}
            </div>
          </div>

          <div>
            <div className="text-xs text-muted uppercase tracking-wide">
              Alerted candidates
            </div>

            <div className="text-2xl font-bold mt-1">
              {alertedCandidates}
            </div>

            <div className="text-xs text-muted mt-1">
              crossed the configured alert threshold
            </div>
          </div>

        </div>

      </Card>

      {/* FALSE WARNING EXPLANATION */}
      <Card title="Why the 98.9% Figure Must Be Interpreted Carefully">

        <p className="text-sm text-muted leading-6">
          The current candidate-to-ground-truth linkage is sparse. Only a
          small number of generated candidate rings satisfy the strict
          matching rule against the AMLSim alert events.
        </p>

        <p className="text-sm text-muted mt-3 leading-6">
          Therefore, the {formatPercent(falseWarningRate)} statistic should
          not be interpreted as the false-positive rate of the account-level
          machine-learning model or as a production banking false-warning
          rate.
        </p>

      </Card>

      {/* SECONDARY COMPLETION VIEW */}
      {completionLeadTime !== undefined && (
        <Card title="Completion-Based Secondary View">

          <div className="text-2xl font-bold">
            {formatNumber(completionLeadTime, 0)}
          </div>

          <div className="text-xs text-muted mt-1">
            mean windows relative to the latest known alert transaction
          </div>

          <p className="text-sm text-muted mt-3 leading-6">
            This secondary view characterizes warning timing relative to
            the end of the known AMLSim alert lifecycle and is reported
            separately from the primary observable-event evaluation.
          </p>

        </Card>
      )}

      {/* RESEARCH INTERPRETATION */}
      <Card title="Research Interpretation">

        <p className="text-sm text-muted leading-6">
          Lead-time evaluation is one research objective of the framework,
          not the sole novelty of the work. The system evaluates whether
          formation-stage suspicious trajectories can become actionable
          before a corresponding known AML event.
        </p>

        <p className="text-sm text-muted mt-3 leading-6">
          The current result demonstrates the complete evaluation mechanism
          while also identifying candidate-to-ground-truth aggregation as
          an important limitation for future improvement.
        </p>

      </Card>

      {/* METHODOLOGY */}
      <Card title="Evaluation Methodology">

        <ul className="text-sm text-muted leading-6 space-y-2 list-disc pl-5">
          <li>
            Ground truth is derived from the AMLSim alert transactions.
          </li>

          <li>
            Strict matching requires shared participant accounts together
            with overlapping transaction intervals.
          </li>

          <li>
            Warning timing is measured using temporal graph windows.
          </li>

          <li>
            Positive lead time means an earlier warning; negative lead time
            means a later warning.
          </li>

          <li>
            The evaluation does not treat unmatched candidates as confirmed
            false laundering cases.
          </li>
        </ul>

      </Card>

      {/* DISCLAIMER */}
      <div className="rounded-lg border border-border px-4 py-3">

        <div className="text-xs font-semibold uppercase tracking-wide">
          Important interpretation
        </div>

        <p className="text-xs text-muted mt-1 leading-relaxed">
          Lead-time results are experimental evaluation metrics for the
          current AMLSim configuration. They should not be interpreted as
          evidence that the system has achieved production-ready early
          warning or as legal confirmation of suspicious activity.
        </p>

      </div>

    </div>
  );
}