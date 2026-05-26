# Smart Classroom Automation System (Akıllı Sınıf Otomasyon Sistemi)

This project is a **Smart Classroom Automation and Energy Management System**. It provides a complete simulation, monitoring, and optimization environment for managing classroom conditions such as energy consumption, temperature, light levels, and CO₂ concentration.

Unlike simple binary occupancy systems, the physical model scales all environmental calculations directly with the **exact headcount** in each classroom — 5 students produce a fundamentally different thermal and air-quality profile than 40 students.

---

## 🚀 Features

- **Real-Time Dashboard**: Visualizes live data (energy usage, temperature, lux, CO₂, occupancy, headcount) from B-201, B-202, and B-203 using time-series charts.
- **Digital Twin**: A secondary interface (`digital_twin.html`) for monitoring a real-time digital representation of the classroom environment.
- **Physics-Based Headcount Simulation**: `eem_simulator.py` generates sensor data where CO₂ accumulation, metabolic heat load, and HVAC power consumption are all scaled by the actual number of students per session (not just a binary occupied/empty flag).
- **Optimization via GRA**: `end_gra.py` runs a Taguchi L9 / Grey Relational Analysis to find the best parameter scenario (lighting threshold, AC setpoint, CO₂ ventilation limit) that balances energy efficiency with student comfort.
- **Automated Startup**: `run.py` orchestrates the entire stack — resets the database, starts the backend, serves the frontend, runs the simulator, then runs the GRA — in a single command.

---

## 🧠 Physical Model (v2 — Dynamic Headcount)

The simulator models three classrooms, each with a weekly schedule that now includes the number of students per session:

| Classroom | Sessions (start–end, students) |
|-----------|-------------------------------|
| B-201     | 08–10 (40), 11–13 (35), 14–16 (38) |
| B-202     | 09–11 (20), 13–15 (15) |
| B-203     | 08–09 (5), 10–12 (12), 15–17 (8) |

### CO₂ Accumulation
```
co2_rate  = num_students × 0.35  ppm/min
co2(t)    = 400 + co2_rate × min(t_into_session, 90)
```
A full class of 40 produces **14 ppm/min** and reaches ~1,660 ppm after 90 minutes.  
A seminar of 5 produces **1.75 ppm/min** and peaks at ~557 ppm — safely below the 1,000 ppm threshold.

### Metabolic Heat Load
```
Q_people = num_students × 80 W
```
40 students inject **3,200 W** of body heat into the room.

### HVAC Power Consumption
```
P_ac = min(2000, 300 + 50 × |T_outdoor − 22| + 5 × num_students)
```
The AC must draw significantly more power in a packed room than an empty one, even at the same outdoor temperature.

### Indoor Temperature
```
net_heat  = Q_people − (P_ac − P_ac_base)
T_indoor  = 22 + max(0, net_heat) × R_thermal
```
If the HVAC is undersized for the heat load, `T_indoor` rises above 22 °C proportionally.

### Payload Fields (new in v2)
The simulator now sends two additional fields to the API:

| Field | Location | Description |
|-------|----------|-------------|
| `num_students` | `sensor_data` | Exact headcount during the session (0 when empty) |
| `metabolic_load_w` | `device_status.ac` | Total body-heat load `Q_people` in watts |

---

## 🛠️ Technology Stack

### Backend
- **Python 3.8+** — core language.
- **FastAPI** — high-performance async REST API framework.
- **Uvicorn** — ASGI server for FastAPI.
- **Pydantic** — request/response validation and schema enforcement.
- **SQLite + aiosqlite** — lightweight async database for sensor logs, scenarios, and GRA results (`classroom.db`).

### Frontend
- **HTML5 / CSS3** — layout and vanilla CSS styling (no heavy frameworks).
- **JavaScript** — vanilla JS for API polling, chart updates, and DOM manipulation.
- **Chart.js** — dynamic time-series charts for sensor data.
- **Python `http.server`** — static file server for the frontend.

---

## 📁 Project Structure

```text
smart_classroom/
├── backend/
│   ├── app/                # FastAPI application (routers, models, DB layer)
│   ├── classroom.db        # SQLite database (auto-generated on each run)
│   ├── eem_simulator.py    # Physics-based sensor data simulator (v2: headcount model)
│   ├── end_gra.py          # Taguchi L9 / Grey Relational Analysis optimizer
│   ├── main.py             # FastAPI entry point
│   ├── run.py              # Single-command orchestrator for the full stack
│   ├── schema.json         # Reference payload schema
│   └── requirements.txt    # Python dependencies
└── frontend/
    ├── app.js              # Frontend logic and API integration
    ├── digital_twin.html   # Digital twin monitoring interface
    ├── index.html          # Main real-time dashboard
    └── style.css           # UI styling
```

---

## ⚙️ How to Run

1. Ensure **Python 3.8+** is installed.
2. Install dependencies from the `backend` directory:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
3. Launch the entire system with a single command:
   ```bash
   python run.py
   ```

`run.py` will automatically:
- Delete and recreate `classroom.db` (fresh run).
- Start the FastAPI backend on port **8000**.
- Serve the frontend on port **3000**.
- Run `eem_simulator.py` (37 time-steps × 15 min, 3 classrooms simultaneously).
- Open the dashboard in your default browser once the first data arrives.
- Run `end_gra.py` (Taguchi L9 GRA analysis) after the simulation completes.

---

## 🔗 Endpoints & URLs

| Interface | URL |
|-----------|-----|
| Main Dashboard | `http://127.0.0.1:3000/index.html` |
| Digital Twin | `http://127.0.0.1:3000/digital_twin.html` |
| API (Swagger docs) | `http://localhost:8000/docs` |
| Latest data (example) | `http://localhost:8000/api/data/latest?classroom_id=B-201` |
| History (example) | `http://localhost:8000/api/data/history?classroom_id=B-201&limit=37` |
