"""Checks that the Flask app and its JSON API run end to end on the data in data/.

Run from the project folder:  python -m unittest discover tests -v
Run the data pipeline (Jobridge_pipeline.ipynb) first; these tests read its output.
"""

import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core          # noqa: E402
import flask_app     # noqa: E402

LEAKED_EMPTY = {"nan", "NaN", "None", "null", "undefined"}


def strict_json(text):
    """JSON the way the browser reads it: JSON.parse rejects NaN and Infinity."""
    def bad(token):
        raise ValueError(f"{token} is not valid JSON")
    return json.loads(text, parse_constant=bad)


def strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from strings(v)
    elif isinstance(obj, str):
        yield obj


class FlaskAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        flask_app.app.testing = True
        cls.client = flask_app.app.test_client()
        cls.state = flask_app.get_data()
        cls.data = cls.state.data
        cls.latest = cls.state.latest

    # ------------------------------------------------------------ helpers
    def call(self, url, payload=None, files=None, status=200):
        """GET (no payload), POST JSON (payload) or POST a form with files; returns the checked JSON answer."""
        if files is not None:
            resp = self.client.post(url, data=files, content_type="multipart/form-data")
        elif payload is not None:
            resp = self.client.post(url, json=payload)
        else:
            resp = self.client.get(url)
        body = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, status, body[:500])
        out = strict_json(body)
        leaked = [s for s in strings(out) if s.strip() in LEAKED_EMPTY]
        self.assertEqual(leaked, [], "an empty value (nan/None) would be shown on the page")
        return out

    def skills_of(self, cv_name):
        found = core.extract_skills(self.data["cvs"][cv_name], self.state.SKILL_RE)
        return found, dict(found)

    def analyze(self, skills, **extra):
        return self.call("/api/analyze", {"cutoff": self.latest, "skills": skills, "sdg": [8, 12, 13],
                                          "sdg_weight": 0.15, **extra})

    def radar(self, cutoff=None):
        cutoff = cutoff or self.latest
        trends = core.trends_for(self.data, cutoff)
        return trends, core.Radar(self.data, trends)

    # ------------------------------------------------------------ page and static files
    def test_home_page(self):
        resp = self.client.get("/")
        body = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 200)
        for text in ["JOBRIDGE", "Your Profile", "Job-Match", "Course Pathway", "About Jobridge",
                     "/static/jobridge.js", "/plotly.min.js"]:
            self.assertIn(text, body)

    def test_static_files(self):
        for url in ["/plotly.min.js", "/static/jobridge.js"]:
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                resp.close()

    def test_page_uses_only_api_data(self):
        """The mock data of the first design (alo.html) must not come back."""
        js = (Path(flask_app.app.static_folder) / "jobridge.js").read_text(encoding="utf-8")
        for mock in ["SKILLS_DICT", "ROLES_DB", "COURSES_CATALOGUE", "SAMPLE_CVS", "baseShare"]:
            self.assertNotIn(mock, js)

    # ------------------------------------------------------------ meta and extract
    def test_meta(self):
        m = self.call("/api/meta")
        self.assertEqual(m["cutoff_options"], self.state.cutoff_options)
        self.assertEqual(m["latest"], self.latest)
        self.assertEqual(len(m["skills"]), len(self.data["skills"]))
        self.assertEqual(len(m["sdg_goals"]), len(self.data["sdg_goals"]))
        self.assertEqual([c["id"] for c in m["sample_cvs"]], list(self.data["cvs"]))
        self.assertNotIn("cv07b", " ".join(t["name"] for t in m["team_sample"]))
        origin = set(self.data["roles"].loc[self.data["roles"]["role_type"] == "origin", "role_id"])
        self.assertFalse(origin & {r["id"] for r in m["team_roles"]})

    def test_extract_text_matches_core(self):
        for name, text in self.data["cvs"].items():
            with self.subTest(cv=name):
                out = self.call("/api/extract", {"text": text.replace("\n", "\r\n"), "source": name})
                expected = core.extract_skills(text, self.state.SKILL_RE)
                self.assertEqual({s["id"]: s["evidence"] for s in out["skills"]}, expected)

    def test_extract_upload(self):
        cv = self.data["cvs"]["cv01_accounts_executive.txt"]
        out = self.call("/api/extract", files={"cv_file": (io.BytesIO(cv.encode()), "my_cv.txt")})
        self.assertEqual(out["source"], "my_cv.txt")
        self.assertTrue(out["label"].startswith("Nurul"))
        self.assertTrue(out["skills"])
        out = self.call("/api/extract", files={"cv_file": (io.BytesIO(b"x"), "cv.docx")}, status=400)
        self.assertIn("only .txt and .pdf", out["error"])
        out = self.call("/api/extract", files={"cv_file": (io.BytesIO(b"not a pdf"), "bad.pdf")}, status=400)
        self.assertIn("Could not read bad.pdf", out["error"])

    def test_extract_pdf(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig = plt.figure()
        fig.text(0.05, 0.5, "Skills: Microsoft Excel, bank reconciliation, payroll, SQL", fontsize=8)
        buf = io.BytesIO()
        fig.savefig(buf, format="pdf")
        plt.close(fig)
        buf.seek(0)
        out = self.call("/api/extract", files={"cv_file": (buf, "cv.pdf")})
        self.assertIn("payroll", {s["id"] for s in out["skills"]})

    def test_upload_too_large(self):
        saved = flask_app.app.config["MAX_CONTENT_LENGTH"]
        try:
            flask_app.app.config["MAX_CONTENT_LENGTH"] = 100
            out = self.call("/api/extract", files={"cv_file": (io.BytesIO(b"x" * 1000), "big.txt")}, status=413)
            self.assertIn("too large", out["error"])
        finally:
            flask_app.app.config["MAX_CONTENT_LENGTH"] = saved

    # ------------------------------------------------------------ analyze
    def test_every_sample_cv_matches_core(self):
        """Each role card shows exactly what core.py calculates, in the right group."""
        trends, radar = self.radar()
        allowed = set(self.state.summary["allowed_target_exposure"])
        for name in self.data["cvs"]:
            with self.subTest(cv=name):
                found, skills = self.skills_of(name)
                out = self.analyze(skills)
                rec = radar.recommend(found).set_index("role_id")
                self.assertEqual(out["current"]["group"], "now")
                self.assertEqual(rec.loc[out["current"]["role_id"], "type"], "origin")
                cards = [out["current"], *out["upgrades"], *out["moves"]]
                for card in cards:
                    row = rec.loc[card["role_id"]]
                    self.assertEqual(card["match"], flask_app.pct_range(row.match_low, row.match_high))
                    self.assertEqual(len(card["explain"]), len(radar.explain(card["role_id"], found)))
                for card in out["moves"]:
                    self.assertTrue(rec.loc[card["role_id"], "recommended"])
                    self.assertIn(card["ilo_gradient"], allowed)
                for card in out["upgrades"]:
                    self.assertEqual(rec.loc[card["role_id"], "type"], "upgrade")
                shown = {c["role_id"] for c in cards} | {o["role"] for o in out["others"]}
                self.assertEqual(len(shown), len(cards) + len(out["others"]))
                self.assertEqual([p["id"] for p in out["profile"]],
                                 sorted(found, key=lambda s: self.state.SKILL_NAME[s]))

    def test_every_pathway_role(self):
        found, skills = self.skills_of("cv03_finance_executive.txt")
        _, radar = self.radar()
        options = self.analyze(skills)["pathway"]["options"]
        self.assertTrue(options)
        for opt in options:
            with self.subTest(role=opt["id"]):
                p = self.analyze(skills, path_role=opt["id"])["pathway"]
                self.assertEqual(p["role_id"], opt["id"])
                self.assertEqual(p["match_now"], flask_app.pct_range(radar.match(opt["id"], found, "moderate"),
                                                                     radar.match(opt["id"], found, "fast")))
                plan, _, _ = radar.pathway(opt["id"], found)
                self.assertEqual([s["skill"] for s in p["steps"]], list(plan["skill"]))
                for s in p["steps"]:
                    if s["url"]:
                        self.assertTrue(s["course"] and s["provider"])

    def test_no_skills(self):
        out = self.analyze({})
        self.assertEqual(out["profile"], [])
        self.assertIsNone(out["current"])
        self.assertIsNone(out["pathway"])

    def test_sdg_weight_and_goals(self):
        _, skills = self.skills_of("cv01_accounts_executive.txt")
        out = self.analyze(skills, sdg_weight=0)
        for card in out["moves"]:
            self.assertEqual(card["sdg"]["ranking"], card["sdg"]["match"])
        out = self.analyze(skills, sdg=[])
        self.assertTrue(all(card["sdg"] is None for card in out["moves"] + out["upgrades"]))

    def test_bad_input_falls_back(self):
        out = self.call("/api/analyze", {"cutoff": ["2020-01"], "skills": {"not_a_skill": "x", "sql": None},
                                         "sdg": ["x", 99, None], "sdg_weight": "NaN", "path_role": ["data_analyst"]})
        self.assertEqual(out["cutoff"], self.latest)
        self.assertEqual(out["sdg"], [])
        self.assertEqual(out["sdg_weight"], flask_app.DEFAULT_SDG_WEIGHT)
        self.assertEqual([p["id"] for p in out["profile"]], ["sql"])
        self.call("/api/analyze", {"skills": "sql", "sdg_weight": 5})
        self.call("/api/radar?cutoff=abc")
        self.call("/api/skill?cutoff=abc&skill=abc")
        self.call("/api/team", {"members": 5, "role": {"x": 1}})
        self.call("/api/team", {"members": [{"name": "A", "skills": 5}, "B"]})
        resp = self.client.post("/api/analyze", data="not json", content_type="application/json")
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------ radar and skill
    def test_radar_every_cutoff(self):
        for cutoff in self.state.cutoff_options[::6] + [self.latest]:
            with self.subTest(cutoff=cutoff):
                out = self.call(f"/api/radar?cutoff={cutoff}")
                trends = core.trends_for(self.data, cutoff)
                self.assertEqual(out["ai"]["months"][-1], cutoff)
                self.assertEqual(len(out["ai"]["future_months"]), core.FORECAST_MONTHS)
                self.assertEqual(len(out["rising"]), int((trends["trend"] == "rising").sum()))
                self.assertEqual(len(out["declining"]), int((trends["trend"] == "declining").sum()))
                self.assertEqual(out["model"], trends["model"].iloc[0])
                skill = self.call(f"/api/skill?cutoff={cutoff}&skill={out['default_skill']}")
                self.assertEqual(skill["skill"], out["default_skill"])
                self.assertEqual(skill["months"][-1], cutoff)

    def test_skill_unknown_falls_back(self):
        out = self.call("/api/skill?skill=not_a_skill")
        self.assertEqual(out["skill"], self.call("/api/radar")["default_skill"])

    # ------------------------------------------------------------ team and about
    def test_team_every_role(self):
        meta = self.call("/api/meta")
        _, radar = self.radar()
        for role in meta["team_roles"]:
            with self.subTest(role=role["id"]):
                out = self.call("/api/team", {"cutoff": self.latest, "role": role["id"], "members": meta["team_sample"]})
                imp = radar.importance(role["id"]).head(12)
                self.assertEqual(out["skills"], [self.state.SKILL_NAME[s] for s in imp.index])
                self.assertEqual(out["posts"], radar.summary.loc[role["id"], "posts"])
                self.assertEqual(len(out["grid"]), len(meta["team_sample"]))
                for m in out["missing"]:
                    j = out["skills"].index(m["skill"])
                    self.assertEqual(m["missing"], sum(1 - row[j] for row in out["grid"]))

    def test_team_same_name(self):
        out = self.call("/api/team", {"members": [{"name": "Nurul", "skills": ["sql"]}, {"name": "Nurul", "skills": []}]})
        self.assertEqual(len(out["people"]), 2)

    def test_about(self):
        out = self.call("/api/about")
        self.assertTrue(out["fairness"]["ok"])
        self.assertIn(out["model"]["chosen"], out["model"]["models"])
        self.assertEqual(len(out["roles"]), len(self.data["role_summary"]))
        self.assertEqual(len(out["sources"]), len(self.data["sources"]))
        self.assertIn("<ol>", out["how"])

    # ------------------------------------------------------------ missing data
    def test_missing_data_message(self):
        saved_load, saved_cache = core.load_data, dict(flask_app._cache)

        def missing():
            raise FileNotFoundError(2, "No such file", "data/processed/summary.json")

        try:
            core.load_data = missing
            flask_app._cache.update(version=None, state=None)
            resp = self.client.get("/")
            self.assertEqual(resp.status_code, 500)
            self.assertIn("Run Jobridge_pipeline.ipynb first", resp.get_data(as_text=True))
            out = self.call("/api/meta", status=500)
            self.assertIn("Run Jobridge_pipeline.ipynb first", out["error"])
        finally:
            core.load_data = saved_load
            flask_app._cache.update(saved_cache)


if __name__ == "__main__":
    unittest.main()
