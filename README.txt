Multi-Agent Smart Traffic Management and Emergency Vehicle Routing System
============================================================================

1. Project overview
-------------------
This project implements a multi-agent simulation of an urban traffic grid using SPADE.
Four types of agents interact over an XMPP server:
  - Vehicle agents
  - Emergency vehicle agents (ambulances)
  - Traffic light agents
  - Incident reporter agent

The city is modelled as a NetworkX grid graph with dynamic edge weights that account
for incidents and congestion. Metrics such as trip times and emergency response
times are logged during the simulation.


2. Requirements
---------------
- Python 3.10 or 3.11
- A running XMPP server accessible at localhost (e.g. Prosody, Openfire, or SPADE demo server)
- The Python packages listed in requirements.txt

All Python dependencies are installed via:

    pip install -r requirements.txt


3. Installation
---------------
1) Download or clone the project into a local directory.

2) (Recommended) Create and activate a virtual environment, for example:

    python -m venv .venv
    source .venv/bin/activate        # Linux/macOS
    .venv\Scripts\activate.bat     # Windows

3) Install all dependencies:

    pip install -r requirements.txt


4. XMPP server configuration
----------------------------
The agents use SPADE and expect an XMPP server running on localhost.

Typical configuration:
  - Server: localhost
  - Example JIDs used in the project:
      vehicle1@localhost, vehicle2@localhost, ...
      emergency1@localhost, ...
      light_0_0@localhost, ...
      reporter@localhost
  - All agents use the password: "password" (as defined in the code).

Ensure that the XMPP server is running and these accounts are allowed or can be
auto-registered by SPADE before starting the simulation.


5. How to run the simulation
----------------------------
1) Make sure the virtual environment is activated (if used).

2) From the root of the project, run:

    python main.py

3) The simulation will:
   - Create the city environment and all agents (vehicles, traffic lights,
     emergency vehicles and reporter).
   - Start the matplotlib visualizer window showing the grid, vehicles,
     hospitals, traffic lights and incidents.
   - Log metrics into metrics.csv and generate plot images when the program
     terminates cleanly.

4) To stop the simulation, use CTRL+C in the terminal where main.py is running.
   On termination, the code attempts to:
     - Compute a summary of metrics.
     - Save metrics.csv.
     - Save PNG plots with prefixes based on the metrics filename.


6. Output files
---------------
After running the simulation you should obtain:

  - metrics.csv
      Contains rows with:
        type, id, value
      Example:
        trip, vehicle3, 17.42
        ev_response, EV, 11.90

  - metrics_trip_hist.png
  - metrics_trip_series.png
  - metrics_ev_hist.png
  - metrics_ev_series.png
  - metrics_rho_series.png (only if congestion snapshots were recorded)

These files can be used to analyse the behaviour of the system, average trip
times, emergency response times and (optionally) congestion over time.


7. Notes
--------
- The number of vehicles, emergency vehicles and the city size are defined in
  main.py and can be adjusted if needed.
- If the visualizer window is closed, the simulation may continue in the
  background until interrupted in the terminal.
- If you change the XMPP domain or accounts, remember to update the agent JIDs
  in main.py accordingly.
