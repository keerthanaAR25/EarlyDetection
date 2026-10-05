import React from "react";
import { api } from "../api.js";
import { Card, Loading, ErrorBox, useApi } from "../components/ui.jsx";

function formatMetric(value, digits = 4) {
  const n = Number(value);

  if (!Number.isFinite(n)) return "—";

  return n.toFixed(digits);
}

function formatPercent(value) {
  const n = Number(value);

  if (!Number.isFinite(n)) return "—";

  return `${(n * 100).toFixed(2)}%`;
}

function MetricCard({ label, value, description }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="text-xs text-muted uppercase tracking-wide">
        {label}
      </div>

      <div className="text-2xl font-bold mt-1">
        {value}
      </div>

      {description && (
        <div className="text-xs text-muted mt-1 leading-relaxed">
          {description}
        </div>
      )}
    </div>
  );
}

function MethodBadge({ method }) {
  const proposed = method.toLowerCase().includes("proposed");

  return (
    <span
      className={`inline-flex rounded-md border px-2 py-1 text-xs ${
        proposed
          ? "border-accent/30 bg-accent/10 text-accent"
          : "border-border text-muted"
      }`}
    >
      {proposed ? "Proposed" : "Baseline"}
    </span>
  );
}

export default function ModelPerformance() {
  const {
    data,
    loading,
    error,
  } = useApi(() => api.metrics(), []);

  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;

  const metrics = data || {};
  const entries = Object.entries(metrics);

  const proposedEntry =
    entries.find(([method]) =>
      method.toLowerCase().includes("proposed")
    ) || null;

  const proposedTest =
    proposedEntry?.[1]?.test || {};

  return (
    <div className="space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold">
          Model Performance
        </h1>

        <p className="text-sm text-muted mt-1">
          Held-out evaluation of account-window suspicious-activity
          forecasting models.
        </p>
      </div>

      {/* Important evaluation context */}
      <div className="rounded-lg border border-border p-4">

        <div className="text-xs font-semibold uppercase tracking-wide">
          Evaluation context
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3">

          <div>
            <div className="text-xs text-muted">
              Test observations
            </div>

            <div className="text-lg font-bold">
              653,487
            </div>
          </div>

          <div>
            <div className="text-xs text-muted">
              Positive observations
            </div>

            <div className="text-lg font-bold">
              32
            </div>
          </div>

          <div>
            <div className="text-xs text-muted">
              Positive rate
            </div>

            <div className="text-lg font-bold">
              0.0049%
            </div>
          </div>

        </div>

        <p className="text-xs text-muted mt-3 leading-relaxed">
          The test set is extremely imbalanced. Precision, recall, F1 and
          especially PR-AUC should therefore be interpreted together rather
          than relying on accuracy alone.
        </p>

      </div>

      {/* Proposed model summary */}
      {proposedEntry && (
        <Card title="Proposed Early-Warning Model — Test Set">

          <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-6 gap-3">

            <MetricCard
              label="Precision"
              value={formatMetric(proposedTest.precision)}
              description="Correct positive predictions"
            />

            <MetricCard
              label="Recall"
              value={formatMetric(proposedTest.recall)}
              description="Positive cases detected"
            />

            <MetricCard
              label="F1"
              value={formatMetric(proposedTest.f1)}
              description="Precision-recall balance"
            />

            <MetricCard
              label="ROC-AUC"
              value={formatMetric(proposedTest.roc_auc)}
              description="Ranking discrimination"
            />

            <MetricCard
              label="PR-AUC"
              value={formatMetric(proposedTest.pr_auc)}
              description="More informative under imbalance"
            />

            <MetricCard
              label="False Warning"
              value={formatMetric(proposedTest.false_warning_rate)}
              description="Negative observations flagged"
            />

          </div>

        </Card>
      )}

      {/* Model comparison */}
      <Card title="Held-Out Test Performance">

        <div className="overflow-x-auto">

          <table className="w-full text-sm">

            <thead className="text-muted text-left bg-muted/5">
              <tr>
                <th className="px-3 py-3">
                  Method
                </th>

                <th className="px-3 py-3">
                  Precision
                </th>

                <th className="px-3 py-3">
                  Recall
                </th>

                <th className="px-3 py-3">
                  F1
                </th>

                <th className="px-3 py-3">
                  ROC-AUC
                </th>

                <th className="px-3 py-3">
                  PR-AUC
                </th>

                <th className="px-3 py-3">
                  False Warning
                </th>
              </tr>
            </thead>

            <tbody>

              {entries.map(([method, splits]) => {

                const m = splits?.test || {};

                return (
                  <tr
                    key={method}
                    className="border-t border-border"
                  >

                    <td className="px-3 py-3">

                      <div className="font-medium">
                        {method}
                      </div>

                      <div className="mt-1">
                        <MethodBadge method={method} />
                      </div>

                    </td>

                    <td className="px-3 py-3">
                      {formatMetric(m.precision)}
                    </td>

                    <td className="px-3 py-3">
                      {formatMetric(m.recall)}
                    </td>

                    <td className="px-3 py-3">
                      {formatMetric(m.f1)}
                    </td>

                    <td className="px-3 py-3 font-medium">
                      {formatMetric(m.roc_auc)}
                    </td>

                    <td className="px-3 py-3 font-medium">
                      {formatMetric(m.pr_auc)}
                    </td>

                    <td className="px-3 py-3">
                      {formatMetric(m.false_warning_rate)}
                    </td>

                  </tr>
                );

              })}

              {entries.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    className="px-3 py-8 text-center text-muted"
                  >
                    No model evaluation results are available.
                  </td>
                </tr>
              )}

            </tbody>

          </table>

        </div>

      </Card>

      {/* Investigator ranking */}
      <Card title="Investigator-Oriented Ranking">

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

          <MetricCard
            label="Precision@10"
            value="40%"
            description="4 of the top 10 ranked test observations were positive."
          />

          <MetricCard
            label="Precision@20"
            value="25%"
            description="5 of the top 20 ranked test observations were positive."
          />

          <MetricCard
            label="Precision@50"
            value="14%"
            description="7 of the top 50 ranked test observations were positive."
          />

        </div>

        <p className="text-xs text-muted mt-4 leading-relaxed">
          Precision@K evaluates whether the highest-ranked observations
          contain useful suspicious cases for investigator prioritization.
        </p>

      </Card>

      {/* Interpretation */}
      <Card title="How to Read These Results">

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

          <div className="rounded-lg border border-border p-4">
            <div className="text-sm font-semibold">
              ROC-AUC
            </div>

            <p className="text-xs text-muted mt-2 leading-relaxed">
              Measures how well the model separates positive and negative
              account-window observations across ranking thresholds.
            </p>
          </div>

          <div className="rounded-lg border border-border p-4">
            <div className="text-sm font-semibold">
              PR-AUC
            </div>

            <p className="text-xs text-muted mt-2 leading-relaxed">
              Focuses on precision-recall behaviour and is particularly
              important because the positive class is extremely rare.
            </p>
          </div>

          <div className="rounded-lg border border-border p-4">
            <div className="text-sm font-semibold">
              Precision@K
            </div>

            <p className="text-xs text-muted mt-2 leading-relaxed">
              Shows how useful the highest-ranked cases are when an
              investigator can only review a limited number of cases.
            </p>
          </div>

        </div>

      </Card>

      {/* Important distinction */}
      <div className="rounded-lg border border-border p-4">

        <div className="text-xs font-semibold uppercase tracking-wide">
          Important distinction
        </div>

        <p className="text-xs text-muted mt-2 leading-relaxed">
          These metrics evaluate the account-window forecasting model.
          They are different from the separate ring-level forensic
          evaluation, where candidate formation and AMLSim ground-truth
          linkage are evaluated independently.
        </p>

      </div>

    </div>
  );
}