import tkinter as tk
from tkinter import font as tkfont
import math
import random
import logging

from config import *
from simulation import World
from objects import (Agent, Resource, Shelter, Farm, 
                     LumberMill, Mine, Blacksmith, ConstructionSite, Tool,
                     Well, FishingHut, HuntersLodge, Deer, Wolf)
from utils import Point, TerrainType, Gender, AgentState
from logger_setup import setup_logger

class CivilizationGUI:
    def __init__(self, root, world: World):
        self.root = root; self.world = world; self.is_running = True; self.root.title("AI Agent Civilization")
        main_frame = tk.Frame(root, bg="#2b2b2b"); main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_rowconfigure(0, weight=1); main_frame.grid_columnconfigure(1, weight=1)
        inspector_frame = tk.Frame(main_frame, width=250, bg="#3c3f41", bd=1, relief=tk.SUNKEN)
        inspector_frame.grid(row=0, column=0, sticky="ns", padx=(5, 2), pady=5); inspector_frame.pack_propagate(False)
        tk.Label(inspector_frame, text="INSPECTOR", font=("Arial", 14, "bold"), fg="white", bg="#3c3f41").pack(pady=10)
        self.inspector_text = tk.Label(inspector_frame, text="Click on an object...", justify=tk.LEFT, anchor="nw", fg="white", bg="#3c3f41", wraplength=230)
        self.inspector_text.pack(padx=10, pady=5, fill=tk.X)
        self.canvas = tk.Canvas(main_frame, width=world.width*CELL_SIZE, height=world.height*CELL_SIZE, bg='black', highlightthickness=0)
        self.canvas.grid(row=0, column=1, padx=0, pady=5, sticky="nsew"); self.canvas.bind("<Button-1>", self.canvas_click_handler)
        status_frame = tk.Frame(main_frame, bg="#3c3f41", height=50); status_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=(0,5))
        self.status_bar = tk.Label(status_frame, text="Initializing...", bd=1, relief=tk.FLAT, anchor=tk.W, fg="white", bg="#3c3f41")
        self.status_bar.pack(side=tk.LEFT, padx=10)
        control_frame = tk.Frame(status_frame, bg="#3c3f41"); control_frame.pack(side=tk.RIGHT, padx=10)
        self.pause_button = tk.Button(control_frame, text="Pause", command=self.toggle_pause); self.pause_button.pack(side=tk.LEFT, padx=5)
        self.step_button = tk.Button(control_frame, text="Step", command=self.step_simulation, state=tk.DISABLED); self.step_button.pack(side=tk.LEFT)
        self.emoji_font = tkfont.Font(family="Segoe UI Emoji", size=int(CELL_SIZE * 0.7)); self.small_emoji_font = tkfont.Font(family="Segoe UI Emoji", size=int(CELL_SIZE * 0.5))
        self.particles = self._init_particles()

    def update_simulation(self):
        if self.is_running: self.world.update()
        self.redraw_canvas(); self.update_status_bar(); self.root.after(UPDATE_DELAY, self.update_simulation)

    def redraw_canvas(self):
        self.canvas.delete("all"); self.draw_background_and_terrain()
        for item in sorted(self.world.get_all_objects(), key=lambda obj: obj.y): self._draw_world_object(item)
        self.draw_day_night_overlay(); self.draw_and_update_particles()

    def draw_background_and_terrain(self):
        terrain_colors = {TerrainType.GRASS: "#346834", TerrainType.WATER: "#4682B4", TerrainType.ROAD: "#8B4513"}
        for y in range(self.world.height):
            for x in range(self.world.width):
                terrain = self.world.terrain[y][x]; color = terrain_colors.get(terrain, "#346834")
                if terrain == TerrainType.GRASS and (x + y) % 2 == 0: color = "#2a542a"
                self.canvas.create_rectangle(x*CELL_SIZE, y*CELL_SIZE, (x+1)*CELL_SIZE, (y+1)*CELL_SIZE, fill=color, outline="")

    def _draw_world_object(self, item):
        draw_map = {
            Agent: self._draw_agent, Resource: self._draw_resource, Shelter: self._draw_shelter,
            Farm: self._draw_farm, LumberMill: self._draw_lumber_mill,
            ConstructionSite: self._draw_construction_site, Mine: self._draw_mine,
            Blacksmith: self._draw_blacksmith, Deer: self._draw_deer, Well: self._draw_well,
            FishingHut: self._draw_fishing_hut, HuntersLodge: self._draw_hunters_lodge,
            Wolf: self._draw_wolf,
        }
        draw_func = draw_map.get(type(item))
        if draw_func: draw_func(item)

    def _draw_agent(self, agent: Agent):
        x, y = agent.x * CELL_SIZE, agent.y * CELL_SIZE
        outline_color = 'white'
        if agent.energy < AGENT_LOW_ENERGY_THRESHOLD: outline_color = "red"
        elif agent.hydration < AGENT_LOW_HYDRATION_THRESHOLD: outline_color = "#3498db"
        padding = 2 + (math.sin(self.world.step_count * 0.2) + 1) / 4 
        if agent.gender == Gender.FEMALE: self.canvas.create_oval(x+padding, y+padding, x+CELL_SIZE-padding, y+CELL_SIZE-padding, fill=agent.role.color, outline=outline_color, width=2)
        else: self.canvas.create_rectangle(x+padding, y+padding, x+CELL_SIZE-padding, y+CELL_SIZE-padding, fill=agent.role.color, outline=outline_color, width=2)
        sprite = agent.role.sprite if agent.is_adult() else "👶"
        self.canvas.create_text(x + CELL_SIZE/2, y + CELL_SIZE/2, text=sprite, font=self.emoji_font)
        if agent.state == AgentState.COMBAT: self._draw_health_bar(agent)
        elif agent.is_pregnant: self._draw_bubble(x, y, "❤️")
        elif agent.inventory: self._draw_bubble(x, y, self.world.get_sprite_for_item_name(next(iter(agent.inventory))))
        elif agent.tool: self._draw_bubble(x, y, agent.tool.sprite)

    def _draw_health_bar(self, agent: Agent):
        x, y = agent.x * CELL_SIZE, agent.y * CELL_SIZE - 5
        health_percentage = agent.health / AGENT_MAX_HEALTH
        self.canvas.create_rectangle(x+2, y, x+CELL_SIZE-2, y+4, fill="#330000", outline="black")
        if health_percentage > 0: self.canvas.create_rectangle(x+2, y, x+2+(CELL_SIZE-4)*health_percentage, y+4, fill="#ff0000", outline="")
            
    def _draw_bubble(self, x, y, sprite):
        bx, by = x + CELL_SIZE - 5, y + 5
        self.canvas.create_oval(bx-8, by-8, bx+8, by+8, fill="white", outline="black")
        self.canvas.create_text(bx, by, text=sprite, font=self.small_emoji_font)

    def _draw_resource(self, resource: Resource):
        x, y = resource.x * CELL_SIZE, resource.y * CELL_SIZE
        self.canvas.create_text(x + CELL_SIZE/2, y + CELL_SIZE/2, text=resource.sprite, font=self.emoji_font)

    def _draw_shelter(self, shelter: Shelter):
        x, y = shelter.x * CELL_SIZE, shelter.y * CELL_SIZE
        self.canvas.create_rectangle(x+2, y+CELL_SIZE*0.4, x+CELL_SIZE-2, y+CELL_SIZE-2, fill="#ab6d43", outline="#734a2d", width=2)
        self.canvas.create_polygon(x, y+CELL_SIZE*0.45, x+CELL_SIZE, y+CELL_SIZE*0.45, x+CELL_SIZE/2, y, fill="#d13a3a", outline="#9e2b2b", width=2)

    def _draw_construction_site(self, site: ConstructionSite):
        x, y = site.x * CELL_SIZE, site.y * CELL_SIZE
        self.canvas.create_rectangle(x+2, y+2, x+CELL_SIZE-2, y+CELL_SIZE-2, fill="#f0e68c", outline="#b8860b", width=2, dash=(4, 4))
        self.canvas.create_text(x + CELL_SIZE/2, y + CELL_SIZE/2, text="🛠️", font=self.emoji_font)

    def _draw_lumber_mill(self, mill: LumberMill):
        x, y = mill.x * CELL_SIZE, mill.y * CELL_SIZE
        self.canvas.create_rectangle(x+2, y+CELL_SIZE*0.3, x+CELL_SIZE-2, y+CELL_SIZE-2, fill="#A0522D", outline="#5a2d0c", width=2)
        self.canvas.create_rectangle(x+4, y+CELL_SIZE*0.5, x+CELL_SIZE-4, y+CELL_SIZE*0.65, fill="#8B4513", outline="#5a2d0c")
        self.canvas.create_rectangle(x+6, y+CELL_SIZE*0.7, x+CELL_SIZE-6, y+CELL_SIZE*0.85, fill="#8B4513", outline="#5a2d0c")

    def _draw_farm(self, farm: Farm):
        x, y = farm.x * CELL_SIZE, farm.y * CELL_SIZE
        self.canvas.create_rectangle(x+2, y+2, x+CELL_SIZE-2, y+CELL_SIZE-2, fill="#6b4423", outline="#4a2f19", width=1)
        growth = farm.production_progress / FARM_PRODUCTION_CYCLE
        for i in range(3):
            cx = x + (i + 1.5) * (CELL_SIZE / 4); ch = (CELL_SIZE / 2.5) * growth
            self.canvas.create_line(cx, y+CELL_SIZE-5, cx, y+CELL_SIZE-5 - ch, fill="#5a945a", width=3)
            self.canvas.create_oval(cx-2, y+CELL_SIZE-7-ch, cx+2, y+CELL_SIZE-3-ch, fill="green", outline="")

    def _draw_mine(self, mine: Mine):
        x, y = mine.x * CELL_SIZE, mine.y * CELL_SIZE
        self.canvas.create_rectangle(x, y+CELL_SIZE*0.3, x+CELL_SIZE, y+CELL_SIZE, fill="#A9A9A9", outline="#696969", width=2)
        self.canvas.create_oval(x+CELL_SIZE*0.2, y+CELL_SIZE*0.5, x+CELL_SIZE*0.8, y+CELL_SIZE, fill="black", outline="")

    def _draw_blacksmith(self, blacksmith: Blacksmith):
        x, y = blacksmith.x * CELL_SIZE, blacksmith.y * CELL_SIZE
        self.canvas.create_rectangle(x+2, y+CELL_SIZE*0.2, x+CELL_SIZE-2, y+CELL_SIZE-2, fill="#696969", outline="#404040", width=2)
        self.canvas.create_rectangle(x+CELL_SIZE*0.6, y+CELL_SIZE*0.5, x+CELL_SIZE*0.9, y+CELL_SIZE*0.7, fill="#404040", outline="black")
        pulse = (math.sin(self.world.step_count * 0.3) + 1) / 2; color_val = int(150 + 105 * pulse)
        self.canvas.create_oval(x+CELL_SIZE*0.1, y+CELL_SIZE*0.4, x+CELL_SIZE*0.5, y+CELL_SIZE*0.8, fill=f'#ff{color_val:02x}00', outline="red")
    
    def _draw_deer(self, deer: Deer): self.canvas.create_text((deer.x+0.5)*CELL_SIZE, (deer.y+0.5)*CELL_SIZE, text="🦌", font=self.emoji_font)
    def _draw_wolf(self, wolf: Wolf): self.canvas.create_text((wolf.x+0.5)*CELL_SIZE, (wolf.y+0.5)*CELL_SIZE, text="🐺", font=self.emoji_font)
    def _draw_well(self, well: Well):
        x, y = well.x * CELL_SIZE, well.y * CELL_SIZE
        self.canvas.create_oval(x+4, y+4, x+CELL_SIZE-4, y+CELL_SIZE-4, fill="#3d3d3d", outline="#2a2a2a", width=2)
        self.canvas.create_rectangle(x+3, y+CELL_SIZE*0.4, x+7, y+CELL_SIZE*0.8, fill="#8B4513", outline="#5a2d0c")
        self.canvas.create_rectangle(x+CELL_SIZE-7, y+CELL_SIZE*0.4, x+CELL_SIZE-3, y+CELL_SIZE*0.8, fill="#8B4513", outline="#5a2d0c")
    def _draw_fishing_hut(self, hut: FishingHut):
        x, y = hut.x * CELL_SIZE, hut.y * CELL_SIZE
        self.canvas.create_rectangle(x+3, y+3, x+CELL_SIZE-3, y+CELL_SIZE-3, fill="#87CEEB", outline="#008B8B", width=2)
        self.canvas.create_text(x+CELL_SIZE/2, y+CELL_SIZE/2, text="🎣", font=self.emoji_font)
    def _draw_hunters_lodge(self, lodge: HuntersLodge):
        x, y = lodge.x * CELL_SIZE, lodge.y * CELL_SIZE
        self.canvas.create_rectangle(x+2, y+CELL_SIZE*0.3, x+CELL_SIZE-2, y+CELL_SIZE-2, fill="#8B4513", outline="#5a2d0c", width=2)
        self.canvas.create_polygon(x, y+CELL_SIZE*0.3, x+CELL_SIZE, y+CELL_SIZE*0.3, x+CELL_SIZE/2, y, fill="#A0522D", outline="#5a2d0c", width=2)
        self.canvas.create_text(x+CELL_SIZE/2, y+CELL_SIZE*0.6, text="🏹", font=self.emoji_font)

    def update_status_bar(self):
        time = "Day" if not self.world.is_night() else "Night"
        status = (f"Step: {self.world.step_count} | {time} | Agents: {len(self.world.get_all_agents())} | "
                  f"Directive: {self.world.oracle.directive.name} | Global Inventory: {self.world.get_global_inventory()}")
        self.status_bar.config(text=status)

    def canvas_click_handler(self, event):
        x, y = event.x // CELL_SIZE, event.y // CELL_SIZE
        items = self.world.get_objects_at(Point(x, y))
        info = f"Location: ({x}, {y})\nTerrain: {self.world.terrain[y][x].name}\n\n"
        if items:
            item = items[0] 
            info += f"TYPE: {type(item).__name__}\n"
            if isinstance(item, Agent):
                status = item.state.name
                if item.is_pregnant: status = f"Pregnant ({item.pregnancy_timer}/{PREGNANCY_DURATION})"
                info += (f"ID: {item.agent_id} ({item.gender.name})\nROLE: {item.role.role_name}\nSTATE: {status}\n"
                         f"ENERGY: {item.energy:.1f}\nHYDRATION: {item.hydration:.1f}\n"
                         f"INVENTORY: {dict(item.inventory) or 'Empty'}")
            elif isinstance(item, Resource): info += f"NAME: {item.name}\n"
            elif isinstance(item, ConstructionSite): info += f"BUILDING: {item.structure_type.name}\nNEEDS: {dict(item.needed_resources)}"
            elif isinstance(item, Shelter): info += f"INVENTORY: {dict(item.inventory)}"
        self.inspector_text.config(text=info)

    def toggle_pause(self):
        self.is_running = not self.is_running
        self.pause_button.config(text="Resume" if not self.is_running else "Pause")
        self.step_button.config(state=tk.NORMAL if not self.is_running else tk.DISABLED)

    def step_simulation(self):
        if not self.is_running: self.world.update(); self.redraw_canvas(); self.update_status_bar()

    def _init_particles(self):
        return [{'x': random.uniform(0, self.world.width*CELL_SIZE), 'y': random.uniform(0, self.world.height*CELL_SIZE),
                 'vx': random.uniform(-0.5, 0.5), 'vy': random.uniform(0.5, 1.5), 'size': random.randint(2, 4)} for _ in range(50)]

    def draw_day_night_overlay(self):
        darkness = (math.sin((self.world.time_of_day / DAY_NIGHT_DURATION)*2*math.pi - math.pi/2) + 1) / 2 
        if darkness > 0.6: self.canvas.create_rectangle(0, 0, self.world.width*CELL_SIZE, self.world.height*CELL_SIZE, fill="#000033", outline="", stipple="gray50")

    def draw_and_update_particles(self):
        is_night = self.world.is_night()
        for p in self.particles:
            p['x'] += p['vx']; p['y'] += p['vy']
            if p['y'] > self.world.height * CELL_SIZE: p['y'] = 0; p['x'] = random.uniform(0, self.world.width * CELL_SIZE)
            color = "yellow" if is_night else "#cb6d51"
            if is_night and random.random() < 0.01: self.canvas.create_oval(p['x'], p['y'], p['x']+p['size'], p['y']+p['size'], fill=color, outline="")
            elif not is_night: self.canvas.create_oval(p['x'], p['y'], p['x']+p['size'], p['y']+p['size'], fill=color, outline="")

def main():
    setup_logger(); logging.info("Simulation starting...")
    root = tk.Tk(); world = World(WORLD_WIDTH, WORLD_HEIGHT); world.initialize_world()
    gui = CivilizationGUI(root, world); gui.update_simulation(); root.mainloop()
    logging.info("Simulation finished.")

if __name__ == "__main__":
    main()