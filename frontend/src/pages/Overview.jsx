import React from "react";
import { api } from "../api.js";
import { Card, StatCard, Loading, ErrorBox, useApi } from "../components/ui.jsx";

function formatNumber(value) {
  const n = Number(value);

  if (!Number.isFinite(n)) {
    return value ?? "—";
  }

  return n.toLocaleString("en-IN");
}

function formatScore(value) {
  const n = Number(value);

  if (!Number.isFinite(n)) {
    return "—";
  }

  return n.toFixed(2);
}

export default function Overview() {
  const {
    data,
    loading,
    error,
  } = useApi(() => api.summary(), []);

  if (loading) return <Loading />;
  if (error) return <ErrorBox error={error} />;

  const summary = data || {};

  const totalTransactions =
    summary.total_transactions ??
    summary.transactions ??
    0;

  const totalAccounts =
    summary.total_accounts ??
    summary.accounts ??
    0;

  const candidateRings =
    summary.candidate_rings ??
    summary.ring_candidates ??
    0;

  const criticalCandidates =
    summary.critical_risk ??
    summary.critical_candidates ??
    0;

  const highCandidates =
    summary.high_risk ??
    summary.high_candidates ??
    0;

  const moderateCandidates =
    summary.moderate_risk ??
    summary.moderate_candidates ??
    0;

  const averageRisk =
    summary.average_risk_score ??
    summary.avg_risk_score;

  return (
    <div className="space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold">
          Executive Overview
        </h1>

        <p className="text-sm text-muted mt-1">
          AMLSim-based transaction-network analytics, suspicious-pattern
          detection and explainable ring-risk prioritization.
        </p>

        <p className="text-xs text-muted mt-2">
          Dataset provenance and methodology are documented in
          <span className="font-mono ml-1">
            docs/dataset.md
          </span>.
        </p>
      </div>

      {/* Primary dataset metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">

        <StatCard
          label="Total Transactions"
          value={formatNumber(totalTransactions)}
        />

        <StatCard
          label="Total Accounts"
          value={formatNumber(totalAccounts)}
        />

        <StatCard
          label="Candidate Rings"
          value={formatNumber(candidateRings)}
        />

        <StatCard
          label="Critical Candidates"
          value={formatNumber(criticalCandidates)}
        />

      </div>

      {/* Risk distribution */}
      <Card title="Candidate Risk Distribution">

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted uppercase tracking-wide">
              Critical
            </div>

            <div className="text-2xl font-bold mt-1">
              {formatNumber(criticalCandidates)}
            </div>

            <div className="text-xs text-muted mt-1">
              Risk score ≥ 75
            </div>
          </div>

          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted uppercase tracking-wide">
              High
            </div>

            <div className="text-2xl font-bold mt-1">
              {formatNumber(highCandidates)}
            </div>

            <div className="text-xs text-muted mt-1">
              Risk score 50–74
            </div>
          </div>

          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted uppercase tracking-wide">
              Moderate
            </div>

            <div className="text-2xl font-bold mt-1">
              {formatNumber(moderateCandidates)}
            </div>

            <div className="text-xs text-muted mt-1">
              Risk score 25–49
            </div>
          </div>

        </div>

      </Card>

      {/* Average risk */}
      <Card title="Average Candidate Risk Score">

        <div className="flex items-end gap-2">

          <div className="text-4xl font-bold">
            {formatScore(averageRisk)}
          </div>

          <div className="text-muted text-base mb-1">
            /100
          </div>

        </div>

        <p className="text-xs text-muted mt-2">
          Average analytical risk score across detected ring candidates,
          not across individual transactions.
        </p>

      </Card>

      {/* System pipeline */}
      <Card title="Detection Pipeline">

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">

          <PipelineStep
            number="01"
            title="Transactions"
            value={formatNumber(totalTransactions)}
            description="Financial transaction records"
          />

          <PipelineStep
            number="02"
            title="Temporal Graph"
            value="720"
            description="Time-evolving transaction windows"
          />

          <PipelineStep
            number="03"
            title="Patterns"
            value="39,869"
            description="Suspicious pattern events"
          />

          <PipelineStep
            number="04"
            title="Trajectories"
            value="3,460"
            description="Bounded temporal behaviour trajectories"
          />

          <PipelineStep
            number="05"
            title="Ring Candidates"
            value={formatNumber(candidateRings)}
            description="Investigator-priority candidates"
          />

        </div>

      </Card>

      {/* Research positioning */}
      <Card title="System Purpose">

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

          <Purpose
            title="Temporal Analytics"
            text="Tracks how suspicious transaction behaviour changes across time rather than evaluating transactions only in isolation."
          />

          <Purpose
            title="Explainable Risk"
            text="Combines behavioural, network, fund-flow and persistence evidence into an interpretable 0–100 risk score."
          />

          <Purpose
            title="Forensic Investigation"
            text="Links suspicious patterns to accounts, transactions, temporal trajectories and network evidence for investigator review."
          />

        </div>

      </Card>

      {/* Important disclaimer */}
      <div className="rounded-lg border border-border px-4 py-3">

        <div className="text-xs font-semibold uppercase tracking-wide">
          Important interpretation
        </div>

        <p className="text-xs text-muted mt-1 leading-relaxed">
          The dashboard provides analytical decision support and
          prioritization. A candidate ring or high risk score does not
          constitute proof or legal confirmation of money laundering.
          Investigators should review the underlying transaction and
          network evidence.
        </p>

      </div>

    </div>
  );
}

function PipelineStep({
  number,
  title,
  value,
  description,
}) {
  return (
    <div className="rounded-lg border border-border p-4">

      <div className="text-xs text-accent font-semibold">
        {number}
      </div>

      <div className="text-sm font-semibold mt-2">
        {title}
      </div>

      <div className="text-xl font-bold mt-1">
        {value}
      </div>

      <div className="text-xs text-muted mt-1 leading-relaxed">
        {description}
      </div>

    </div>
  );
}

function Purpose({ title, text }) {
  return (
    <div className="rounded-lg border border-border p-4">

      <div className="text-sm font-semibold">
        {title}
      </div>

      <p className="text-xs text-muted mt-2 leading-relaxed">
        {text}
      </p>

    </div>
  );
}