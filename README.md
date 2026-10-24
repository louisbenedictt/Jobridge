# JOBRIDGE      

> A web application designed for a hackathon competition, featuring tasks automated by artificial intelligence (AI). The application analyzes users' CVs to identify which of their skills are seeing an increase or decrease in demand as AI evolves. Furthermore, it recommends realistic job roles that are endure to the impact of AI. Each recommendation includes an explainable match score, an assessment of changes in the level of exposure to AI, a skills gap analysis, and a step-by-step learning plan curated from verified, real-world courses. Every role and skill is linked to the UN Sustainable Development Goals (SDGs). All data points include their sources and dates, with projections presented across two distinct AI scenarios are ultimately leaving the final decision in the hands of the user.

## Team Information

| Field                  | Details                                     |
| ---------------------- | ------------------------------------------- |
| **Team Name**          | JONG JAVA                                   |
| **Team Domain**        | Domain 1                                    |
| **SDG Track (1–17)**   | SDG 4 — Quality Education                  
                           SDG 5 - Gender Equality    
                           SDG 8 - Decent Work and Economic Growth     |
| **Team Leader**        | Louis Benedict Oen                          |
| **University**         | Xiamen University Malaysia                  |
| **Number of Members**  | 5                                           |

## Links

| Resource          | Link                                           |
| ----------------- | ---------------------------------------------- |
| GitHub Repository | https://github.com/louisbenedictt/Jobridge     |
| Replit Project    | https://replit.com/@gwentiffany37/Jobridge     |
| Live Demo         | https://jobridge.replit.app/                   |
| RunPod Endpoint   | -                                              |
| Slide Deck        | https://drive.google.com/file/d/1S4XaumOntapxHaOque2b1lyZSIe7g1MQ/view?usp=sharingslides                     |
| Demo Video        | https://youtu.be/7c0RkoZdOZodemo-video                 |

---

## Overview

### Problem

Currently, artificial intelligence (AI) is rapidly eliminating administrative jobs, leaving both recent graduates and experienced workers with increasingly obsolete skill sets. The core problem is that these workers do not know how to safely transition to new careers, while, conversely, companies are struggling to find talent that is "ready to hit the ground running." If this gap is not addressed promptly, we will face mass unemployment, deepening social inequality, and a shortage of the workforce essential for the transition toward a green economy.

### Solution

How our project uses AI to solve the problem :

Understanding the user’s current skills. The user enters [their skills / background / target role]. The system [uses AI to analyze and structure this input].
Identifying future skill demand. AI [analyzes job market data / role requirements / industry trends] to find which skills are growing in importance.
Showing the gap and a path forward. The results are shown on an interactive radar chart that compares the user’s current skills with the skills needed for their target career. AI then [recommends specific skills and learning steps] to close the gap.

What makes it valuable :

Personalized. Advice is based on each user’s own profile, not generic career tips.
Easy to understand. The radar chart shows strengths and gaps at a glance, without reading long reports.
Actionable. Users get clear next steps, not just a score.
Future-focused. It prepares people for the skills of tomorrow, which supports the Future-Ready Workforce goal.
Scalable and accessible. As a web app, it can serve many students and workers at low cost.

### Key Features

- **Dynamic Skills and Jobs Trend** — Tracks changes in job markets and skills, so users can see which jobs and skills are becoming more or less in demand.
- **ILO Research-Based AI Jobs replacement Risk** — Uses ILO research to estimate how likely a job is to be affected by AI, helping users better understand their future career risks.
- **Personalized Reskilling Pathways** — Recommends skills users need to improve and provides learning resources to help them prepare for their target jobs.

### Tech Stack

| Layer         | Technology                   |
| ------------- | ---------------------------- |
| Frontend      | HTML,CSS Tailwind,Java Script|
| Backend       | Python, Flask                |
| Database      | -                            |
| AI / Compute  | - (runpod is not required)   |
| Hosting / Dev | Replit                       |

---

## Project Structure

```
Jobridge
├── data/
│   ├── cvs/
│   │   ├── _version.txt
│   │   ├── cv01_accounts_executive.txt
│   │   ├── cv02_admin_executive.txt
│   │   ├── cv03_finance_executive.txt
│   │   ├── cv04_fresh_graduate.txt
│   │   ├── cv05_customer_ops.txt
│   │   ├── cv06_payroll_admin.txt
│   │   ├── cv07a_twin.txt
│   │   └── cv07b_twin.txt
│   ├── processed/
│   │   ├── ai_index_monthly.csv
│   │   ├── model_experiment.csv
│   │   ├── recommendations_sample_cvs.csv
│   │   ├── role_post_counts.csv
│   │   ├── role_profiles.csv
│   │   ├── role_summary.csv
│   │   ├── sdg_map.csv
│   │   ├── skill_share_monthly.csv
│   │   ├── skill_trends_by_cutoff.csv.gz
│   │   ├── skill_trends.csv
│   │   ├── summary.json
│   │   └── time_machine.csv
│   └── reference/
│       ├── _version.txt
│       ├── ai_terms.csv
│       ├── courses.csv
│       ├── ilo_exposure.csv
│       ├── roles.csv
│       ├── sdg_goals.csv
│       ├── sdg_links.csv
│       ├── sdg_targets.csv
│       ├── skills.csv
│       └── sources.csv
├── static/
│   └── jobbridge.js
├── submission/
│   └── REPLIT PROOF OF USE.pdf
├── templates/
│   ├── error.html
│   └── jobbridge.html
├── tests/
├── .gitignore
├── .replit
├── core.py
├── flask_app.py
├── Jobbridge_pipeline.ipynb
├── LICENSE
├── postings.csv
├── README.md
└── requirements.txt

### Architecture

```
User (Browser)
      │
      ├── (HTTP Request: GET / POST)
      ▼
┌─────────────────────────────────────────────────────────────┐
│ Replit Hosting Environment                                  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Flask App (flask_app.py)                              │  │
│  │   ├── Routing & Controller                            │  │
│  │   └── Template Rendering (templates/jobbridge.html)   │  │
│  └──────────────┬────────────────────────────────────────┘  │
│                 │                                           │
│                 ▼                                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Core Logic & Pipeline (core.py / Jobbridge_pipeline)  │  │
│  │   ├── Data Processing & CV Parsing                    │  │
│  │   ├── Explainable Matching & Scoring                  │  │
│  │   └── SDG & Reskilling Pathway Logic                  │  │
│  └──────────────┬────────────────────────────────────────┘  │
│                 │                                           │
│                 ▼                                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Data Storage (Local CSV / JSON Files)                 │  │
│  │   ├── data/cvs/ (Sample CVs)                          │  │
│  │   ├── data/processed/ (AI Index, Role Profiles, dll)  │  │
│  │   ├── data/reference/ (Courses, Skills, SDG, dll)     │  │
│  │   └── postings.csv & static/ (JS / Assets)            │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
      │
      └──► Response (HTML UI + JavaScript Interactivity) returned to User
```

## How We Use Replit *(Required)*

- **Development:** Replit help us to brainstorm and build our ideas.
- **Hosting:** The app is deployed with Replit Deployments.

📄 Proof of use: (https://github.com/louisbenedictt/Jobridge/blob/main/submission/REPLIT%20PROOF%20OF%20USE.pdf)


## Challenges & Learnings

- What challenges did you face, and how did you overcome them?
1. Finding reliable data on future skills
2. Building and deploying within a short hackathon timeline
- What did your team learn?
1. Teamwork and time management

## Future Improvements

- [☑️] More advanced and creative features
- [☑️] Use more efficient and simple codes

## Team

| Name        | Role                | GitHub                                   |
| ----------- | ------------------- | ---------------------------------------- |
| Louis Benedict Oen  | Team Lead / Backend / Data Pipeline | [@louisbenedictt](https://github.com/louisbenedictt) |
| William Putra Widhianto | Data Integration | [@LiaamZ](https://github.com/LiaamZ) |
| Stephanie Linggawan | AI / ML Forecasing and Trends | [@Stephanie-Linggawan](https://github.com/Stephanie-Linggawan) |
| Christian Valentino Linardi | AI /Recommendation Engine| [@ChristianValentino-gg](https://github.com/ChristianValentino-gg) |
| Gwen Tiffany Aloei | Frontend Developer | [@gwentiffanyy](https://github.com/gwentiffanyy) |

---

## Submission Checklist

- [☑️] Team name, domain (Domain 1) and SDG track filled in
- [☑️] Slide deck link added
- [☑️] Demo video link added
- [☑️] Replit used, with proof of use in `submission/`
- [☑️] RunPod used, with proof of use in `submission/`
- [☑️] Submission template completed in `submission/`
- [☑️] "How to Run" steps verified
- [☑️] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).
