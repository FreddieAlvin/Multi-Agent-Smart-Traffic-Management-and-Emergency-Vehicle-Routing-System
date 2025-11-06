# 🏙️ Multi-Agent Smart Traffic Management and Emergency Vehicle Routing System

A **multi-agent simulation** of a Manhattan-style city grid using [SPADE](https://spade-mas.readthedocs.io/) for communication between vehicles, traffic lights, and emergency responders.  
The environment uses **NetworkX** to model roads, **dynamic routing**, and **event management** (incidents, congestion, roadblocks, etc.).

---

## 🚀 Features

### ✅ City Environment
- Grid-based graph (`networkx.grid_2d_graph`)
- Traffic lights, buildings, and hospitals
- Dynamic edge weights (affected by incidents or congestion)

### ✅ Agents
- **VehicleAgent** → moves around, reports congestion, requests passage  
- **EmergencyVehicleAgent** → requests priority routing  
- **TrafficLightAgent** → responds to passage and priority requests  
- **IncidentReporterAgent** → creates random incidents  

### ✅ Event System
- Manages active incidents and roadblocks with TTL (time-to-live)
- Updates route costs dynamically

### ✅ Occupancy Tracking
- Tracks vehicles on edges
- Computes road density (using Exponential Moving Averages)
- Integrates congestion levels into A*/Dijkstra routing

---

## 🧩 Project Structure

city_simulation/
│
├── environment/
│ ├── city_environment.py # Graph and world generation
│ ├── event_manager.py # Incident and roadblock management
│ ├── occupancy.py # Density and capacity tracking
│
├── agents/
│ ├── vehicle_agent.py
│ ├── emergency_vehicle_agent.py
│ ├── traffic_light_agent.py
│ ├── incident_reporter_agent.py
│
├── utils/
│ ├── routing.py # Shortest path, nearest traffic light
│
├── run_simulation.py # Entry point to launch agents
├── requirements.txt
└── README.md


---

## ⚙️ Installation

```bash
# Clone the repository
git clone https://github.com/FreddieAlvin/Multi-Agent-Smart-Traffic-Management-and-Emergency-Vehicle-Routing-System.git
cd Multi-Agent-Smart-Traffic-Management-and-Emergency-Vehicle-Routing-System

# (Optional) Create a virtual environment
python -m venv venv
source venv/bin/activate     # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
