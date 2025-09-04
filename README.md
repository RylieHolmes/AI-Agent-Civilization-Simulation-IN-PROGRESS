# AI Agent Civilization Simulation

A dynamic multi-agent simulation where autonomous agents with distinct roles work together to gather resources, construct buildings, and develop a small civilization from scratch. The project is built in Python using `tkinter` for the graphical user interface.

![Project Screenshot](<./path_to_your_screenshot.png>)
*(**Note:** Replace the path above with a real screenshot of your simulation running!)*

## About The Project

This simulation explores emergent behavior in a system of autonomous agents. Each agent operates based on a simple set of rules and a state machine, but together they can achieve complex goals. The civilization's overall direction is guided by a high-level "Oracle" AI, which sets strategic directives like "Build a Well" or "Build a Farm" based on the colony's current needs.

The goal is to observe how a small group of agents with simple individual logic can bootstrap a functioning micro-society, complete with resource supply chains, construction projects, and survival instincts.

### Core Features

*   **Autonomous Agents:** Each agent manages its own needs, such as energy and hydration, and will seek out food and water when low.
*   **Role-Based AI:** Agents are assigned roles (Builder, Lumberjack, Miner, Hunter, etc.) that define their primary tasks and behaviors.
*   **Resource Management:** Agents gather essential resources like Wood, Stone, and Ore from the environment. A global inventory tracks the civilization's wealth.
*   **Construction System:** Builders can construct a variety of buildings (Wells, Lumber Mills, Farms) based on recipes. The system is dynamic, with agents gathering and delivering the required materials to construction sites.
*   **The Oracle AI Director:** A high-level AI that analyzes the state of the world and issues strategic directives to guide the civilization's growth and address its most pressing needs.
*   **Dynamic Environment:** Features a day/night cycle, procedural terrain generation, and resource regeneration. Pathfinding uses the A* algorithm, and a Spatial Hash Grid ensures efficient querying of nearby objects.
*   **Interactive GUI:** Built with Python's native `tkinter` library, the GUI provides a real-time visualization of the world. You can click on any tile or agent to inspect its current state and properties.

### Technologies Used

*   **Python 3**
*   **Tkinter** (for the Graphical User Interface)

## Getting Started

Follow these simple steps to get the simulation running on your local machine.

### Prerequisites

*   Python 3.8 or newer. You can download it from [python.org](https://www.python.org/).

### Installation & Usage

1.  **Clone the repository:**
    ```sh
    git clone https://github.com/your-username/AI-Agent-Civilization-Simulation.git
    ```
2.  **Navigate to the project directory:**
    ```sh
    cd AI-Agent-Civilization-Simulation
    ```
3.  **Run the simulation:**
    ```sh
    python main.py
    ```
    The simulation window should appear and the agents will begin their tasks immediately.

## Project Structure

The project is organized into several key files, each with a distinct responsibility:

*   `main.py`: The main entry point of the application. Initializes the world and the GUI, and contains the main simulation loop.
*   `simulation.py`: The core simulation engine. Contains the `World` class that manages all objects, terrain, and game state, as well as the `Oracle` AI director.
*   `objects.py`: Defines all the classes for entities that exist in the world, such as `Agent`, `Resource`, `ConstructionSite`, and all building types. Contains the core agent AI and state machine logic.
*   `utils.py`: A collection of helper classes and functions, including the `Point` class for coordinates, all `Enums` (e.g., `AgentRole`, `ResourceType`), the `SpatialHash` grid, and the `a_star_search` function.
*   `config.py`: A centralized file for all simulation parameters and "magic numbers" (e.g., world size, agent speed, building costs), allowing for easy tuning and balancing.
*   `logger_setup.py`: A simple utility to configure the console logger for detailed debug output.

## Future Enhancements

This project has a solid foundation that can be extended in many exciting ways:

*   [ ] **Physicalized Inventory:** Implement Stockpile/Warehouse buildings where agents must physically deposit and retrieve resources, creating logistical challenges.
*   [ ] **Complex Social Dynamics:** Introduce family units, claimed shelters, and more advanced social interactions between agents.
*   [ ] **Dynamic Task System:** Move from fixed roles to a "job board" where the Oracle posts tasks that any available agent can claim.
*   [ ] **Environmental Events:** Add seasons, weather, or random events like forest fires or resource booms that the civilization must adapt to.

## License

Distributed under the MIT License. See `LICENSE` for more information.