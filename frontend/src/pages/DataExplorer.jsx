import React from "react";
import { api } from "../api.js";
import { Loading, ErrorBox, useApi } from "../components/ui.jsx";

function formatAmount(value) {
  const n = Number(value);

  if (!Number.isFinite(n)) return value ?? "—";

  return n.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatDate(value) {
  if (!value) return "—";

  const d = new Date(value);

  if (Number.isNaN(d.getTime())) {
    return String(value).slice(0, 19);
  }

  return d.toLocaleString("en-IN", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function LabelBadge({ label }) {
  if (label === 1 || label === "1") {
    return (
      <span className="inline-flex rounded-md border border-red-500/20 bg-red-500/10 px-2 py-1 text-xs font-medium text-red-400">
        SAR
      </span>
    );
  }

  return (
    <span className="text-xs text-muted">
      Unlabelled
    </span>
  );
}

export default function DataExplorer() {
  const [accountId, setAccountId] = React.useState("");
  const [search, setSearch] = React.useState("");

  const { data, loading, error } = useApi(
    () =>
      api.transactions({
        account_id: accountId || null,
        limit: 50,
      }),
    [accountId]
  );

  const transactions = Array.isArray(data) ? data : [];

  const filteredTransactions = React.useMemo(() => {
    const q = search.trim().toLowerCase();

    if (!q) return transactions;

    return transactions.filter((t) =>
      [
        t.transaction_id,
        t.sender,
        t.receiver,
        t.amount,
        t.timestamp,
      ]
        .filter(Boolean)
        .some((value) =>
          String(value).toLowerCase().includes(q)
        )
    );
  }, [transactions, search]);

  const labelledCount = transactions.filter(
    (t) => t.label === 1 || t.label === "1"
  ).length;

  const totalAmount = transactions.reduce(
    (sum, t) => sum + (Number(t.amount) || 0),
    0
  );

  return (
    <div className="space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold">
          Transaction Data Explorer
        </h1>

        <p className="text-sm text-muted mt-1">
          Inspect transaction-level activity and investigate suspicious
          financial flows.
        </p>
      </div>

      {/* Filters */}
      <div className="rounded-lg border border-border p-4">

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">

          <div>
            <label className="block text-xs font-medium text-muted mb-1">
              Account ID
            </label>

            <input
              className="bg-panel border border-border rounded-md px-3 py-2 text-sm w-full"
              placeholder="e.g. 4354"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-muted mb-1">
              Search loaded transactions
            </label>

            <input
              className="bg-panel border border-border rounded-md px-3 py-2 text-sm w-full"
              placeholder="Transaction ID, sender, receiver..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

        </div>

        {accountId && (
          <button
            type="button"
            className="mt-3 text-xs text-accent hover:underline"
            onClick={() => {
              setAccountId("");
              setSearch("");
            }}
          >
            Clear filters
          </button>
        )}

      </div>

      {/* Summary */}
      {!loading && !error && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">

          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted uppercase tracking-wide">
              Transactions loaded
            </div>

            <div className="text-2xl font-bold mt-1">
              {transactions.length}
            </div>

            <div className="text-xs text-muted mt-1">
              Maximum 50 shown per request
            </div>
          </div>

          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted uppercase tracking-wide">
              Labelled SAR transactions
            </div>

            <div className="text-2xl font-bold mt-1">
              {labelledCount}
            </div>

            <div className="text-xs text-muted mt-1">
              Based on available transaction labels
            </div>
          </div>

          <div className="rounded-lg border border-border p-4">
            <div className="text-xs text-muted uppercase tracking-wide">
              Amount in loaded records
            </div>

            <div className="text-2xl font-bold mt-1">
              {formatAmount(totalAmount)}
            </div>

            <div className="text-xs text-muted mt-1">
              Sum of displayed transactions
            </div>
          </div>

        </div>
      )}

      {/* Loading / Error */}
      {loading && <Loading />}

      {error && <ErrorBox error={error} />}

      {/* Table */}
      {!loading && !error && (
        <div className="rounded-lg border border-border overflow-hidden">

          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <div>
              <h2 className="font-semibold text-sm">
                Transaction Records
              </h2>

              <p className="text-xs text-muted mt-1">
                {filteredTransactions.length} records shown
              </p>
            </div>

            {accountId && (
              <span className="text-xs text-muted">
                Account: {accountId}
              </span>
            )}
          </div>

          <div className="overflow-x-auto">

            <table className="w-full text-sm">

              <thead className="bg-muted/5 text-muted text-left">
                <tr>
                  <th className="px-4 py-3 font-medium">
                    Transaction
                  </th>

                  <th className="px-4 py-3 font-medium">
                    Sender
                  </th>

                  <th className="px-4 py-3 font-medium">
                    Receiver
                  </th>

                  <th className="px-4 py-3 font-medium">
                    Amount
                  </th>

                  <th className="px-4 py-3 font-medium">
                    Timestamp
                  </th>

                  <th className="px-4 py-3 font-medium">
                    Label
                  </th>
                </tr>
              </thead>

              <tbody>

                {filteredTransactions.map((t) => (

                  <tr
                    key={t.transaction_id}
                    className="border-t border-border hover:bg-muted/5 transition-colors"
                  >

                    <td className="px-4 py-3">
                      <div className="font-medium">
                        {t.transaction_id}
                      </div>
                    </td>

                    <td className="px-4 py-3">
                      <span className="font-mono text-xs">
                        {t.sender || "—"}
                      </span>
                    </td>

                    <td className="px-4 py-3">
                      <span className="font-mono text-xs">
                        {t.receiver || "—"}
                      </span>
                    </td>

                    <td className="px-4 py-3 font-medium">
                      {formatAmount(t.amount)}
                    </td>

                    <td className="px-4 py-3 text-xs text-muted whitespace-nowrap">
                      {formatDate(t.timestamp)}
                    </td>

                    <td className="px-4 py-3">
                      <LabelBadge label={t.label} />
                    </td>

                  </tr>

                ))}

                {filteredTransactions.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-10 text-center text-muted"
                    >
                      No transactions match the current filters.
                    </td>
                  </tr>
                )}

              </tbody>

            </table>

          </div>

        </div>
      )}

      {/* Interpretation */}
      <div className="rounded-lg border border-border px-4 py-3">
        <div className="text-xs font-semibold uppercase tracking-wide">
          Forensic interpretation
        </div>

        <p className="text-xs text-muted mt-1 leading-relaxed">
          Transaction records provide the underlying evidence used by the
          temporal transaction graph, behavioural features and suspicious
          pattern detectors. A SAR label identifies an available labelled
          transaction; it does not by itself establish that the account or
          transaction constitutes confirmed money laundering.
        </p>
      </div>

    </div>
  );
}