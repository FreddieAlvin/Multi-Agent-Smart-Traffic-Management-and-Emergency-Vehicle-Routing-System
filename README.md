# Multi-Agent-Smart-Traffic-Management-and-Emergency-Vehicle-Routing-System

A multi-agent simulation of a Manhattan-style city grid using SPADE for communication between vehicles, traffic lights, and emergency responders.
The environment uses NetworkX to model roads, dynamic routing, and event management (incidents, congestion, roadblocks, etc.).
🚀 Features
✅ City environment
Grid-based graph (networkx.grid_2d_graph)
Traffic lights, buildings, and hospitals
Dynamic edge weights (affected by incidents or congestion)
✅ Agents
VehicleAgent → moves around, reports congestion, requests passage
EmergencyVehicleAgent → requests priority routing
TrafficLightAgent → responds to passage and priority requests
IncidentReporterAgent → creates random incidents
✅ Event system
Manages active incidents and roadblocks with TTL (time-to-live)
Updates route costs dynamically
✅ Occupancy tracking
Tracks vehicles on edges
Computes road density (can later use exponential moving averages)

## Project Structure

city_simulation/
│
├── environment/
│   ├── city_environment.py      # Graph and world generation
│   ├── event_manager.py         # Incident and roadblock management
│   ├── occupancy.py             # Density and capacity tracking
│
├── agents/
│   ├── vehicle_agent.py
│   ├── emergency_vehicle_agent.py
│   ├── traffic_light_agent.py
│   ├── incident_reporter_agent.py
│
├── utils/
│   ├── routing.py               # Shortest path, nearest traffic light
│
├── run_simulation.py            # Entry point to launch agents
├── requirements.txt
└── README.md

## Installation 

Clone the repo
git clone https://github.com/<your-username>/city-simulation.git
cd city-simulation

(Optional) create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

Install dependencies
pip install -r requirements.txt

## Usage 
Start the XMPP server (if you’re using localhost):
prosodyctl start

Then run your agents — for example:
python agents/traffic_light_agent.py
python agents/vehicle_agent.py
python agents/emergency_vehicle_agent.py
python agents/incident_reporter_agent.py

## Configuration
You can modify:
Grid size in CityEnvironment(width, height)
Incident frequency in IncidentReporterAgent
Traffic light spacing in _generate_traffic_lights()
Road capacities in Occupancy