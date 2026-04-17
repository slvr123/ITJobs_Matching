import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist


# ── Cluster labels (human-readable names derived from top TF-IDF terms) ───────
_CLUSTER_NAMES = {}
_KMEANS_MODEL  = None
_TFIDF_MODEL   = None

# ── Privacy threshold (Differential Privacy / Minimum Sample Size) ────────────
# Any group with fewer than this many records will have salary data suppressed
# to prevent re-identification of individuals.
# Aligns with GDPR Article 5 and the Philippine Data Privacy Act of 2012.
PRIVACY_THRESHOLD = 5


def apply_privacy_threshold(df: pd.DataFrame, group_col: str, salary_col: str = "salary_mid") -> pd.DataFrame:
    """
    Suppress salary data for groups below the minimum sample threshold.

    For each unique value in group_col, if the group has fewer than
    PRIVACY_THRESHOLD records, the salary_col values are replaced with NaN
    and a 'privacy_suppressed' flag is set to True.

    This prevents re-identification attacks where a small group (e.g. 1–2 jobs
    in a niche cluster) could expose an individual's salary.

    Parameters
    ----------
    df         : DataFrame to process (copy is made internally)
    group_col  : column to group by (e.g. "level", "kmeans_label")
    salary_col : salary column to suppress

    Returns
    -------
    DataFrame with suppressed rows flagged and salary set to NaN.
    """
    df = df.copy()
    df["privacy_suppressed"] = False
    group_sizes = df.groupby(group_col)[salary_col].transform("count")
    mask = group_sizes < PRIVACY_THRESHOLD
    df.loc[mask, salary_col] = np.nan
    df.loc[mask, "privacy_suppressed"] = True
    return df


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


def build_clusters(df: pd.DataFrame, n_clusters: int = 8) -> pd.DataFrame:
    """
    Cluster all jobs using two techniques and return an enriched DataFrame.

    ── K-Means clustering ────────────────────────────────────────────────────
    K-Means partitions jobs into K groups by minimising intra-cluster variance.
    Each job is assigned to the nearest centroid in TF-IDF vector space.
    We also mix in normalised salary and experience so clusters reflect both
    skills AND seniority/pay band — not just text similarity.

    Feature matrix per job:
      - TF-IDF vector of tech_specialisation  (text → skill fingerprint)
      - normalised salary_mid                 (pay band signal)
      - normalised work_experience_years      (seniority signal)

    ── Hierarchical clustering ───────────────────────────────────────────────
    Ward linkage builds a bottom-up tree: start with every job as its own
    cluster, then repeatedly merge the pair whose merge increases total
    within-cluster variance the least.  We cut the tree at n_clusters to get
    flat labels, but the full linkage matrix is returned for the dendrogram.

    ── PCA projection ────────────────────────────────────────────────────────
    We reduce the high-dimensional TF-IDF matrix to 2D with PCA so we can
    plot every job as a dot on a scatter chart.

    Returns
    -------
    df_out : DataFrame — original df + columns:
        kmeans_cluster      int   cluster id (0-based)
        kmeans_label        str   human-readable cluster name
        hier_cluster        int   hierarchical cluster id
        pca_x, pca_y        float 2-D coordinates for scatter plot
    linkage_matrix          stored as df_out.attrs["linkage_matrix"]
    cluster_names           stored as df_out.attrs["cluster_names"]
    """
    global _CLUSTER_NAMES, _KMEANS_MODEL, _TFIDF_MODEL

    df_out = df.copy().reset_index(drop=True)

    # ── 1. TF-IDF on specialisation text ─────────────────────────────────────
    _TFIDF_MODEL = TfidfVectorizer(
        ngram_range=(1, 2),
        stop_words="english",
        min_df=2,          # ignore terms appearing in only 1 job
        max_features=300,  # cap vocabulary for speed
    )
    tfidf_matrix = _TFIDF_MODEL.fit_transform(df_out["tech_specialisation"]).toarray()

    # ── 2. Numeric features (salary + experience) ────────────────────────────
    scaler = StandardScaler()
    numeric_cols = df_out[["salary_mid", "work_experience_years"]].fillna(
        df_out[["salary_mid", "work_experience_years"]].median()
    )
    numeric_scaled = scaler.fit_transform(numeric_cols)

    # Weight numeric features — give text 80% of the signal, numeric 20%
    feature_matrix = np.hstack([tfidf_matrix * 0.8, numeric_scaled * 0.2])

    # ── 3. K-Means ────────────────────────────────────────────────────────────
    _KMEANS_MODEL = KMeans(
        n_clusters=n_clusters,
        random_state=42,
        n_init=10,          # run 10 times, keep best inertia
        max_iter=300,
    )
    kmeans_labels = _KMEANS_MODEL.fit_predict(feature_matrix)
    df_out["kmeans_cluster"] = kmeans_labels

    # Name each cluster by its top-3 TF-IDF terms at the centroid
    feature_names = _TFIDF_MODEL.get_feature_names_out()
    cluster_names = {}
    for cid in range(n_clusters):
        # centroid in TF-IDF space (first len(feature_names) dims)
        centroid = _KMEANS_MODEL.cluster_centers_[cid, : len(feature_names)]
        top_idx  = centroid.argsort()[::-1][:3]
        top_terms = [feature_names[i].title() for i in top_idx]
        cluster_names[cid] = " / ".join(top_terms)

    _CLUSTER_NAMES = cluster_names
    df_out["kmeans_label"] = df_out["kmeans_cluster"].map(cluster_names)

    # ── 4. Hierarchical clustering (Ward linkage) ─────────────────────────────
    # pdist on the full feature matrix, then Ward linkage
    dist_matrix   = pdist(feature_matrix, metric="euclidean")
    link_matrix   = linkage(dist_matrix, method="ward")
    hier_labels   = fcluster(link_matrix, t=n_clusters, criterion="maxclust")
    df_out["hier_cluster"] = hier_labels

    # ── 5. PCA → 2D for scatter plot ──────────────────────────────────────────
    pca = PCA(n_components=2, random_state=42)
    coords = pca.fit_transform(feature_matrix)
    df_out["pca_x"] = coords[:, 0]
    df_out["pca_y"] = coords[:, 1]

    # Stash linkage matrix and names in DataFrame attrs for the dashboard
    df_out.attrs["linkage_matrix"] = link_matrix
    df_out.attrs["cluster_names"]  = cluster_names

    return df_out


def get_cluster_for_query(skill_query: str, n_clusters: int = 8) -> int | None:
    """
    Given a free-text skill query, predict which K-Means cluster it belongs to.
    Returns None if the model hasn't been built yet.
    """
    if _KMEANS_MODEL is None or _TFIDF_MODEL is None:
        return None
    try:
        vec = _TFIDF_MODEL.transform([skill_query]).toarray()
        # Pad with zeros for the numeric dims (salary/exp unknown for query)
        numeric_zeros = np.zeros((1, 2))
        feature_vec   = np.hstack([vec * 0.8, numeric_zeros * 0.2])
        return int(_KMEANS_MODEL.predict(feature_vec)[0])
    except Exception:
        return None


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
    Three-stage matching:

    Stage 1 — Hard filters
      Remove any job that fails a non-negotiable constraint.
      If the user picks "Any" for a filter, we skip that constraint entirely.

    Stage 2 — Soft scoring
      Score each surviving job 0–100 based on:
        - TF-IDF cosine similarity on tech_specialisation (up to 55 pts)
        - Salary fit: does the job's mid-point land in the user's range? (up to 25 pts)
        - Experience proximity: how close is the job's required exp to the user's? (up to 15 pts)

    Stage 3 — Cluster boost (up to 5 pts)
      If the K-Means model has been built (via build_clusters), predict which
      cluster the user's query belongs to.  Jobs in the same cluster get a
      small bonus — this rewards specialisation-level similarity beyond
      what raw TF-IDF cosine captures.

    We then sort by score descending and return the top N.
    """

    candidates = df.copy()

    # ── Stage 1: Hard filters ──────────────────────────────────────────────────
    if level:
        candidates = candidates[candidates["level"].isin(level)]
    if mode:
        candidates = candidates[candidates["mode"].isin(mode)]
    if job_type:
        candidates = candidates[candidates["type"].isin(job_type)]

    candidates = candidates[
        (candidates["salary_mid"] >= salary_min) &
        (candidates["salary_mid"] <= salary_max)
    ]

    if candidates.empty:
        return pd.DataFrame()

    # ── Stage 2: Soft scoring ──────────────────────────────────────────────────

    # --- 2a. TF-IDF cosine similarity (0–55 pts) ---
    # Slightly reduced from 60 to make room for the cluster boost (5 pts).
    if skill_query.strip():
        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            stop_words="english",
            min_df=1,
        )
        job_vectors   = vectorizer.fit_transform(candidates["tech_specialisation"])
        query_vector  = vectorizer.transform([skill_query])
        similarity_scores = cosine_similarity(query_vector, job_vectors).flatten()
        candidates = candidates.copy()
        candidates["skill_score"] = similarity_scores * 55
    else:
        candidates = candidates.copy()
        candidates["skill_score"] = 27.5  # neutral middle score

    # --- 2b. Salary fit score (0–25 pts) ---
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
    def exp_score(req_exp):
        if pd.isna(req_exp):
            return 7.5
        diff = abs(req_exp - exp_years)
        return max(0.0, 15.0 - diff * 3.0)

    candidates["exp_score"] = candidates["work_experience_years"].apply(exp_score)

    # ── Stage 3: Cluster boost (0–5 pts) ──────────────────────────────────────
    # Predict which K-Means cluster the user's query falls into.
    # Jobs already in that cluster get +5 pts — they're in the same
    # "neighbourhood" of the job market as what the user described.
    user_cluster = get_cluster_for_query(skill_query) if skill_query.strip() else None

    if user_cluster is not None and "kmeans_cluster" in candidates.columns:
        candidates["cluster_boost"] = candidates["kmeans_cluster"].apply(
            lambda c: 5.0 if c == user_cluster else 0.0
        )
    else:
        candidates["cluster_boost"] = 0.0

    # ── Final score ───────────────────────────────────────────────────────────
    candidates["match_score"] = (
        candidates["skill_score"] +
        candidates["salary_score"] +
        candidates["exp_score"] +
        candidates["cluster_boost"]
    ).round(1)

    # Max possible = 55 + 25 + 15 + 5 = 100
    candidates["match_pct"] = candidates["match_score"].clip(upper=100).astype(int)

    result = candidates.sort_values("match_pct", ascending=False).head(top_n)

    return result[[
        "jobid", "tech_specialisation", "level", "mode", "type",
        "salary_from", "salary_to", "salary_mid",
        "work_experience_years", "education_level",
        "match_pct", "skill_score", "salary_score", "exp_score", "cluster_boost"
    ]].reset_index(drop=True)