from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
REF = ROOT / "data" / "reference"
CVS = ROOT / "data" / "cvs"
PROC = ROOT / "data" / "processed"

FORECAST_MONTHS = 12
MIN_MENTIONS = 30
MIN_POSTS = 50
STRENGTH = {"direct": 1.0, "supporting": 0.5, "baseline": 0.0}
LEVEL_RANK = {"beginner": 0, "intermediate": 1, "advanced": 2}

UPGRADE_FROM = {"senior_accounts": {"accounts_executive", "payroll_admin"},
                "office_supervisor": {"admin_executive", "customer_service"}}
EXPOSURE_RANK = {"Not Exposed": 0, "Minimal Exposure": 1, "Gradient 1": 2, "Gradient 2": 3, "Gradient 3": 4, "Gradient 4": 5}
PERSONAL_RE = re.compile(
    r"^\s*(name|gender|sex|age|date of birth|dob|nationality|religion|race|marital status)\s*:.*$",
    re.IGNORECASE | re.MULTILINE)


# loading
def load_data() -> dict:
    """Read every table the app needs. Raises FileNotFoundError if the pipeline has not been run."""
    d = {
        "skills": pd.read_csv(REF / "skills.csv"),
        "roles": pd.read_csv(REF / "roles.csv", dtype={"isco_code": str}),
        "ilo": pd.read_csv(REF / "ilo_exposure.csv", dtype={"isco_code": str}),
        "courses": pd.read_csv(REF / "courses.csv"),
        "sdg_goals": pd.read_csv(REF / "sdg_goals.csv"),
        "sdg_targets": pd.read_csv(REF / "sdg_targets.csv", dtype={"target": str}),
        "sources": pd.read_csv(REF / "sources.csv"),
        "sdg_map": pd.read_csv(PROC / "sdg_map.csv", dtype={"target": str}),
        "monthly": pd.read_csv(PROC / "skill_share_monthly.csv", index_col=0),
        "ai_monthly": pd.read_csv(PROC / "ai_index_monthly.csv", index_col=0),
        "trends_by_cutoff": pd.read_csv(PROC / "skill_trends_by_cutoff.csv.gz", dtype={"cutoff": str}),
        "profiles": pd.read_csv(PROC / "role_profiles.csv"),
        "role_summary": pd.read_csv(PROC / "role_summary.csv", dtype={"isco_code": str}),
        "experiment": pd.read_csv(PROC / "model_experiment.csv"),
        "summary": json.loads((PROC / "summary.json").read_text(encoding="utf-8")),
    }
    d["monthly"].index = pd.PeriodIndex(d["monthly"].index.astype(str), freq="M")
    d["ai_monthly"].index = pd.PeriodIndex(d["ai_monthly"].index.astype(str), freq="M")
    d["role_summary"]["not_recommended_because"] = d["role_summary"]["not_recommended_because"].fillna("")
    c = d["courses"]
    c["skills_list"] = c["skills"].str.split(";")
    c["level_rank"] = c["level"].map(LEVEL_RANK).fillna(1)
    c["free_confirmed"] = c["cost_rm"].eq(0)
    d["cvs"] = {p.name: p.read_text(encoding="utf-8") for p in sorted(CVS.glob("cv*.txt"))}
    return d


def trends_for(data: dict, cutoff: str) -> pd.DataFrame:
    """Skill trend table precomputed by the notebook for data up to `cutoff` (YYYY-MM)."""
    t = data["trends_by_cutoff"]
    return t[t["cutoff"] == cutoff].set_index("skill_id")


def ai_scenarios(ai_hist, h=FORECAST_MONTHS, window=24):
    """Moderate: AI adoption keeps its pace of the last 24 months. Fast: twice that pace."""
    recent = np.asarray(ai_hist)[-window:]
    pace = np.polyfit(np.arange(len(recent)), recent, 1)[0]
    now = np.asarray(ai_hist)[-3:].mean()
    steps = np.arange(1, h + 1)
    return {"moderate": np.clip(now + pace * steps, 0, 1), "fast": np.clip(now + 2 * pace * steps, 0, 1)}, pace, now


# CV reading
def compile_skill_patterns(skills: pd.DataFrame) -> dict:
    return {r.skill_id: re.compile(r.pattern, re.IGNORECASE) for r in skills.itertuples()}


def extract_skills(cv_text: str, skill_re: dict) -> dict:
    """Return {skill_id: evidence}. Personal details and the INTERESTS section are ignored."""
    body = re.split(r"^\s*INTERESTS\b", cv_text or "", flags=re.IGNORECASE | re.MULTILINE)[0]
    body = PERSONAL_RE.sub("", body)
    found = {}
    for sid, pat in skill_re.items():
        m = pat.search(body)
        if m:
            found[sid] = m.group(0)
    return found


def read_upload(name: str, data: bytes) -> str:
    """Plain text from an uploaded .txt or .pdf CV."""
    if name.lower().endswith(".pdf"):
        from io import BytesIO
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)
    return data.decode("utf-8", errors="ignore")


def cost_label(row) -> str:
    if row.get("cost_rm") == 0:
        return "free" if "certificate" not in str(row.get("funding_route", "")).lower() else "free to study, certificate fee"
    if pd.notna(row.get("cost_rm")):
        return f"RM {row['cost_rm']:.0f}"
    return str(row.get("funding_route") or "cost not stated")


# matching, pathway, SDG
@dataclass
class Radar:
    data: dict
    trends: pd.DataFrame

    def __post_init__(self):
        d = self.data
        self.skill_name = d["skills"].set_index("skill_id")["skill_name"]
        self.role_name = d["roles"].set_index("role_id")["role_name"]
        self.goal_name = d["sdg_goals"].set_index("goal")["goal_name"]
        self.goal_colour = d["sdg_goals"].set_index("goal")["colour_hex"]
        self.summary = d["role_summary"].set_index("role_id")
        prof = d["profiles"]
        self.core = prof[~prof["transferable"]]
        self.transferable = prof[prof["transferable"]]

    def future_factor(self, scenario: str) -> pd.Series:
        """Only skills with a clear rising or declining trend move the match; the rest stay at 1."""
        g = self.trends[f"growth_{scenario}"].where(self.trends["trend"].isin(["rising", "declining"]), 1.0)
        return g.fillna(1.0).clip(0.5, 2.0)

    def importance(self, role_id: str, scenario: str = "moderate") -> pd.Series:
        w = self.core[self.core["role_id"] == role_id].set_index("skill_id")["weight"]
        return (w * self.future_factor(scenario).reindex(w.index).fillna(1.0)).sort_values(ascending=False)

    def match(self, role_id: str, skill_set, scenario: str = "moderate") -> float:
        imp = self.importance(role_id, scenario)
        return float(imp[imp.index.isin(list(skill_set))].sum() / imp.sum()) if imp.sum() > 0 else 0.0

    def recommend(self, skill_set) -> pd.DataFrame:
        rows = []
        for r in self.data["roles"].itertuples():
            imp = self.importance(r.role_id)
            s = self.summary.loc[r.role_id]
            mod, fast = self.match(r.role_id, skill_set, "moderate"), self.match(r.role_id, skill_set, "fast")
            rows.append({
                "role_id": r.role_id, "role": r.role_name, "type": r.role_type, "description": r.description,
                "match_moderate": mod, "match_fast": fast, "match_low": min(mod, fast), "match_high": max(mod, fast),
                "gaps": [g for g in imp.index if g not in skill_set][:5],
                "posts": int(s["posts"]), "limited_data": int(s["posts"]) < MIN_POSTS,
                "isco_code": r.isco_code, "isco_title": r.isco_title,
                "ilo_score": s["ilo_score"], "ilo_gradient": s["ilo_gradient"],
                "exposure_rank": EXPOSURE_RANK.get(s["ilo_gradient"], 9),
                "transferability": s["transferability"], "recommended": bool(s["recommended"]),
                "not_recommended_because": s["not_recommended_because"],
            })
        return pd.DataFrame(rows).sort_values("match_moderate", ascending=False).reset_index(drop=True)

    def explain(self, role_id: str, skill_set: dict) -> pd.DataFrame:
        w = self.core[self.core["role_id"] == role_id].set_index("skill_id")["weight"]
        g = self.future_factor("moderate").reindex(w.index).fillna(1.0)
        t = pd.DataFrame({"Skill": self.skill_name.reindex(w.index).values,
                          "Share of job posts": w.values, "Future factor": g.values,
                          "Market trend": self.trends["trend"].reindex(w.index).values,
                          "In your profile": w.index.isin(list(skill_set)),
                          "Evidence": [skill_set.get(s, "") if isinstance(skill_set, dict) else "" for s in w.index]},
                         index=w.index)
        t["Importance"] = t["Share of job posts"] * t["Future factor"]
        return t.sort_values("Importance", ascending=False)

    def course_options(self, skill_id: str) -> pd.DataFrame:
        c = self.data["courses"]
        c = c[c["skills_list"].map(lambda s: skill_id in s)].copy()
        c["n_skills"] = c["skills_list"].map(len)
        c["has_hours"] = c["hours"].notna()
        return c.sort_values(["level_rank", "free_confirmed", "n_skills", "has_hours", "hours"],
                             ascending=[True, False, True, False, True])

    def pathway(self, role_id: str, skill_set, max_skills: int = 6):
        """Ordered plan from the course catalogue only. Returns (plan, skills covered, extra options)."""
        courses = self.data["courses"]
        imp = self.importance(role_id)
        gaps = imp[~imp.index.isin(list(skill_set))].head(max_skills)
        covered, steps, extras = set(), [], []
        for skill in gaps.index:
            if skill in covered:
                continue
            cands = courses[courses["skills_list"].map(lambda s: skill in s)].copy()
            if cands.empty:
                steps.append({"skill_id": skill, "skill": self.skill_name[skill],
                              "course": "No free course in our catalogue yet", "provider": "", "level": "",
                              "level_rank": 9, "hours": np.nan, "cost": "", "url": "",
                              "covers": self.skill_name[skill], "importance": gaps[skill], "checked_on": ""})
                continue
            cands["n_gaps"] = cands["skills_list"].map(lambda s: len((set(s) & set(gaps.index)) - covered))
            cands["n_skills"] = cands["skills_list"].map(len)
            cands["has_hours"] = cands["hours"].notna()
            ranked = cands.sort_values(["level_rank", "free_confirmed", "n_gaps", "n_skills", "has_hours", "hours"],
                                       ascending=[True, False, False, True, False, True])
            best = ranked.iloc[0]
            new = (set(best["skills_list"]) & set(gaps.index)) - covered
            covered |= new
            steps.append({"skill_id": skill, "skill": self.skill_name[skill], "course": best["title"],
                          "provider": best["provider"], "level": best["level"], "level_rank": best["level_rank"],
                          "hours": best["hours"], "cost": cost_label(best), "url": best["url"],
                          "covers": ", ".join(self.skill_name[s] for s in new), "importance": gaps[skill],
                          "checked_on": best["checked_on"]})
            for e in ranked.iloc[1:4].to_dict("records"):
                extras.append({"skill_id": skill, "course": e["title"], "provider": e["provider"], "level": e["level"],
                               "hours": e["hours"], "cost": cost_label(e), "url": e["url"]})
        cols = ["skill_id", "skill", "course", "provider", "level", "level_rank", "hours", "cost", "url", "covers",
                "importance", "checked_on"]
        plan = pd.DataFrame(steps, columns=cols).sort_values(["level_rank", "importance"], ascending=[True, False])
        extra = pd.DataFrame(extras, columns=["skill_id", "course", "provider", "level", "hours", "cost", "url"])
        return plan.drop(columns=["level_rank"]).reset_index(drop=True), covered, extra

    def sdg_links(self, role_id: str, skill_ids) -> pd.DataFrame:
        m = self.data["sdg_map"]
        rows = m[((m["entity_type"] == "role") & (m["entity_id"] == role_id)) |
                 ((m["entity_type"] == "skill") & (m["entity_id"].isin(list(skill_ids))))].copy()
        rows["name"] = [self.role_name.get(e, self.skill_name.get(e, e)) for e in rows["entity_id"]]
        rows["goal_name"] = rows["goal"].map(self.goal_name)
        return rows.merge(self.data["sdg_targets"][["target", "target_summary"]], on="target", how="left")

    def sdg_score(self, role_id: str, skill_ids, goals) -> float:
        if not goals:
            return 0.0
        v = self.sdg_links(role_id, skill_ids)
        v = v[v["goal"].isin(goals)]
        if v.empty:
            return 0.0
        per_goal = v.assign(w=v["strength"].map(STRENGTH)).groupby("goal")["w"].max()
        return float(per_goal.reindex(goals).fillna(0).mean())
