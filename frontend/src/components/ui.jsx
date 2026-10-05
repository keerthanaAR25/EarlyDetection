import React from "react";

/* =========================================================
   CARD
   ========================================================= */

export function Card({
  title,
  subtitle,
  children,
  className = "",
  accent = false,
}) {
  return (
    <div
      className={`card ${
        accent ? "risk-glow" : ""
      } ${className}`}
    >
      {(title || subtitle) && (
        <div className="mb-4">
          {title && (
            <div className="flex items-center gap-2">
              {accent && (
                <span className="w-1.5 h-5 rounded-full bg-accent" />
              )}

              <div className="text-xs uppercase text-muted tracking-wide font-semibold">
                {title}
              </div>
            </div>
          )}

          {subtitle && (
            <div className="text-xs text-muted mt-1">
              {subtitle}
            </div>
          )}
        </div>
      )}

      {children}
    </div>
  );
}


/* =========================================================
   STAT CARD
   ========================================================= */

export function StatCard({
  label,
  value,
  subtitle,
  icon,
  trend,
  accent = false,
}) {
  return (
    <div
      className={`card group relative overflow-hidden ${
        accent ? "risk-glow" : ""
      }`}
    >
      {/* Decorative background */}
      <div
        className="
          absolute
          -right-8
          -top-8
          w-24
          h-24
          rounded-full
          bg-accent/10
          blur-2xl
          opacity-0
          group-hover:opacity-100
          transition-opacity
          duration-500
        "
      />

      <div className="relative">

        <div className="flex items-start justify-between gap-3">

          <div>
            <div className="text-xs uppercase text-muted tracking-wide font-semibold">
              {label}
            </div>

            <div className="text-2xl md:text-3xl font-bold mt-2 tracking-tight">
              {value ?? "—"}
            </div>

            {subtitle && (
              <div className="text-xs text-muted mt-1">
                {subtitle}
              </div>
            )}

            {trend && (
              <div className="text-xs text-accent font-medium mt-2">
                {trend}
              </div>
            )}
          </div>

          {icon && (
            <div
              className="
                w-10
                h-10
                rounded-xl
                bg-accent/10
                border
                border-accent/20
                flex
                items-center
                justify-center
                text-accent
                float-animation
              "
            >
              {icon}
            </div>
          )}

        </div>

        {/* Bottom accent line */}
        <div
          className="
            absolute
            left-0
            bottom-0
            h-0.5
            w-0
            bg-accent
            group-hover:w-full
            transition-all
            duration-500
          "
        />

      </div>
    </div>
  );
}


/* =========================================================
   RISK BADGE
   ========================================================= */

const LEVEL_CONFIG = {
  LOW: {
    className: "bg-emerald-50 text-emerald-700 border-emerald-200",
    dot: "bg-emerald-500",
  },

  MODERATE: {
    className: "bg-amber-50 text-amber-700 border-amber-200",
    dot: "bg-amber-500",
  },

  HIGH: {
    className: "bg-orange-50 text-orange-700 border-orange-200",
    dot: "bg-orange-500",
  },

  CRITICAL: {
    className: "bg-red-50 text-red-700 border-red-200",
    dot: "bg-red-500",
  },
};

export function RiskBadge({ level }) {
  const normalized = String(level || "").toUpperCase();

  const config =
    LEVEL_CONFIG[normalized] || {
      className: "bg-slate-50 text-slate-600 border-slate-200",
      dot: "bg-slate-400",
    };

  return (
    <span
      className={`
        badge
        border
        ${config.className}
        ${normalized === "CRITICAL" ? "risk-glow" : ""}
      `}
    >
      <span
        className={`
          inline-block
          w-1.5
          h-1.5
          rounded-full
          ${config.dot}
        `}
      />

      {level || "N/A"}
    </span>
  );
}


/* =========================================================
   FORMATION STAGE BADGE
   ========================================================= */

export function StageBadge({ stage }) {
  const normalized = String(stage || "")
    .toUpperCase();

  const config = {
    WATCH: "bg-slate-50 text-slate-600 border-slate-200",
    FORMING: "bg-blue-50 text-blue-700 border-blue-200",
    EMERGING: "bg-violet-50 text-violet-700 border-violet-200",
    OBSERVABLE_RING:
      "bg-red-50 text-red-700 border-red-200",
  };

  return (
    <span
      className={`
        badge
        border
        ${config[normalized] || "bg-slate-50 text-slate-600 border-slate-200"}
      `}
    >
      {String(stage || "N/A")
        .replaceAll("_", " ")}
    </span>
  );
}


/* =========================================================
   LOADING
   ========================================================= */

export function Loading({
  message = "Loading analytical data...",
}) {
  return (
    <div className="space-y-4 fade-in">

      <div className="flex items-center gap-3">

        <div
          className="
            w-5
            h-5
            rounded-full
            border-2
            border-slate-200
            border-t-blue-600
            animate-spin
          "
        />

        <div className="text-sm text-muted">
          {message}
        </div>

      </div>

      {/* Skeleton cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

        {[1, 2, 3].map((item) => (
          <div
            key={item}
            className="
              h-28
              rounded-xl
              border
              border-border
              bg-white
              animate-pulse
            "
          />
        ))}

      </div>

    </div>
  );
}


/* =========================================================
   ERROR BOX
   ========================================================= */

export function ErrorBox({ error }) {
  const message =
    error?.message ||
    String(error || "Unknown error");

  return (
    <div
      className="
        rounded-xl
        border
        border-red-200
        bg-red-50
        p-4
        fade-in
      "
    >

      <div className="flex items-start gap-3">

        <div
          className="
            w-8
            h-8
            rounded-lg
            bg-red-100
            text-red-600
            flex
            items-center
            justify-center
            font-bold
          "
        >
          !
        </div>

        <div>

          <div className="text-sm font-semibold text-red-700">
            Unable to load data
          </div>

          <div className="text-xs text-red-600 mt-1 break-words">
            {message}
          </div>

          <div className="text-xs text-red-500 mt-2">
            Check that the FastAPI backend is running and the requested
            endpoint is available.
          </div>

        </div>

      </div>

    </div>
  );
}


/* =========================================================
   EMPTY STATE
   ========================================================= */

export function EmptyState({
  title = "No data available",
  description = "There are no records to display.",
}) {
  return (
    <div
      className="
        rounded-xl
        border
        border-dashed
        border-border
        bg-slate-50
        p-8
        text-center
        fade-in
      "
    >

      <div className="text-2xl mb-2">
        ◌
      </div>

      <div className="text-sm font-semibold">
        {title}
      </div>

      <div className="text-xs text-muted mt-1">
        {description}
      </div>

    </div>
  );
}


/* =========================================================
   PROGRESS BAR
   ========================================================= */

export function ProgressBar({
  value = 0,
  max = 100,
  label,
  showValue = true,
}) {
  const numericValue = Number(value) || 0;
  const numericMax = Number(max) || 100;

  const percentage = Math.max(
    0,
    Math.min(
      100,
      (numericValue / numericMax) * 100
    )
  );

  return (
    <div className="w-full">

      {(label || showValue) && (
        <div className="flex justify-between items-center mb-1.5">

          {label && (
            <span className="text-xs text-muted">
              {label}
            </span>
          )}

          {showValue && (
            <span className="text-xs font-semibold">
              {percentage.toFixed(0)}%
            </span>
          )}

        </div>
      )}

      <div
        className="
          h-2
          rounded-full
          bg-slate-100
          overflow-hidden
        "
      >
        <div
          className="
            h-full
            rounded-full
            bg-gradient-to-r
            from-blue-500
            to-blue-600
            transition-all
            duration-700
            ease-out
          "
          style={{
            width: `${percentage}%`,
          }}
        />
      </div>

    </div>
  );
}


/* =========================================================
   API HOOK
   ========================================================= */

export function useApi(fn, deps = []) {
  const [state, setState] = React.useState({
    data: null,
    loading: true,
    error: null,
  });

  React.useEffect(() => {
    let alive = true;

    setState({
      data: null,
      loading: true,
      error: null,
    });

    Promise.resolve()
      .then(() => fn())
      .then((data) => {
        if (!alive) return;

        setState({
          data,
          loading: false,
          error: null,
        });
      })
      .catch((error) => {
        if (!alive) return;

        setState({
          data: null,
          loading: false,
          error,
        });
      });

    return () => {
      alive = false;
    };
  }, deps);

  return state;
}