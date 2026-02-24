# app.py
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")

st.title("Provisional Natality Data Dashboard")
st.subheader("Birth Analysis by State and Gender")


def _normalize_colname(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_")


def _canonical_key(name: str) -> str:
    # Remove non-alphanumerics to support flexible matching (underscores, dashes, etc.)
    s = _normalize_colname(name)
    return "".join(ch for ch in s if ch.isalnum())


def _match_logical_fields(columns_norm):
    """
    Returns a dict mapping logical field -> actual normalized column name in df.
    Performs:
      1) Exact normalized match
      2) Canonical (alnum-only) match
      3) Known aliases (without assuming extra columns)
    """
    logical_required = [
        "state_of_residence",
        "month",
        "month_code",
        "year_code",
        "sex_of_infant",
        "births",
    ]

    cols_set = set(columns_norm)
    cols_canon_map = {c: _canonical_key(c) for c in columns_norm}
    canon_to_cols = {}
    for c, ck in cols_canon_map.items():
        canon_to_cols.setdefault(ck, []).append(c)

    # Light aliasing only for the required logical fields
    alias_candidates = {
        "state_of_residence": ["state_of_residence", "state", "state_residence", "residence_state"],
        "month": ["month", "month_of_birth", "birth_month"],
        "month_code": ["month_code", "monthcode", "month_cd", "month_cd_code", "monthnumber", "month_num", "monthnumbercode"],
        "year_code": ["year_code", "yearcode", "year_cd", "year"],
        "sex_of_infant": ["sex_of_infant", "sex", "infant_sex", "sex_of_child"],
        "births": ["births", "birth", "birth_count", "count", "number_of_births", "num_births"],
    }

    matched = {}

    for logical in logical_required:
        # 1) Exact normalized match
        if logical in cols_set:
            matched[logical] = logical
            continue

        # 2) Canonical match (e.g., "State of Residence" -> "state_of_residence")
        target_canon = _canonical_key(logical)
        if target_canon in canon_to_cols and len(canon_to_cols[target_canon]) >= 1:
            # If multiple candidates collide, pick the shortest (often the cleanest)
            candidates = sorted(canon_to_cols[target_canon], key=lambda x: (len(x), x))
            matched[logical] = candidates[0]
            continue

        # 3) Alias-based match (normalized then canonical)
        found = None
        for alias in alias_candidates.get(logical, []):
            alias_norm = _normalize_colname(alias)
            if alias_norm in cols_set:
                found = alias_norm
                break
            alias_canon = _canonical_key(alias_norm)
            if alias_canon in canon_to_cols:
                candidates = sorted(canon_to_cols[alias_canon], key=lambda x: (len(x), x))
                found = candidates[0]
                break
        if found is not None:
            matched[logical] = found

    return matched


# STEP 3 â€” Load Data
try:
    df = pd.read_csv("Provisional_Natality_2025_CDC.csv")
except FileNotFoundError:
    st.error("Dataset file not found in repository.")
    st.stop()
except Exception as e:
    st.error("An unexpected error occurred while loading the dataset.")
    st.write(e)
    st.stop()

# Normalize column names
df = df.copy()
df.columns = [_normalize_colname(c) for c in df.columns]

# Validate required fields (dynamic matching)
required_logical_fields = [
    "state_of_residence",
    "month",
    "month_code",
    "year_code",
    "sex_of_infant",
    "births",
]
field_map = _match_logical_fields(list(df.columns))

missing_logical = [f for f in required_logical_fields if f not in field_map]
if missing_logical:
    st.error(
        "Missing required logical fields: "
        + ", ".join(missing_logical)
        + ". Please verify the dataset column names."
    )
    st.write(df.columns)
    st.stop()

# Rename matched columns to the canonical logical names (keeps remaining columns intact)
rename_dict = {field_map[k]: k for k in required_logical_fields if k in field_map}
df = df.rename(columns=rename_dict)

# Convert births to numeric and drop null births
df["births"] = pd.to_numeric(df["births"], errors="coerce")
df = df.dropna(subset=["births"])

# Coerce filter columns to string for stable multiselect display (without fabricating categories)
for c in ["state_of_residence", "month", "sex_of_infant"]:
    df[c] = df[c].astype(str).str.strip()

# STEP 4 â€” Sidebar Filters (multiselect only, with "All" option)
def _build_options(series: pd.Series):
    vals = sorted([v for v in series.dropna().unique().tolist() if str(v).strip() != ""])
    return ["All"] + vals


month_options = _build_options(df["month"])
gender_options = _build_options(df["sex_of_infant"])
state_options = _build_options(df["state_of_residence"])

selected_months = st.sidebar.multiselect("Month", options=month_options, default=["All"])
selected_genders = st.sidebar.multiselect("Gender", options=gender_options, default=["All"])
selected_states = st.sidebar.multiselect("State", options=state_options, default=["All"])

# STEP 5 â€” Filtering Logic (do not modify original df)
df_filtered = df

if "All" not in selected_months:
    df_filtered = df_filtered[df_filtered["month"].isin(selected_months)]

if "All" not in selected_genders:
    df_filtered = df_filtered[df_filtered["sex_of_infant"].isin(selected_genders)]

if "All" not in selected_states:
    df_filtered = df_filtered[df_filtered["state_of_residence"].isin(selected_states)]

# STEP 9 â€” Edge Case Handling: empty result
if df_filtered.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

# STEP 6 â€” Aggregation
df_agg = (
    df_filtered.groupby(["state_of_residence", "sex_of_infant"], as_index=False)["births"]
    .sum()
    .sort_values(by=["state_of_residence", "sex_of_infant"], ascending=[True, True])
)

# STEP 7 â€” Plot
fig = px.bar(
    df_agg,
    x="state_of_residence",
    y="births",
    color="sex_of_infant",
    title="Total Births by State and Gender",
)

fig.update_layout(
    plot_bgcolor="white",
    paper_bgcolor="white",
    legend_title_text="Gender",
    xaxis_title="State of Residence",
    yaxis_title="Births",
    margin=dict(l=20, r=20, t=60, b=40),
)

st.plotly_chart(fig, use_container_width=True)

# STEP 8 â€” Show Filtered Table (clean display, no index)
display_cols = ["state_of_residence", "month", "month_code", "year_code", "sex_of_infant", "births"]
df_table = df_filtered.loc[:, [c for c in display_cols if c in df_filtered.columns]].copy()

st.dataframe(df_table.reset_index(drop=True), use_container_width=True)
