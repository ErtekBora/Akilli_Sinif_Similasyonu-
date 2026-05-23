# Smart Classroom Automation System (Akıllı Sınıf Otomasyon Sistemi)

This project is a **Smart Classroom Automation and Energy Management System**. It provides a complete simulation, monitoring, and optimization environment for managing classroom conditions such as energy consumption, temperature, light levels, and CO₂ concentration.

## 🚀 Features
- **Real-Time Dashboard**: Visualizes live data (energy usage, temperature, lux, CO₂, occupancy) from multiple classrooms (e.g., B-201, B-202, B-203) using time-series charts.
- **Digital Twin**: Includes a secondary interface (`digital_twin.html`) for monitoring a digital representation of the classroom.
- **Sensor Simulation**: An automated simulator (`eem_simulator.py`) that generates mock sensor data simulating real-world classroom conditions.
- **Optimization via GRA**: Uses Taguchi / Grey Relational Analysis (GRA) via `end_gra.py` to calculate the best scenarios for balancing energy efficiency with student comfort (thermal, lighting, and air quality).
- **Automated Startup**: A single launcher script (`run.py`) coordinates the entire stack (Database, Backend, Frontend, Simulator, and Analyzer).

## 🛠️ Technology Stack

### Backend
- **Python**: Core programming language.
- **FastAPI**: High-performance asynchronous web framework for building the REST APIs.
- **Uvicorn**: ASGI web server implementation for FastAPI.
- **Pydantic**: Data validation and settings management.
- **SQLite & aiosqlite**: Lightweight, asynchronous database used to store sensor logs, scenarios, and optimization results (`classroom.db`).

### Frontend
- **HTML5 / CSS3**: For layout and custom styling (Vanilla CSS, no heavy frameworks).
- **JavaScript**: Vanilla JS for logic, WebSocket/API polling, and DOM manipulation.
- **Chart.js**: For rendering dynamic time-series charts of the sensor data.
- **Python `http.server`**: Used to serve the static frontend files.

## 📁 Project Structure
```text
smart_classroom/
├── backend/
│   ├── app/                # FastAPI application (routers, db, models)
│   ├── classroom.db        # SQLite database (auto-generated)
│   ├── eem_simulator.py    # Sensor data simulator
│   ├── end_gra.py          # GRA Optimization analyzer
│   ├── main.py             # FastAPI entry point
│   ├── run.py              # Main orchestrator script to run the whole app
│   └── requirements.txt    # Python dependencies
└── frontend/
    ├── app.js              # Frontend logic and API integration
    ├── digital_twin.html   # Digital twin interface
    ├── index.html          # Main monitoring dashboard
    └── style.css           # UI Styling
```

## ⚙️ How to Run

1. Ensure you have **Python 3.8+** installed.
2. Navigate to the `backend` directory and install the requirements:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
3. Start the entire system using the orchestration script:
   ```bash
   python run.py
   ```
4. The script will automatically start the Backend (`:8000`), Frontend (`:3000`), and Simulator. Your default browser will automatically open the Dashboard once the first simulated data is received.

## 🔗 Endpoints & URLs
- **Main Dashboard**: `http://127.0.0.1:3000/index.html`
- **Digital Twin**: `http://127.0.0.1:3000/digital_twin.html`
- **API Documentation**: `http://localhost:8000/docs`
