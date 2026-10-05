#!/usr/bin/env python3

"""

AMLSim Ground-Truth Lead-Time Evaluation



This script evaluates the existing ring candidates against AMLSim

alert transactions.



IMPORTANT:

    This script changes ONLY evaluation/linkage.

    It does not modify:

        - pattern detection

        - trajectories

        - ring candidates

        - risk scores

        - evidence



Ground-truth matching rule:

    A candidate matches an AMLSim alert when:



        1. Candidate and alert share at least 2 participant accounts

        2. Their transaction time intervals overlap



Ground-truth observable time:

    Earliest transaction timestamp belonging to the AMLSim alert.



Warning time:

    First candidate trajectory window where cumulative risk

    crosses the configured alert threshold.



Lead time:

    observable_window - warning_window



Positive lead time = detected before AMLSim observable event.

"""



import json

import sys

from pathlib import Path



import numpy as np

import pandas as pd

import yaml





# ============================================================

# PROJECT ROOT

# ============================================================



ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT))





# ============================================================

# PROJECT IMPORTS

# ============================================================



from src.graph.temporal_graph import TemporalGraphBuilder

from src.ring.ring_candidate_engine import RingCandidate

from src.scoring.risk_engine import RiskScoreResult

from src.temporal.trajectory import _PATTERN_WEIGHT





# ============================================================

# CONSTANTS

# ============================================================



MAX_PATTERN_WEIGHT = sum(_PATTERN_WEIGHT.values())



# Minimum number of shared accounts required for an

# evaluation match.

MIN_SHARED_ACCOUNTS = 2

# Secondary forensic linkage window. This does NOT replace strict matching.
MAX_NEARBY_GAP_DAYS = 10.0





# ============================================================

# LOAD AMLSIM GROUND TRUTH

# ============================================================



def load_ground_truth(alert_path):

    """

    Build ground-truth alert events from AMLSim

    alert_transactions.csv.



    Each alert becomes one ground-truth laundering event.

    """



    df = pd.read_csv(

        alert_path,

        dtype={

            "alert_id": str,

            "tran_id": str,

            "orig_acct": str,

            "bene_acct": str,

        },

    )



    # --------------------------------------------------------

    # Parse timestamps

    # --------------------------------------------------------



    df["tran_timestamp"] = pd.to_datetime(

        df["tran_timestamp"],

        utc=True,

        errors="coerce",

    )



    df = df.dropna(

        subset=[

            "alert_id",

            "tran_timestamp",

        ]

    )



    ground_truth = []



    # --------------------------------------------------------

    # One AML event per alert_id

    # --------------------------------------------------------



    for alert_id, group in df.groupby("alert_id"):



        # All accounts participating in this alert.

        origin_accounts = set(

            group["orig_acct"]

            .dropna()

            .astype(str)

        )



        beneficiary_accounts = set(

            group["bene_acct"]

            .dropna()

            .astype(str)

        )



        participants = (

            origin_accounts

            | beneficiary_accounts

        )



        # Alert transaction IDs.

        transaction_ids = set(

            group["tran_id"]

            .dropna()

            .astype(str)

        )



        if not participants:

            continue



        if group.empty:

            continue



        # ----------------------------------------------------

        # Observable AML event interval

        # ----------------------------------------------------



        first_alert_time = group[

            "tran_timestamp"

        ].min()



        last_alert_time = group[

            "tran_timestamp"

        ].max()



        # ----------------------------------------------------

        # Alert metadata

        # ----------------------------------------------------



        if "alert_type" in group.columns:

            alert_type = str(

                group["alert_type"].iloc[0]

            )

        else:

            alert_type = "unknown"



        if "is_sar" in group.columns:

            is_sar = bool(

                group["is_sar"].iloc[0]

            )

        else:

            is_sar = True



        ground_truth.append(

            {

                "ring_id": str(alert_id),

                "alert_id": str(alert_id),

                "alert_type": alert_type,

                "is_sar": is_sar,



                "participants": sorted(

                    participants

                ),



                "transaction_ids": sorted(

                    transaction_ids

                ),



                "first_alert_time":

                    first_alert_time,



                "last_alert_time":

                    last_alert_time,



                "n_alert_transactions":

                    len(transaction_ids),



                "n_alert_accounts":

                    len(participants),

            }

        )



    return ground_truth





# ============================================================

# CANDIDATE TIME SPAN

# ============================================================



def candidate_time_span(

    candidate,

    transactions,

):

    """

    Determine the actual transaction time interval

    represented by a ring candidate.

    """



    candidate_transaction_ids = {

        str(x)

        for x in candidate.transaction_ids

    }



    if not candidate_transaction_ids:

        return None, None



    subset = transactions[

        transactions["transaction_id"]

        .astype(str)

        .isin(candidate_transaction_ids)

    ]



    if subset.empty:

        return None, None



    start_time = subset[

        "timestamp"

    ].min()



    end_time = subset[

        "timestamp"

    ].max()



    return start_time, end_time





# ============================================================

# CANDIDATE ↔ GROUND-TRUTH MATCH

# ============================================================



def calculate_match(candidate, ground_truth_event, transactions):
    """Match using STRONG (overlap) or secondary MODERATE (<=10-day gap) linkage."""
    candidate_accounts = {str(a) for a in candidate.accounts}
    gt_accounts = {str(a) for a in ground_truth_event["participants"]}
    shared_accounts = candidate_accounts & gt_accounts
    n_shared = len(shared_accounts)
    if n_shared < MIN_SHARED_ACCOUNTS:
        return None

    candidate_start, candidate_end = candidate_time_span(candidate, transactions)
    if candidate_start is None or candidate_end is None:
        return None

    gt_start = pd.Timestamp(ground_truth_event["first_alert_time"])
    gt_end = pd.Timestamp(ground_truth_event["last_alert_time"])
    vals=[]
    for ts in (gt_start, gt_end, pd.Timestamp(candidate_start), pd.Timestamp(candidate_end)):
        if ts.tzinfo is None: ts=ts.tz_localize("UTC")
        else: ts=ts.tz_convert("UTC")
        vals.append(ts)
    gt_start, gt_end, candidate_start, candidate_end = vals

    overlap_start=max(candidate_start,gt_start); overlap_end=min(candidate_end,gt_end)
    if overlap_start <= overlap_end:
        strength="STRONG"; overlap_days=(overlap_end-overlap_start).total_seconds()/86400.0; gap_days=0.0
    else:
        gap_days=((gt_start-candidate_end) if candidate_end < gt_start else (candidate_start-gt_end)).total_seconds()/86400.0
        if gap_days > MAX_NEARBY_GAP_DAYS: return None
        strength="MODERATE"; overlap_days=0.0

    recall=n_shared/len(gt_accounts) if gt_accounts else 0.0
    precision=n_shared/len(candidate_accounts) if candidate_accounts else 0.0
    union=candidate_accounts|gt_accounts
    jaccard=n_shared/len(union) if union else 0.0
    return {
        "ring_id":ground_truth_event["ring_id"],"alert_id":ground_truth_event["alert_id"],
        "alert_type":ground_truth_event["alert_type"],"first_alert_time":gt_start,"last_alert_time":gt_end,
        "shared_accounts":sorted(shared_accounts),"n_shared_accounts":n_shared,
        "account_recall":recall,"candidate_account_precision":precision,"jaccard":jaccard,
        "candidate_start":candidate_start,"candidate_end":candidate_end,
        "ground_truth_start":gt_start,"ground_truth_end":gt_end,
        "temporal_overlap_start":overlap_start if strength=="STRONG" else None,
        "temporal_overlap_end":overlap_end if strength=="STRONG" else None,
        "temporal_overlap_days":overlap_days,"temporal_gap_days":gap_days,
        "match_strength":strength,
        "match_method":("2_shared_accounts_plus_temporal_overlap" if strength=="STRONG" else "2_shared_accounts_plus_within_10_day_gap"),
        "candidate_span_days":(candidate_end-candidate_start).total_seconds()/86400.0,
        "ground_truth_span_days":(gt_end-gt_start).total_seconds()/86400.0,
    }




# FIND BEST MATCH

# ============================================================



def find_best_match(candidate, ground_truth, transactions):
    """Find the strongest match; STRONG always outranks MODERATE."""
    matches=[]
    for gt in ground_truth:
        m=calculate_match(candidate,gt,transactions)
        if m is not None: matches.append(m)
    if not matches: return None
    matches.sort(key=lambda x:(1 if x["match_strength"]=="STRONG" else 0,x["n_shared_accounts"],x["account_recall"],x["jaccard"],x["temporal_overlap_days"],-x["temporal_gap_days"]),reverse=True)
    return matches[0]




# WINDOW MAPPING

# ============================================================



def window_id_for_timestamp(

    timestamp,

    window_bounds,

):

    """

    Convert a timestamp into the corresponding

    temporal graph window.

    """



    ts = pd.Timestamp(timestamp)



    if ts.tzinfo is None:

        ts = ts.tz_localize("UTC")

    else:

        ts = ts.tz_convert("UTC")



    for bound in window_bounds:



        if (

            bound.start

            <= ts

            < bound.end

        ):

            return bound.window_id



    # If timestamp is outside generated range,

    # return None rather than silently assigning the

    # final window.

    return None





# ============================================================

# CUMULATIVE RISK

# ============================================================



def cumulative_risk_at_window(

    candidate,

    target_window,

    final_behavioural,

    final_network,

    weights,

):

    """

    Reconstruct cumulative risk using the candidate's

    trajectory evidence up to a specific window.



    Existing project approximation is preserved:



        behavioural = final candidate behavioural score

        network     = final candidate network score



    Fund-flow and persistence are reconstructed

    cumulatively from the trajectory.

    """



    sequence = candidate.trajectory.get(

        "pattern_sequence",

        [],

    )



    window_ids = candidate.trajectory.get(

        "event_window_ids",

        [],

    )



    truncated_patterns = [

        pattern

        for pattern, window_id

        in zip(

            sequence,

            window_ids,

        )

        if window_id <= target_window

    ]



    if not truncated_patterns:

        return 0.0



    # --------------------------------------------------------

    # Fund-flow component

    # --------------------------------------------------------



    distinct_patterns = set(

        truncated_patterns

    )



    weight_sum = sum(

        _PATTERN_WEIGHT.get(

            pattern,

            0.5,

        )

        for pattern in distinct_patterns

    )



    if MAX_PATTERN_WEIGHT > 0:



        fund_flow = min(

            100.0,

            (

                weight_sum

                / MAX_PATTERN_WEIGHT

            ) * 100.0,

        )



    else:

        fund_flow = 0.0



    # --------------------------------------------------------

    # Persistence component

    # --------------------------------------------------------



    density = (

        len(truncated_patterns)

        / max(

            len(candidate.accounts),

            1,

        )

    )



    persistence = min(

        100.0,

        35.0

        * np.log1p(

            density * 3.0

        ),

    )



    # --------------------------------------------------------

    # Final cumulative risk

    # --------------------------------------------------------



    score = (

        weights["behavioural"]

        * final_behavioural



        + weights["network"]

        * final_network



        + weights["fund_flow"]

        * fund_flow



        + weights["persistence"]

        * persistence

    )



    return float(score)





# ============================================================

# WARNING WINDOW

# ============================================================



def calculate_warning_window(

    candidate,

    risk_result,

    weights,

    alert_threshold,

):

    """

    Find the first trajectory window where cumulative

    risk reaches the configured alert threshold.

    """



    window_ids = candidate.trajectory.get(

        "event_window_ids",

        [],

    )



    if not window_ids:

        return None



    # --------------------------------------------------------

    # Final behavioural component

    # --------------------------------------------------------



    if risk_result:



        final_behavioural = (

            risk_result.score_components.get(

                "behavioural",

                0.0,

            )

        )



        final_network = (

            risk_result.score_components.get(

                "network",

                0.0,

            )

        )



    else:



        final_behavioural = 0.0

        final_network = 0.0



    # --------------------------------------------------------

    # Chronological warning search

    # --------------------------------------------------------



    for window_id in sorted(

        set(window_ids)

    ):



        score = cumulative_risk_at_window(

            candidate,

            window_id,

            final_behavioural,

            final_network,

            weights,

        )



        if score >= alert_threshold:

            return window_id



    return None





# ============================================================

# BUILD CANDIDATE RESULT

# ============================================================



def build_result(candidate, risk_result, ground_truth, match, window_bounds, weights, alert_threshold):
    """Build one candidate evaluation record."""
    warning_window=calculate_warning_window(candidate,risk_result,weights,alert_threshold)
    alerted=warning_window is not None
    result={"candidate_ring_id":candidate.candidate_ring_id,"warning_window":warning_window,"alerted":alerted}
    if match is None:
        result.update({"matched_ground_truth_ring_id":None,"match_strength":"NONE","match_method":"no_match","match_overlap_fraction":0.0,"n_shared_accounts":0,"account_recall":0.0,"candidate_account_precision":0.0,"jaccard":0.0,"alert_type":None,"shared_accounts":[],"candidate_start":None,"candidate_end":None,"ground_truth_start":None,"ground_truth_end":None,"temporal_overlap_days":0.0,"temporal_gap_days":None,"candidate_span_days":None,"ground_truth_span_days":None,"observable_window":None,"lead_time_windows":None,"early_detection":None,"completion_observable_window":None,"completion_lead_time_windows":None,"completion_early_detection":None})
        return result
    observable_window=window_id_for_timestamp(match["first_alert_time"],window_bounds)
    completion_observable_window=window_id_for_timestamp(match["last_alert_time"],window_bounds)
    lead_time=None; early=None
    completion_lead_time=None; completion_early=None
    if alerted and observable_window is not None:
        lead_time=observable_window-warning_window; early=lead_time>=0
    if alerted and completion_observable_window is not None:
        completion_lead_time=completion_observable_window-warning_window; completion_early=completion_lead_time>=0
    result.update({"matched_ground_truth_ring_id":match["ring_id"],"match_strength":match["match_strength"],"match_method":match["match_method"],"match_overlap_fraction":match["account_recall"],"n_shared_accounts":match["n_shared_accounts"],"account_recall":match["account_recall"],"candidate_account_precision":match["candidate_account_precision"],"jaccard":match["jaccard"],"alert_type":match["alert_type"],"shared_accounts":match["shared_accounts"],"candidate_start":str(match["candidate_start"]),"candidate_end":str(match["candidate_end"]),"ground_truth_start":str(match["ground_truth_start"]),"ground_truth_end":str(match["ground_truth_end"]),"temporal_overlap_days":match["temporal_overlap_days"],"temporal_gap_days":match["temporal_gap_days"],"candidate_span_days":match["candidate_span_days"],"ground_truth_span_days":match["ground_truth_span_days"],"observable_window":observable_window,"lead_time_windows":lead_time,"early_detection":early,"completion_observable_window":completion_observable_window,"completion_lead_time_windows":completion_lead_time,"completion_early_detection":completion_early})
    return result




# SUMMARY

# ============================================================



def summarize(results, n_ground_truth):
    """Report original strict metrics separately from secondary moderate linkage."""
    strong=[r for r in results if r.get("match_strength")=="STRONG"]; moderate=[r for r in results if r.get("match_strength")=="MODERATE"]; extended=strong+moderate
    alerted=[r for r in results if r["alerted"]]
    strict=[r for r in strong if r["alerted"] and r["lead_time_windows"] is not None]
    ext=[r for r in extended if r["alerted"] and r["lead_time_windows"] is not None]
    sleads=[r["lead_time_windows"] for r in strict]; eleads=[r["lead_time_windows"] for r in ext]
    completion_strict=[r for r in strong if r["alerted"] and r.get("completion_lead_time_windows") is not None]
    completion_extended=[r for r in extended if r["alerted"] and r.get("completion_lead_time_windows") is not None]
    cleads=[r["completion_lead_time_windows"] for r in completion_strict]; celeads=[r["completion_lead_time_windows"] for r in completion_extended]
    searly=[r for r in strict if r["early_detection"]]; eearly=[r for r in ext if r["early_detection"]]
    csearly=[r for r in completion_strict if r.get("completion_early_detection")]; ceearly=[r for r in completion_extended if r.get("completion_early_detection")]
    sg={r["matched_ground_truth_ring_id"] for r in strict}; eg={r["matched_ground_truth_ring_id"] for r in ext}
    strict_unmatched=[r for r in alerted if r.get("match_strength")!="STRONG"]; ext_unmatched=[r for r in alerted if r.get("match_strength")=="NONE"]
    def st(v,fn): return float(fn(v)) if v else None
    return {
      "ground_truth_rings":n_ground_truth,"n_candidates":len(results),"n_matched_to_ground_truth":len(strong),"n_strong_matches":len(strong),"n_moderate_matches":len(moderate),"n_extended_matches":len(extended),"n_alerted_candidates":len(alerted),"n_alerted_and_matched":len(strict),"unique_ground_truth_rings_detected":len(sg),"candidate_match_rate":len(strong)/len(results) if results else None,"ring_detection_rate":len(sg)/n_ground_truth if n_ground_truth else None,"strong_match_ring_detection_rate":len(sg)/n_ground_truth if n_ground_truth else None,"false_warning_rate_candidates":len(strict_unmatched)/len(alerted) if alerted else None,"mean_lead_time_windows":st(sleads,np.mean),"median_lead_time_windows":st(sleads,np.median),"min_lead_time_windows":st(sleads,np.min),"max_lead_time_windows":st(sleads,np.max),"std_lead_time_windows":float(np.std(sleads)) if len(sleads)>1 else None,"early_detection_rate":len(searly)/len(strict) if strict else None,"n_early_detections":len(searly),
      "extended_candidate_match_rate":len(extended)/len(results) if results else None,"extended_match_ring_detection_rate":len(eg)/n_ground_truth if n_ground_truth else None,"extended_false_warning_rate_candidates":len(ext_unmatched)/len(alerted) if alerted else None,"extended_n_alerted_and_matched":len(ext),"extended_mean_lead_time_windows":st(eleads,np.mean),"extended_median_lead_time_windows":st(eleads,np.median),"extended_min_lead_time_windows":st(eleads,np.min),"extended_max_lead_time_windows":st(eleads,np.max),"extended_std_lead_time_windows":float(np.std(eleads)) if len(eleads)>1 else None,"extended_early_detection_rate":len(eearly)/len(ext) if ext else None,"extended_n_early_detections":len(eearly),
      "evaluation_rule":("STRICT/STRONG: >=2 shared participant accounts AND overlapping transaction intervals; original ring detection and lead-time metrics use STRONG matches only. SECONDARY/MODERATE: >=2 shared accounts with no temporal overlap but a gap <= " + str(MAX_NEARBY_GAP_DAYS) + " days. Moderate linkage is reported separately and does not replace strict evaluation. Baseline lead time uses the earliest AMLSim alert transaction as the observable event. Completion-based lead time uses the latest AMLSim alert transaction and is reported separately to characterize warning before the end of the known alert lifecycle."),
      "risk_model_note":"Warning-time reconstruction preserves the existing project's approximation: final behavioural and network components are held constant while fund-flow and persistence components are accumulated by trajectory window."
    }




# MAIN

# ============================================================



def main():



    print("=" * 70)

    print("AMLSim Ground-Truth Lead-Time Evaluation")

    print("=" * 70)



    # --------------------------------------------------------

    # Configuration

    # --------------------------------------------------------



    with open(

        ROOT

        / "configs"

        / "config.yaml"

    ) as f:



        config = yaml.safe_load(f)



    # --------------------------------------------------------

    # Transactions

    # --------------------------------------------------------



    transactions = pd.read_csv(

        ROOT

        / "data"

        / "processed"

        / "transactions_clean.csv",



        parse_dates=[

            "timestamp"

        ],



        dtype={

            "transaction_id": str,

            "sender": str,

            "receiver": str,

            "scenario_id": str,

            "ring_id": str,

        },

    )



    transactions["timestamp"] = (

        pd.to_datetime(

            transactions["timestamp"],

            utc=True,

            errors="coerce",

        )

    )



    print(

        f"Loaded {len(transactions):,} transactions"

    )



    # --------------------------------------------------------

    # Temporal graph windows

    # --------------------------------------------------------



    builder = TemporalGraphBuilder(

        transactions,

        config["temporal"]["window_size"],

        config["temporal"]["step_size"],

    )



    window_bounds = (

        builder.generate_window_bounds()

    )



    print(

        f"Generated {len(window_bounds)} temporal windows"

    )



    # --------------------------------------------------------

    # Ring candidates

    # --------------------------------------------------------



    candidate_path = (

        ROOT

        / "results"

        / "ring_candidates.json"

    )



    with open(candidate_path) as f:



        candidates = [

            RingCandidate(**d)

            for d in json.load(f)

        ]



    print(

        f"Loaded {len(candidates)} ring candidates"

    )



    # --------------------------------------------------------

    # Risk scores

    # --------------------------------------------------------



    risk_path = (

        ROOT

        / "results"

        / "risk_scores.json"

    )



    with open(risk_path) as f:



        risk_records = json.load(f)



    risk_by_id = {

        record[

            "candidate_ring_id"

        ]: RiskScoreResult(**record)



        for record in risk_records

    }



    print(

        f"Loaded {len(risk_by_id)} risk scores"

    )



    # --------------------------------------------------------

    # AMLSim ground truth

    # --------------------------------------------------------



    if (

        config["dataset"]["active"]

        != "amlsim"

    ):



        raise RuntimeError(

            "This evaluation script expects "

            "dataset.active = amlsim."

        )



    alert_path = (

        ROOT

        / "data"

        / "raw"

        / "amlsim"

        / "alert_transactions.csv"

    )



    if not alert_path.exists():



        raise FileNotFoundError(

            f"AMLSim alert file not found: "

            f"{alert_path}"

        )



    ground_truth = (

        load_ground_truth(

            alert_path

        )

    )



    print(

        f"Loaded {len(ground_truth)} AMLSim alert events"

    )



    # --------------------------------------------------------

    # Risk configuration

    # --------------------------------------------------------



    weights = config[

        "risk_scoring"

    ][

        "component_weights"

    ]



    alert_threshold = config[

        "risk_scoring"

    ][

        "alert_threshold"

    ]



    print(

        f"Alert threshold: {alert_threshold}"

    )



    print(

        f"Minimum shared accounts: "

        f"{MIN_SHARED_ACCOUNTS}"

    )



    # --------------------------------------------------------

    # Evaluate candidates

    # --------------------------------------------------------



    results = []



    print("\nEvaluating candidates...")



    for index, candidate in enumerate(

        candidates,

        start=1,

    ):



        match = find_best_match(

            candidate,

            ground_truth,

            transactions,

        )



        result = build_result(

            candidate,

            risk_by_id.get(

                candidate.candidate_ring_id

            ),

            ground_truth,

            match,

            window_bounds,

            weights,

            alert_threshold,

        )



        results.append(result)



        if match is not None:



            print(

                f"  [{index}/{len(candidates)}] "

                f"{candidate.candidate_ring_id} "

                f"-> {match['ring_id']} "

                f"| shared={match['n_shared_accounts']} "

                f"| recall={match['account_recall']:.2f} "

                f"| type={match['alert_type']}"

            )



    # --------------------------------------------------------

    # Summary

    # --------------------------------------------------------



    summary = summarize(

        results,

        len(ground_truth),

    )



    print("\n" + "=" * 70)

    print("EVALUATION SUMMARY")

    print("=" * 70)



    for key, value in summary.items():



        print(

            f"{key}: {value}"

        )



    # --------------------------------------------------------

    # Output directory

    # --------------------------------------------------------



    out_dir = (

        ROOT

        / "results"

    )



    out_dir.mkdir(

        parents=True,

        exist_ok=True,

    )



    # --------------------------------------------------------

    # JSON results

    # --------------------------------------------------------



    results_path = (

        out_dir

        / "lead_time_results.json"

    )



    with open(

        results_path,

        "w",

    ) as f:



        json.dump(

            results,

            f,

            indent=2,

            default=str,

        )



    # --------------------------------------------------------

    # JSON summary

    # --------------------------------------------------------



    summary_path = (

        out_dir

        / "lead_time_summary.json"

    )



    with open(

        summary_path,

        "w",

    ) as f:



        json.dump(

            summary,

            f,

            indent=2,

            default=str,

        )



    # --------------------------------------------------------

    # CSV

    # --------------------------------------------------------



    csv_path = (

        out_dir

        / "lead_time.csv"

    )



    pd.DataFrame(

        results

    ).to_csv(

        csv_path,

        index=False,

    )



    # --------------------------------------------------------

    # Final output

    # --------------------------------------------------------



    print("\nOutput files:")

    print(

        f"  {results_path}"

    )

    print(

        f"  {summary_path}"

    )

    print(

        f"  {csv_path}"

    )



    print("\nEvaluation completed successfully.")





# ============================================================

# ENTRY POINT

# ============================================================



if __name__ == "__main__":

    main()
