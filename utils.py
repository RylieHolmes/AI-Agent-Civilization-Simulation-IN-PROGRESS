import heapq
from enum import Enum
from collections import namedtuple, defaultdict
import math
import logging

class Point:
    def __init__(self, x, y): self.x = x; self.y = y
    def __eq__(self, other): return self.x == other.x and self.y == other.y
    def __hash__(self): return hash((self.x, self.y))
    def __lt__(self, other): return self.y < other.y or (self.y == other.y and self.x < other.x)
    def distance_to(self, other): return abs(self.x - other.x) + abs(self.y - other.y)
    def __repr__(self): return f"Point({self.x}, {self.y})"

def heuristic(a, b): return abs(a.x - b.x) + abs(a.y - b.y)

class Gender(Enum): MALE = 1; FEMALE = 2

class AgentState(Enum):
    IDLE=1; MOVING=2; WORKING=3; RESTING=4; SEEKING_FOOD=5; SEEKING_WATER=6; SEEKING_SHELTER=7
    SEEKING_PARTNER=8; PREGNANT=9; SUPPORTING_PARTNER=10; BUILDING=11; SEEKING_TOOL=12; COMBAT=13

class ToolType(Enum):
    AXE = ("Axe", "🪓", {"Iron Ingot": 2}, ["Wood"])
    PICKAXE = ("Pickaxe", "⛏️", {"Iron Ingot": 3, "Wood": 1}, ["Stone", "Iron Ore"])
    def __init__(self, n, s, r, g): self.tool_name=n; self.sprite=s; self.recipe=r; self.gathers=g

class AgentRole(Enum):
    LUMBERJACK=("Lumberjack","🪓","#c19a6b",True,ToolType.AXE);MINER=("Miner","⛏️","#808080",True,ToolType.PICKAXE)
    BUILDER=("Builder","👷","#ffb400",True,None);FARMER=("Farmer","🧑‍🌾","#654321",True,None)
    BLACKSMITH=("Blacksmith","🧑‍🏭","#4c4c4c",True,None);HUNTER=("Hunter","🏹","#006400",True,None)
    FISHERMAN=("Fisherman","🎣","#00008b",True,None)
    def __init__(self, n, s, c, i, r): self.role_name=n;self.sprite=s;self.color=c;self.is_starter_role=i;self.required_tool=r

class ResourceType(Enum):
    WOOD=("Wood","🌳","#8B4513");STONE=("Stone","🪨","#808080");IRON_ORE=("Iron Ore","⚙️","#A9A9A9")
    IRON_INGOT=("Iron Ingot","🔩","#d3d3d3");FOOD=("Food","🍎","#ff0000");FISH=("Fish","🐟","#4682b4")
    MEAT=("Meat","🥩","#d2691e")
    def __init__(self, n, s, c): self.resource_name=n;self.sprite=s;self.color=c

class StructureType(Enum):
    SHELTER=("Shelter",{"Wood":10,"Stone":5});FARM=("Farm",{"Wood":15});LUMBER_MILL=("Lumber Mill",{"Wood":20,"Stone":10})
    MINE=("Mine",{"Wood":15,"Stone":20});BLACKSMITH=("Blacksmith",{"Stone":30,"Iron Ingot":5})
    WELL=("Well",{"Stone":15});FISHING_HUT=("Fishing Hut",{"Wood":10});HUNTERS_LODGE=("Hunter's Lodge",{"Wood":15,"Stone":5})
    def __init__(self, n, r): self.structure_name=n; self.recipe=r
    def get_class(self):
        from objects import Shelter, Farm, LumberMill, Mine, Blacksmith, Well, FishingHut, HuntersLodge
        class_map = {"Shelter":Shelter,"Farm":Farm,"Lumber Mill":LumberMill,"Mine":Mine,
                     "Blacksmith":Blacksmith,"Well":Well,"Fishing Hut":FishingHut,"Hunter's Lodge":HuntersLodge}
        return class_map.get(self.structure_name)

class Directive(Enum):
    STOCKPILE_RESOURCES=1;BUILD_SHELTER=StructureType.SHELTER;BUILD_FARM=StructureType.FARM
    BUILD_LUMBER_MILL=StructureType.LUMBER_MILL;BUILD_MINE=StructureType.MINE
    BUILD_BLACKSMITH=StructureType.BLACKSMITH;BUILD_WELL=StructureType.WELL
    BUILD_FISHING_HUT=StructureType.FISHING_HUT;BUILD_HUNTERS_LODGE=StructureType.HUNTERS_LODGE

class TerrainType(Enum): GRASS=1; WATER=2; ROAD=3

class SpatialHash:
    def __init__(self, cell_size): self.cell_size=cell_size; self.grid=defaultdict(set)
    def _get_cell_coords(self, pos: Point): return (pos.x // self.cell_size, pos.y // self.cell_size)
    def add(self, obj): self.grid[self._get_cell_coords(obj.pos)].add(obj)
    def remove(self, obj):
        cell = self._get_cell_coords(obj.pos)
        if obj in self.grid[cell]: self.grid[cell].remove(obj)
    
    def move(self, obj, old_pos: Point):
        old_cell = self._get_cell_coords(old_pos)
        if obj in self.grid[old_cell]: self.grid[old_cell].remove(obj)
        new_cell = self._get_cell_coords(obj.pos); self.grid[new_cell].add(obj)

    def get_at(self, pos: Point): return list(self.grid[self._get_cell_coords(pos)])
    def query_radius(self, pos: Point, radius: int):
        res = set()
        x_min,y_min=(pos.x-radius)//self.cell_size,(pos.y-radius)//self.cell_size
        x_max,y_max=(pos.x+radius)//self.cell_size,(pos.y+radius)//self.cell_size
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1): res.update(self.grid.get((x, y), set()))
        return list(res)
    def get_all(self): return [obj for cell in self.grid.values() for obj in cell]

def a_star_search(world, start, end):
    # --- MODIFIED: The check for a valid destination now ALSO ignores agents. This is the fix.
    if not world.is_passable(end, ignore_agents=True):
        accessible_end = world.find_adjacent_empty(end)
        if not accessible_end: 
            logging.debug(f"A* Search: Cannot find any accessible adjacent tile to {end}")
            return None 
        end = accessible_end
        
    neighbors = [(0,1),(0,-1),(1,0),(-1,0),(1,1),(1,-1),(-1,1),(-1,-1)]
    close_set=set(); came_from={}; gscore={start: 0}; fscore={start:heuristic(start,end)}
    oheap=[(fscore[start], start)]
    while oheap:
        current = heapq.heappop(oheap)[1]
        if current == end:
            path=[]
            while current in came_from: path.append(current); current=came_from[current]
            return path[::-1]
        close_set.add(current)
        for i,j in neighbors:
            neighbor = Point(current.x+i, current.y+j)
            if not (0 <= neighbor.x < world.width and 0 <= neighbor.y < world.height): continue
            if not world.is_passable(neighbor, ignore_agents=True) and neighbor != end: continue
            tentative_g_score = gscore[current] + 1
            if tentative_g_score < gscore.get(neighbor, float('inf')):
                came_from[neighbor] = current; gscore[neighbor] = tentative_g_score
                fscore[neighbor] = tentative_g_score + heuristic(neighbor, end)
                if neighbor not in [item[1] for item in oheap]: heapq.heappush(oheap, (fscore[neighbor], neighbor))
    return None