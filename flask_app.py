"""JOBRIDGE: Flask backend (v2).

Run locally:  python flask_app.py          (or: flask --app flask_app run)
Then open     http://localhost:5000

Pipeline:  Jobridge_pipeline.ipynb writes data/reference, data/cvs and data/processed;
           core.py reads those files and does every calculation (matching, pathway, SDG scoring);
           this file serves the page (templates/jobridge.html with static/jobridge.js) and the JSON API below.
The page holds no data of its own: every number it shows comes from this API, which calls core.py.
When the notebook is run again, the new data is picked up on the next request (no restart needed).

API
  GET  /api/meta                   cutoff months, SDG goals, skill dictionary, sample CVs, sample team, team roles
  POST /api/extract                CV as JSON {"text"} or as a .txt/.pdf file (form field cv_file) -> skills found
  POST /api/analyze                {cutoff, skills, sdg, sdg_weight, path_role} -> profile, role options, pathway
  GET  /api/radar?cutoff=          AI Adoption Index and its two scenarios, rising and declining skills
  GET  /api/skill?cutoff=&skill=   one skill's share of job posts and its 12 month scenarios
  POST /api/team                   {cutoff, role, members: [{name, skills}]} -> team readiness grid
  GET  /api/about?cutoff=          method, model backtest, fairness check, roles, sources
Errors come back as {"error": message}: 400 bad input, 413 upload too large, 500 data files missing.
"""

import html
import math
import os
import re
from functools import lru_cache
from types import SimpleNamespace

import numpy as np
import pandas as pd
from flask import Flask, Response, jsonify, render_template, request
from markupsafe import Markup
from plotly.offline import get_plotlyjs

import core

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024    # one upload, up to 20 MB

TREND_ICON = {"rising": "▲ rising", "declining": "▼ declining", "stable": "● stable", "limited data": "○ limited data"}
ILO_NOTE = "ILO Working Paper 140 (2025), Table A1. Gradient 4 is the most exposed to generative AI; exposure is not the same as job loss."
DEFAULT_SDG, DEFAULT_SDG_WEIGHT, MAX_SDG_WEIGHT = [8, 12, 13], 0.15, 0.3
BADGE = {"now": "Where you are now", "upgrade": "Upgrade in your field", "move": "Move", "other": "Not recommended",
         "origin": "Starting role"}
PATH_LABEL = {"upgrade": "upgrade", "move": "move", "other": "not recommended", "now": "current role"}


# ---------------------------------------------------------------- data
_cache = {"version": None, "state": None}


def _data_version():
    """Latest change time of the files the pipeline notebook writes (data/reference, data/cvs, data/processed)."""
    return max((f.stat().st_mtime_ns for d in (core.REF, core.CVS, core.PROC) if d.is_dir()
                for f in d.iterdir() if f.is_file()), default=0)


def get_data():
    """Loaded once and reused, but reloaded when the notebook writes new data,
    so a pipeline re-run shows up without restarting Flask. While the notebook is still writing (a half
    written file fails to load), the previous data keeps being served."""
    version = _data_version()
    if _cache["version"] != version:
        try:
            _cache["state"], _cache["version"] = _build_state(core.load_data()), version
        except Exception:
            if _cache["state"] is None:
                raise
    return _cache["state"]


def _build_state(data):
    summary = data["summary"]
    skills_df = data["skills"]
    skill_name = skills_df.set_index("skill_id")["skill_name"]
    roles = data["roles"]
    months = [str(m) for m in data["monthly"].index]
    cutoff_options = sorted(data["trends_by_cutoff"]["cutoff"].unique())
    retrieved = str(summary.get("hn_retrieved_at_utc", "unknown"))[:10]
    return SimpleNamespace(
        data=data, summary=summary, skills_df=skills_df,
        SKILL_RE=core.compile_skill_patterns(skills_df),
        SKILL_NAME=skill_name, SKILL_IDS=set(skill_name.index),
        goals=[int(x) for x in data["sdg_goals"]["goal"]],
        team_roles=list(roles.loc[roles["role_type"] != "origin", "role_id"]),
        months=months, cutoff_options=cutoff_options, latest=cutoff_options[-1], retrieved=retrieved,
        SOURCE_NOTE=(f"Source: Hacker News 'Ask HN: Who is hiring?' monthly threads ({months[0]} to {months[-1]}, "
                     f"{summary.get('hn_posts', 0):,} job posts), retrieved {retrieved}."))


# ---------------------------------------------------------------- formatting helpers
def joined(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def pct(x, digits=0):
    return "n/a" if pd.isna(x) else f"{x * 100:.{digits}f}%"


def pct_range(a, b):
    lo, hi = pct(min(a, b)), pct(max(a, b))
    return lo if lo == hi else f"{lo} to {hi}"


def hours_text(h):
    return f"{h:g} h" if pd.notna(h) else "duration not stated"


def persona_label(name, text):
    who = re.search(r"^Name:\s*(.+)$", text, re.MULTILINE)
    role = re.search(r"^Current (?:role|status):\s*(.+)$", text, re.MULTILINE)
    return f"{who.group(1).split()[0] if who else name}: {role.group(1) if role else name}"


def _inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)


def md(text):
    """The Markdown subset the page text uses: **bold**, [text](url), '* ' and '1. ' lists, paragraphs."""
    blocks, items, kind = [], [], None

    def flush():
        nonlocal items, kind
        if items:
            blocks.append(f"<{kind}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{kind}>")
        items, kind = [], None

    for line in (text or "").split("\n"):
        m = re.match(r"^\s*(\*|\d+\.)\s+(.*)$", line)
        if m:
            k = "ul" if m.group(1) == "*" else "ol"
            if k != kind:
                flush()
                kind = k
            items.append(_inline(m.group(2)))
        else:
            flush()
            if line.strip():
                blocks.append(f"<p>{_inline(line)}</p>")
    flush()
    return Markup("".join(blocks))


def as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def as_float(value, default):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


# ---------------------------------------------------------------- JSON helpers
def plain(v):
    """A value JSON can carry: numpy scalars become Python numbers, NaN becomes null (JSON.parse rejects NaN)."""
    if isinstance(v, dict):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray, pd.Series, pd.Index)):
        return [plain(x) for x in v]
    if v is None or v is pd.NA:
        return None
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def api(payload, status=200):
    return jsonify(plain(payload)), status


def api_error(message, status=400):
    return jsonify(error=message), status


def _body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


def _cutoff(g, value):
    return value if value in g.cutoff_options else g.latest


def _skill_set(g, raw):
    """{skill_id: evidence} sent by the page; unknown skills are dropped and evidence is kept short."""
    if not isinstance(raw, dict):
        return {}
    return {s: str(e or "added by you")[:120] for s, e in raw.items() if s in g.SKILL_IDS}


def _sdg_pref(g, raw):
    chosen = {as_int(x, None) for x in raw} if isinstance(raw, list) else set()
    return [goal for goal in g.goals if goal in chosen]


def _radar(g, cutoff):
    trends = core.trends_for(g.data, cutoff)
    return trends, core.Radar(g.data, trends)


# ---------------------------------------------------------------- matching, role cards and pathway
def rank_roles(radar, skill_set, sdg_pref, sdg_weight):
    """Every role with its match, SDG score and group, plus the closest current role.
    Groups: now = closest current role; origin = the other high exposure starting roles (not suggested);
    upgrade = same field, one level up; move = passes the recommendation rule; other = checked but not recommended."""
    rec = radar.recommend(skill_set)
    sdg_scores = []
    for r in rec.itertuples():
        _, learned, _ = radar.pathway(r.role_id, skill_set)
        sdg_scores.append(radar.sdg_score(r.role_id, learned | set(skill_set), sdg_pref))
    rec["sdg_score"] = sdg_scores
    rec["final_score"] = rec["match_moderate"] + sdg_weight * rec["sdg_score"]
    current_id = rec.loc[rec["type"] == "origin", "role_id"].iloc[0]
    in_field = rec["role_id"].map(lambda r: current_id in core.UPGRADE_FROM.get(r, set()))
    rec["group"] = np.select([rec["role_id"] == current_id, rec["type"] == "origin", in_field, rec["recommended"]],
                             ["now", "origin", "upgrade", "move"], "other")
    return rec, next(rec[rec["group"] == "now"].itertuples())


def role_json(r, ctx, show_sdg=True):
    """One role card: match, ILO exposure, transferability, gaps, SDG fit and the 'why this score' table."""
    cur = ctx.current
    exposure = None
    if r.group != "now":
        step = cur.exposure_rank - r.exposure_rank
        verdict = (f"{step} level{'s' if step > 1 else ''} less exposed" if step > 0 else
                   "same exposure" if step == 0 else "more exposed")
        exposure = {"from": cur.ilo_gradient, "to": r.ilo_gradient, "from_score": f"{cur.ilo_score:.2f}",
                    "to_score": f"{r.ilo_score:.2f}", "verdict": verdict}
    ex = ctx.radar.explain(r.role_id, ctx.skill_set)
    return {
        "role_id": r.role_id, "role": r.role, "group": r.group, "badge": BADGE[r.group], "description": r.description,
        "match": pct_range(r.match_low, r.match_high), "ilo_gradient": r.ilo_gradient, "exposure_rank": r.exposure_rank,
        "ilo_note": f"ISCO {r.isco_code} {r.isco_title}, mean task score {r.ilo_score:.2f}. {ILO_NOTE}",
        "transferability": pct(r.transferability), "posts": f"{r.posts:,}", "exposure": exposure,
        "limited": (f"Limited data: only {r.posts} job posts for this role, so treat this match with caution."
                    if r.limited_data else None),
        "gaps": [{"name": ctx.g.SKILL_NAME[s], "trend": ctx.trends.loc[s, "trend"]} for s in r.gaps],
        "sdg": ({"fit": pct(r.sdg_score), "ranking": pct(r.final_score), "match": pct(r.match_moderate)}
                if show_sdg and ctx.sdg_pref else None),
        "explain": [{"skill": e["Skill"], "share": e["Share of job posts"], "future_factor": e["Future factor"],
                     "trend": e["Market trend"], "in_profile": e["In your profile"], "evidence": e["Evidence"],
                     "importance": e["Importance"]} for e in ex.to_dict("records")],
    }


def pathway_json(ctx, rec, requested):
    """The reskilling plan for one role: the best upgrade or move, unless the page asks for another role."""
    radar, skill_set, cur = ctx.radar, ctx.skill_set, ctx.current
    order = pd.concat([rec[rec["group"].isin(["upgrade", "move"])].sort_values("final_score", ascending=False),
                       rec[rec["group"] == "other"].sort_values("final_score", ascending=False),
                       rec[rec["group"] == "now"]])
    info = order.set_index("role_id")
    ids = list(order["role_id"])
    role_id = requested if isinstance(requested, str) and requested in ids else ids[0]
    plan, learned, extras = radar.pathway(role_id, skill_set)
    after = set(skill_set) | learned
    hours = plan["hours"].sum()
    unknown = int((plan["hours"].isna() & (plan["url"] != "")).sum())
    steps = []
    for i, s in enumerate(plan.itertuples(), start=1):
        step = {"i": i, "skill_id": s.skill_id, "skill": s.skill, "url": s.url}
        if s.url:
            step.update(course=s.course, provider=s.provider, level=s.level, hours=hours_text(s.hours), cost=s.cost,
                        covers=s.covers, checked_on=s.checked_on,
                        more=[{"course": e.course, "url": e.url, "provider": e.provider, "level": e.level,
                               "hours": hours_text(e.hours), "cost": e.cost}
                              for e in extras[extras["skill_id"] == s.skill_id].itertuples()])
        steps.append(step)
    links = radar.sdg_links(role_id, after)
    specific = links[links["strength"] != "baseline"].sort_values(["goal", "strength"])
    sdg = [{"title": f"SDG {goal}: {radar.goal_name[goal]}", "colour": radar.goal_colour.get(goal, "#888888"),
            "links": [{"target": l.target, "strength": l.strength, "name": l.name, "rationale": l.rationale}
                      for l in grp.itertuples()]}
           for goal, grp in specific.groupby("goal")]
    return {
        "options": [{"id": r, "label": f"{radar.role_name[r]} ({PATH_LABEL[info.loc[r, 'group']]}, "
                                        f"{pct(info.loc[r, 'match_moderate'])} match now)"} for r in ids],
        "role_id": role_id, "role": radar.role_name[role_id],
        "match_now": pct_range(radar.match(role_id, skill_set, "moderate"), radar.match(role_id, skill_set, "fast")),
        "match_after": pct_range(radar.match(role_id, after, "moderate"), radar.match(role_id, after, "fast")),
        "hours": f"{hours:.1f} h" if hours else "not stated",
        "hours_note": f"{unknown} course(s) do not state a duration." if unknown else "Stated by the course providers",
        "exposure": info.loc[role_id, "ilo_gradient"], "exposure_from": f"From {cur.ilo_gradient} today",
        "exposure_note": ILO_NOTE, "steps": steps, "sdg": sdg,
        "course_caption": (f"Courses come only from our checked catalogue of {len(ctx.g.data['courses'])} free or low "
                           "cost courses (Alison, OpenLearn, Microsoft Learn, Kaggle, Cisco Networking Academy, "
                           "Atlassian, HRD Corp e LATiH and others). Steps go from beginner upwards. Where a page gives "
                           "a range of hours, the upper figure is used. For HRD Corp e LATiH, sign in to confirm "
                           "whether a course is free or premium."),
    }


def default_skill(trends, skills_df):
    """The skill the radar shows first: the one with the largest forecast rise."""
    rising = trends[trends["trend"] == "rising"]
    return rising.sort_values("change_pp_moderate").index[-1] if len(rising) else skills_df["skill_id"].iloc[0]


# ---------------------------------------------------------------- page, errors and static files
@app.route("/")
def home():
    get_data()   # missing data files show the error page instead of an empty app
    return render_template("jobridge.html")


@app.route("/plotly.min.js")
def plotly_js():
    return Response(_plotly_js(), mimetype="application/javascript", headers={"Cache-Control": "public, max-age=86400"})


@lru_cache(maxsize=1)
def _plotly_js():
    return get_plotlyjs()


@app.errorhandler(FileNotFoundError)
def data_missing(err):
    message = (f"Data files are missing ({err.filename}). Run Jobridge_pipeline.ipynb first, "
               "then upload the data/reference, data/cvs and data/processed folders.")
    if request.path.startswith("/api/"):
        return api_error(message, 500)
    return render_template("error.html", message=message), 500


@app.errorhandler(413)
def too_large(_err):
    message = "The upload is too large. Please upload under 20 MB at a time."
    if request.path.startswith("/api/"):
        return api_error(message, 413)
    return render_template("error.html", message=message), 413


# ---------------------------------------------------------------- API
@app.route("/api/meta")
def api_meta():
    """Everything the page needs before the first calculation: controls, dictionary, sample CVs."""
    g = get_data()
    data, summary = g.data, g.summary
    role_name = data["roles"].set_index("role_id")["role_name"]
    return api({
        "cutoff_options": g.cutoff_options, "latest": g.latest, "source_note": g.SOURCE_NOTE,
        "skills": [{"id": s, "name": n} for s, n in sorted(g.SKILL_NAME.items(), key=lambda kv: kv[1])],
        "sdg_goals": [{"goal": r.goal, "name": r.goal_name, "colour": r.colour_hex} for r in data["sdg_goals"].itertuples()],
        "sdg_default": DEFAULT_SDG, "sdg_weight_default": DEFAULT_SDG_WEIGHT, "sdg_weight_max": MAX_SDG_WEIGHT,
        "sample_cvs": [{"id": n, "label": persona_label(n, t), "text": t} for n, t in data["cvs"].items()],
        "team_sample": [{"name": persona_label(n, t), "skills": list(core.extract_skills(t, g.SKILL_RE))}
                        for n, t in data["cvs"].items() if not n.startswith("cv07b")],
        "team_roles": [{"id": r, "name": role_name[r]} for r in g.team_roles],
        "privacy_note": ("Your CV is processed in memory and not stored. Name, gender, age and similar details are "
                         "removed before matching and are never used in any score. Skills are recognised from a fixed "
                         f"dictionary of {len(g.SKILL_NAME)} skills, so nothing is invented."),
        "current_caption": ("The closest current role to your CV. Admin, finance, payroll and contact centre roles are "
                            "among the occupations most exposed to generative AI. " + ILO_NOTE),
        "move_caption": (f"Realistic roles rated {joined(summary.get('allowed_target_exposure', ['Gradient 2 or lower']))} "
                         f"by the ILO, with at least {core.MIN_POSTS} job posts and enough overlap with admin and finance "
                         "skills. Sorted by skills match plus your SDG priorities. Weigh closeness against exposure: "
                         "the closest role is not always the safest."),
    })


@app.route("/api/extract", methods=["POST"])
def api_extract():
    """Skills found in one CV. Personal details and the INTERESTS section are ignored (core.extract_skills)."""
    g = get_data()
    up = request.files.get("cv_file")
    if up is not None and up.filename:
        if not up.filename.lower().endswith((".txt", ".pdf")):
            return api_error(f"{up.filename}: only .txt and .pdf files are accepted.")
        try:
            text, source = core.read_upload(up.filename, up.read()), up.filename
        except Exception as err:   # broken or encrypted PDF, pypdf missing
            return api_error(f"Could not read {up.filename}: {err}")
    else:
        body = _body()
        text = str(body.get("text") or request.form.get("text") or "").replace("\r\n", "\n")
        source = str(body.get("source") or "pasted text")
    found = core.extract_skills(text, g.SKILL_RE)
    return api({"source": source, "label": persona_label(source, text),
                "skills": [{"id": s, "name": g.SKILL_NAME[s], "evidence": e}
                           for s, e in sorted(found.items(), key=lambda kv: g.SKILL_NAME[kv[0]])]})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Everything that depends on the person's skills: profile trends, role options and the pathway."""
    g, body = get_data(), _body()
    cutoff = _cutoff(g, body.get("cutoff"))
    trends, radar = _radar(g, cutoff)
    skill_set = _skill_set(g, body.get("skills"))
    sdg_pref = _sdg_pref(g, body.get("sdg", DEFAULT_SDG))
    sdg_weight = round(min(max(as_float(body.get("sdg_weight"), DEFAULT_SDG_WEIGHT), 0.0), MAX_SDG_WEIGHT), 2)
    out = {"cutoff": cutoff, "sdg": sdg_pref, "sdg_weight": sdg_weight,
           "profile": [{"id": s, "name": g.SKILL_NAME[s], "evidence": e, "trend": trends.loc[s, "trend"]}
                       for s, e in sorted(skill_set.items(), key=lambda kv: g.SKILL_NAME[kv[0]])],
           "current": None, "upgrades": [], "moves": [], "others": [], "pathway": None}
    if not skill_set:
        return api(out)
    rec, current = rank_roles(radar, skill_set, sdg_pref, sdg_weight)
    ctx = SimpleNamespace(g=g, radar=radar, trends=trends, skill_set=skill_set, current=current, sdg_pref=sdg_pref)

    def by_score(group):
        return rec[rec["group"] == group].sort_values("final_score", ascending=False).itertuples()

    out.update(
        current=role_json(current, ctx, show_sdg=False),
        upgrades=[role_json(r, ctx) for r in by_score("upgrade")],
        moves=[role_json(r, ctx) for r in by_score("move")],
        others=[{"role": r.role, "match": pct_range(r.match_low, r.match_high), "ilo_gradient": r.ilo_gradient,
                 "transferability": pct(r.transferability), "posts": r.posts, "why": r.not_recommended_because}
                for r in rec[rec["group"] == "other"].itertuples()],
        pathway=pathway_json(ctx, rec, body.get("path_role")))
    return api(out)


@app.route("/api/radar")
def api_radar():
    """AI Adoption Index with its moderate and fast scenarios, and the rising and declining skills."""
    g = get_data()
    data = g.data
    cutoff = _cutoff(g, request.args.get("cutoff"))
    trends = core.trends_for(data, cutoff)
    model = trends["model"].iloc[0]
    ai = data["ai_monthly"].loc[: pd.Period(cutoff, "M"), "ai_index"]
    paths, _, ai_now = core.ai_scenarios(ai.values)
    obs = ai.rolling(3, min_periods=1).mean()
    future = pd.period_range(ai.index.max() + 1, periods=core.FORECAST_MONTHS, freq="M")

    def listing(label):
        t = trends[trends["trend"] == label].sort_values("change_pp_moderate", ascending=(label == "declining"))
        return [{"id": s, "name": g.SKILL_NAME.get(s, s), "now": pct(r["share_now"]),
                 "future": pct_range(r["forecast_moderate"], r["forecast_fast"])} for s, r in t.iterrows()]

    counts = trends["trend"].value_counts()
    return api({
        "cutoff": cutoff, "model": model,
        "metrics": {"now": pct(ai_now, 1), "moderate": pct(paths["moderate"][-1], 1), "fast": pct(paths["fast"][-1], 1)},
        "ai": {"months": [str(m) for m in obs.index], "observed": obs.values,
               "future_months": [str(m) for m in future], "moderate": paths["moderate"], "fast": paths["fast"]},
        "source_caption": g.SOURCE_NOTE + " The index is computed from the job posts themselves, so it updates with every new month.",
        "rising": listing("rising"), "declining": listing("declining"),
        "trend_caption": (f"{counts.get('stable', 0)} skills stable, {counts.get('limited data', 0)} with limited data "
                          f"(fewer than {core.MIN_MENTIONS} mentions). 'Now' is the share of job posts mentioning the skill; "
                          "'In 12 months' shows the moderate to fast AI scenario. "
                          f"Forecast model: {model}, chosen by a backtest of five models (see About). "
                          "A skill is called rising or declining only when its forecast change is at least 10% and 0.2 points."),
        "default_skill": default_skill(trends, g.skills_df),
    })


@app.route("/api/skill")
def api_skill():
    """One skill: its monthly share of job posts (3 month average) and where the two AI scenarios take it."""
    g = get_data()
    data = g.data
    cutoff = _cutoff(g, request.args.get("cutoff"))
    trends = core.trends_for(data, cutoff)
    skill = request.args.get("skill")
    if skill not in trends.index or skill not in data["monthly"].columns:
        skill = default_skill(trends, g.skills_df)
    y = data["monthly"].loc[: pd.Period(cutoff, "M"), skill].rolling(3, min_periods=1).mean()
    t = trends.loc[skill]
    name = g.SKILL_NAME[skill]
    return api({
        "skill": skill, "name": name, "trend": t["trend"], "cutoff": cutoff,
        "months": [str(m) for m in y.index], "observed": y.values,
        "forecast_months": [cutoff, str(pd.Period(cutoff, "M") + core.FORECAST_MONTHS)],
        "moderate": [t["share_now"], t["forecast_moderate"]], "fast": [t["share_now"], t["forecast_fast"]],
        "title": f"{name}: share of job posts mentioning it ({t['trend']})",
        "caption": (f"{int(t['mentions']):,} mentions up to {cutoff}. The dashed and dotted lines join today's level "
                    f"(last 3 months) to the {core.FORECAST_MONTHS} month estimate of the {t['model']} model."),
    })


@app.route("/api/team", methods=["POST"])
def api_team():
    """Which of a role's top skills each team member has, and how many people miss each one."""
    g, body = get_data(), _body()
    cutoff = _cutoff(g, body.get("cutoff"))
    trends, radar = _radar(g, cutoff)
    role = body.get("role")
    role = role if isinstance(role, str) and role in g.team_roles else g.team_roles[0]
    members = body.get("members")
    team = {}
    for m in members if isinstance(members, list) else []:
        if not isinstance(m, dict):
            continue
        name = str(m.get("name") or f"Person {len(team) + 1}")[:80]
        if name in team:          # two people with the same first name and role
            name = f"{name} ({len(team) + 1})"
        skills = m.get("skills") if isinstance(m.get("skills"), (list, dict)) else []
        team[name] = {s for s in skills if isinstance(s, str) and s in g.SKILL_IDS}
    imp = radar.importance(role).head(12)
    grid = [[int(s in sk) for s in imp.index] for sk in team.values()]
    missing = pd.Series([sum(1 - row[j] for row in grid) for j in range(len(imp))], index=imp.index)
    missing = missing.sort_values(ascending=False, kind="stable")
    return api({
        "cutoff": cutoff, "role": role, "role_name": radar.role_name[role], "team_size": len(team),
        "posts": radar.summary.loc[role, "posts"],
        "title": f"Team readiness for {radar.role_name[role]} (blue = has the skill)",
        "skills": [g.SKILL_NAME[s] for s in imp.index], "people": list(team), "grid": grid,
        "missing": [{"skill": g.SKILL_NAME[s], "missing": n, "trend": trends.loc[s, "trend"]} for s, n in missing.items()],
    })


@app.route("/api/about")
def api_about():
    """Method, forecasting backtest, fairness check, recommendation rule per role and data sources."""
    g = get_data()
    data, summary = g.data, g.summary
    cutoff = _cutoff(g, request.args.get("cutoff"))
    trends, radar = _radar(g, cutoff)
    model_used = trends["model"].iloc[0]
    chosen = summary.get("chosen_model", model_used)
    how = md(
        "1. **Track AI advancement.** Every monthly Hacker News 'Who is hiring?' thread since January 2020 is downloaded "
        "from the public API. The AI Adoption Index is the share of job posts that mention generative AI.\n"
        f"2. **Predict rising and declining skills.** Five forecasting models were tested on the same backtest; the app uses "
        f"**{chosen}**. Two scenarios: AI adoption at its recent pace (moderate) or twice as fast (fast).\n"
        "3. **Choose realistic, less exposed roles.** Starting roles are rated Gradient 3 or 4 by the ILO. Move roles must be "
        f"rated {joined(summary.get('allowed_target_exposure', ['Gradient 2 or lower']))}, have at least {core.MIN_POSTS} job posts "
        "and share enough skills with admin and finance work.\n"
        "4. **Match people to roles.** Role profiles come from the job posts for each role (Hacker News and LinkedIn). "
        "The match weights each skill by how often the role asks for it and by its forecast.\n"
        "5. **Plan the reskilling.** Gaps become an ordered plan using only checked courses, with extra options per skill.\n"
        "6. **Link to the SDGs.** Roles and skills are tagged to SDG targets; your SDG priorities can change the ranking, "
        "and the original match is always shown.")

    exp = data["experiment"]
    h_main = int(exp["horizon_months"].max())
    e12 = exp[exp["horizon_months"] == h_main].sort_values("mae_pp")

    lines = [f"* **Time machine:** {summary.get('time_machine_changed_labels', 'n/a')} skills changed label when only "
             "older data is used, which shows the signal responds to new data."]
    mr = summary.get("manual_review")
    if mr:
        lines.append(f"* **Skill detection, checked by hand on {mr['posts_reviewed']} posts:** precision {mr['precision']:.0%}, "
                     f"recall {mr['recall']:.0%}.")

    fairness = None
    a, b = data["cvs"].get("cv07a_twin.txt"), data["cvs"].get("cv07b_twin.txt")
    if a and b:
        cols = ["role_id", "match_moderate", "match_fast"]
        ok = radar.recommend(core.extract_skills(a, g.SKILL_RE))[cols].equals(
            radar.recommend(core.extract_skills(b, g.SKILL_RE))[cols])
        fairness = {"ok": ok, "text": ("Fairness check: two CVs identical except name, gender and age (female, 52 and "
                                       f"male, 29) get {'identical' if ok else 'different'} recommendations.")}

    rs = data["role_summary"]
    return api({
        "cutoff": cutoff, "how": str(how),
        "model": {"horizon": h_main, "chosen": chosen, "models": e12["model"], "mae": e12["mae_pp"]},
        "model_reason": str(md(summary.get("model_reason", ""))),
        "fairness": fairness, "checks": str(md("\n".join(lines))),
        "roles": [{"role": r.role, "type": r.type, "isco": r.isco_code, "ilo_gradient": r.ilo_gradient,
                   "ilo_score": f"{r.ilo_score:.2f}", "posts": r.posts, "transferability": pct(r.transferability),
                   "recommended": r.recommended, "why": r.not_recommended_because} for r in rs.itertuples()],
        "roles_caption": ILO_NOTE + " Job titles are mapped to ISCO 08 codes by the team.",
        "sources": data["sources"][["name", "publisher", "url", "type", "used_for"]].to_dict("records"),
        "sources_caption": (f"Hacker News retrieved {g.retrieved}. LinkedIn postings listed "
                            f"{summary.get('linkedin_listed', 'n/a')} (used for role profiles only, not for trends)."),
        "disclosure": str(md(
            "* Code, the skill dictionary, role patterns, the course search and SDG links were drafted with **Claude (Anthropic)** "
            "and reviewed by the team. The app itself uses **no language model**: every recommendation comes from the data "
            "files and cites its source.\n"
            "* Hacker News leans towards technology companies in the United States, so it shows global demand, not Malaysia. "
            "Many non tech skills are rarely mentioned there and show as limited data; LinkedIn fills in the role profiles.\n"
            "* AI sensitivity is an association, not proof of cause. ILO exposure measures exposure to GenAI, not job loss.\n"
            "* The tool supports human career decisions. It does not make hiring decisions.")),
    })


if __name__ == "__main__":
    # Replit (and most hosts) pass the port in PORT and need the app reachable from outside the container;
    # on a laptop it stays private on 127.0.0.1:5000.
    hosted = "PORT" in os.environ or "REPL_ID" in os.environ
    app.run(host="0.0.0.0" if hosted else "127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
