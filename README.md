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
| Replit Project    | https://replit.com/@your-username/your-project |
| Live Demo         | https://your-project.replit.app                |
| RunPod Endpoint   | https://api.runpod.ai/v2/your-endpoint-id      |
| Slide Deck        | https://example.com/slides                     |
| Demo Video        | https://example.com/demo-video                 |

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
| Frontend      | HTML,CSS,Java Script         |
| Backend       | Python, Flask         |
| Database      | e.g. PostgreSQL, SQLite      |
| AI / Compute  | RunPod (GPU)                 |
| Hosting / Dev | Replit                       |

---

## Project Structure

```
.
├── docs/                    # Screenshots, diagrams
├── runpod/
│   └── handler.py           # RunPod serverless handler (GPU workload)
├── src/
│   ├── main.py              # Application entry point
│   └── utils.py             # Helper functions
├── submission/              # Required submission documents
│   ├── REPLIT PROOF OF USE.pdf
│   ├── RUNPOD PROOF OF USE.pdf
│   └── Submission Template SDC Hackathon.pdf
├── tests/
│   └── test_utils.py        # Unit tests
├── .env.example             # Example environment variables
├── .gitignore
├── .replit                  # Replit run configuration
├── LICENSE
├── requirements.txt         # Python dependencies
└── README.md
```

### Architecture

```
User ──► Replit (App / API) ──► RunPod Endpoint (GPU model)
                │
                └──► Response returned to user
```

---

## How to Run

### Option 1 — Run on Replit (Recommended)

1. Open the [Replit Project](https://replit.com/@your-username/your-project), or import this repository via **Create Repl → Import from GitHub**.
2. Open the **Secrets** tab (🔒) and add the variables listed in `.env.example`:
   - `RUNPOD_API_KEY`
   - `RUNPOD_ENDPOINT_ID`
3. Click **Run**. Replit uses the `.replit` file to start `python src/main.py`.

### Option 2 — Run Locally

```bash
# 1. Clone the repository
git clone https://github.com/your-username/your-project.git
cd your-project

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env            # then fill in your values

# 5. Run the app
python src/main.py
```

### Run Tests

```bash
python -m unittest discover tests
```

---

## How We Use Replit *(Required)*

Describe how your team used Replit. For example:

- **Development:** Collaborative coding in a shared Repl using Multiplayer.
- **Hosting:** The app is deployed with Replit Deployments at the Live Demo link above.
- **Secrets:** API keys are stored in Replit Secrets, never in the code.

📄 Proof of use: [`submission/REPLIT PROOF OF USE.pdf`](submission/REPLIT%20PROOF%20OF%20USE.pdf)

## How We Use RunPod *(Required)*

Describe how your team used RunPod. For example:

- **Workload:** Model inference (e.g. text generation, image processing) runs on a RunPod GPU.
- **Setup:** `runpod/handler.py` is deployed as a **RunPod Serverless Endpoint**.
- **Integration:** The Replit app sends requests to the endpoint using `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID`.

Example request:

```bash
curl -X POST https://api.runpod.ai/v2/$RUNPOD_ENDPOINT_ID/runsync \
  -H "Authorization: Bearer $RUNPOD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"prompt": "Hello"}}'
```

📄 Proof of use: [`submission/RUNPOD PROOF OF USE.pdf`](submission/RUNPOD%20PROOF%20OF%20USE.pdf)

---

## Challenges & Learnings

- What challenges did you face, and how did you overcome them?
1. Finding reliable data on future skills
2. Building and deploying within a short hackathon timeline
- What did your team learn?
1. Teamwork and time management

## Future Improvements

- [ ] Improvement 1
- [ ] Improvement 2

## Team

| Name        | Role                | GitHub                                   |
| ----------- | ------------------- | ---------------------------------------- |
| Louis Benedict Oen  | Team Lead / Backend | [@username](https://github.com/username) |
| William Putra Widhianto | Frontend        | [@username](https://github.com/username) |
| Stephanie Linggawan | AI / RunPod         | [@username](https://github.com/username) |
| Christian Valentino Linardi | AI / RunPod | [@username](https://github.com/username) |
| Gwen Tiffany Aloei | AI / RunPod          | [@username](https://github.com/username) |

---

## Submission Checklist

- [ ] Team name, domain (Domain 1 / Domain 2) and SDG track filled in
- [ ] Slide deck link added
- [ ] Demo video link added
- [ ] Replit used, with proof of use in `submission/`
- [ ] RunPod used, with proof of use in `submission/`
- [ ] Submission template completed in `submission/`
- [ ] "How to Run" steps verified
- [ ] No API keys or secrets committed to the repository

## License

This project is licensed under the [Apache License 2.0](LICENSE).
