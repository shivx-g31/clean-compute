# CleanCompute
> **Same AI. Less carbon.**

CleanCompute is a carbon-aware AI workload scheduler built for the Sustainable AI track.

## The Problem
Conventional AI workload scheduling prioritizes raw compute performance and financial cost, completely ignoring the carbon intensity ($\text{gCO}_2/\text{kWh}$) and renewable energy availability of the electricity powering data centers. Grid carbon intensity fluctuates significantly—often by 3x to 5x—across different hours of the day and different geographical regions. Running an AI training or fine-tuning job during peak fossil-fuel hours in a coal-heavy region produces vastly more emissions than running the exact same workload powered by wind or solar in a cleaner grid.

## The Solution
CleanCompute allows users to submit AI workloads specifying:
- GPU type (e.g., NVIDIA H100, A100, L40S, V100, T4)
- GPU count
- Estimated runtime duration
- Completion deadline
- Workload flexibility & checkpointability

CleanCompute forecasts carbon intensity across **14 worldwide regions** and determines optimal execution schedules using three core optimization strategies:
1. **Time-Shifting**: Delaying execution until local renewable energy is at its peak.
2. **Geo-Shifting**: Dispatching jobs to regions with lower carbon intensity, factoring in network distance and data transfer carbon overhead.
3. **Pause-and-Resume**: Interleaving execution windows during optimal renewable spikes for checkpointable jobs.

Users can choose between three scheduling modes:
- **Greenest**: Maximizes carbon reduction regardless of wait time (within deadline).
- **Balanced**: Strikes a trade-off between carbon savings and job completion speed.
- **Fastest**: Prioritizes lowest turnaround time while selecting the greenest available slot right now.

---

## Project Structure
```text
C^2/
├── backend/                  # FastAPI + NumPy + Pydantic + MongoDB Atlas backend
│   ├── app/
│   │   ├── main.py           # FastAPI entrypoint
│   │   ├── core/             # Configuration and database client
│   │   ├── models/           # Pydantic schemas and database models
│   │   ├── services/         # Carbon forecasting & scheduling algorithms
│   │   └── api/              # API route definitions
│   ├── requirements.txt      # Python dependencies
│   └── .env.example
├── frontend/                 # React + Vite + Tailwind CSS + Lucide React + Recharts
│   ├── src/
│   │   ├── components/       # UI components & CleanCompute leaf-chip branding
│   │   ├── pages/            # View pages (Dashboard, Scheduler, Regions, Analytics)
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
├── .env.example              # Template environment variables
├── .gitignore                # Git exclusions (including .env)
└── README.md
```

---

## Getting Started

### Backend Setup
```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Unix:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

