import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def load_data(path: str) -> pd.DataFrame:
    """
    Load and clean the CSV. We do a few things here:
    - Normalise salary outliers (cap at 500k/month — anything above is likely annual)
    - Fill missing text fields so TF-IDF doesn't choke on NaN
    - Create a salary_mid column (average of from/to) for easy comparison
    """
    df = pd.read_csv(path)

    # Cap extreme salary values — a few rows have annual figures mixed in
    df["salary_from"] = df["salary_from"].clip(upper=500_000)
    df["salary_to"] = df["salary_to"].clip(upper=500_000)

    # Mid-point salary makes range comparisons simpler
    df["salary_mid"] = (df["salary_from"] + df["salary_to"]) / 2

    # Fill nulls in text columns so TF-IDF vectoriser never sees NaN
    df["tech_specialisation"] = df["tech_specialisation"].fillna("")
    df["level"] = df["level"].fillna("Unspecified")
    df["mode"] = df["mode"].fillna("Unspecified")
    df["type"] = df["type"].fillna("Unspecified")
    df["education_level"] = df["education_level"].fillna("Unspecified")

    # Normalise job type casing — dataset has both "Full time" and "Full Time"
    df["type"] = df["type"].str.strip().str.title()

    return df


def match_jobs(
    df: pd.DataFrame,
    skill_query: str,
    level: list,
    mode: list,
    job_type: list,
    exp_years: float,
    salary_min: float,
    salary_max: float,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Two-stage matching:

    Stage 1 — Hard filters
      Remove any job that fails a non-negotiable constraint.
      If the user picks "Any" for a filter, we skip that constraint entirely.

    Stage 2 — Soft scoring
      Score each surviving job 0–100 based on:
        - TF-IDF cosine similarity on tech_specialisation (up to 60 pts)
        - Salary fit: does the job's mid-point land in the user's range? (up to 25 pts)
        - Experience proximity: how close is the job's required exp to the user's? (up to 15 pts)

    We then sort by score descending and return the top N.
    """

    candidates = df.copy()

    # ── Stage 1: Hard filters ──────────────────────────────────────────────────
    # Each filter only activates when the user made a selection (non-empty list).
    # "Any" = empty list = no filter applied.

    if level:
        candidates = candidates[candidates["level"].isin(level)]

    if mode:
        candidates = candidates[candidates["mode"].isin(mode)]

    if job_type:
        candidates = candidates[candidates["type"].isin(job_type)]

    # Salary hard filter: only show jobs where salary_mid is within user range.
    # We use salary_mid (the midpoint) as the representative salary for a listing.
    candidates = candidates[
        (candidates["salary_mid"] >= salary_min) &
        (candidates["salary_mid"] <= salary_max)
    ]

    if candidates.empty:
        return pd.DataFrame()

    # ── Stage 2: Soft scoring ──────────────────────────────────────────────────

    # --- 2a. TF-IDF cosine similarity (0–60 pts) ---
    # TF-IDF turns text into a vector of word importance weights.
    # "TF" = how often a word appears in this document.
    # "IDF" = how rare the word is across all documents (rare words = more signal).
    # Cosine similarity measures the angle between two vectors — 1.0 = identical, 0.0 = nothing in common.
    #
    # We fit the vectoriser on all job specialisations, then transform both
    # the job corpus and the user's query into the same vector space.

    if skill_query.strip():
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),   # unigrams + bigrams: "full stack" counts as one feature
            stop_words="english", # remove common words like "and", "the"
            min_df=1,             # include even rare terms (small dataset)
        )

        # Fit on all job specialisations (so IDF weights are consistent)
        job_vectors = vectorizer.fit_transform(candidates["tech_specialisation"])

        # Transform the user's query into the same space
        query_vector = vectorizer.transform([skill_query])

        # Cosine similarity returns a (1 × n_jobs) matrix — flatten to 1D
        similarity_scores = cosine_similarity(query_vector, job_vectors).flatten()

        # Scale to 0–60 pts
        candidates = candidates.copy()
        candidates["skill_score"] = similarity_scores * 60
    else:
        # No skill query → all jobs get equal skill score
        candidates = candidates.copy()
        candidates["skill_score"] = 30.0  # neutral middle score

    # --- 2b. Salary fit score (0–25 pts) ---
    # Full 25 pts if job mid is inside user range.
    # Partial credit if it's close (within 20% outside the range).
    def salary_score(mid):
        if salary_min <= mid <= salary_max:
            return 25.0
        elif mid < salary_min:
            gap = salary_min - mid
            return max(0, 25 - (gap / salary_min) * 25) if salary_min > 0 else 0
        else:
            gap = mid - salary_max
            return max(0, 25 - (gap / salary_max) * 25) if salary_max > 0 else 0

    candidates["salary_score"] = candidates["salary_mid"].apply(salary_score)

    # --- 2c. Experience proximity score (0–15 pts) ---
    # Perfect score if required exp == user's exp.
    # Loses 3 pts per year of difference, floored at 0.
    def exp_score(req_exp):
        if pd.isna(req_exp):
            return 7.5  # neutral if unspecified
        diff = abs(req_exp - exp_years)
        return max(0.0, 15.0 - diff * 3.0)

    candidates["exp_score"] = candidates["work_experience_years"].apply(exp_score)

    # ── Final score ───────────────────────────────────────────────────────────
    candidates["match_score"] = (
        candidates["skill_score"] +
        candidates["salary_score"] +
        candidates["exp_score"]
    ).round(1)

    # Normalise to 0–100 range (max possible = 60+25+15 = 100)
    candidates["match_pct"] = candidates["match_score"].clip(upper=100).astype(int)

    # Sort by score and return top N
    result = candidates.sort_values("match_pct", ascending=False).head(top_n)

    return result[[
        "jobid", "tech_specialisation", "level", "mode", "type",
        "salary_from", "salary_to", "salary_mid",
        "work_experience_years", "education_level",
        "match_pct", "skill_score", "salary_score", "exp_score"
    ]].reset_index(drop=True)