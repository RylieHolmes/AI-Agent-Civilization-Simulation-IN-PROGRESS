import random
import logging
import math
from collections import defaultdict, deque
from typing import Dict, List, Optional, Callable, Any

from config import *
from objects import (Agent, Resource, Shelter, Farm, LumberMill, 
                     Mine, Blacksmith, ConstructionSite, Tool, Deer,
                     Well, FishingHut, HuntersLodge, ProductionBuilding, Wolf)
from utils import (Point, AgentRole, AgentState, ResourceType, StructureType, 
                   TerrainType, ToolType, Gender, Directive, SpatialHash, a_star_search)

class Oracle:
    """The AI 'brain' for the civilization, determining high-level goals."""
    def __init__(self):
        self.directive: Directive = Directive.STOCKPILE_RESOURCES

    def update_directive(self, world: 'World', force_update: bool = False):
        if not force_update and world.step_count % 100 != 0: 
            return
        num_agents = len(world.get_all_agents())
        if num_agents == 0: return
        inventory = world.get_global_inventory()
        structures = world.get_all_structures()
        num_shelters = len([s for s in structures if isinstance(s, Shelter)])
        has_well = any(isinstance(s, Well) for s in structures)
        old_directive = self.directive
        food_count = (inventory.get(ResourceType.FOOD.resource_name, 0) + 
                      inventory.get(ResourceType.FISH.resource_name, 0) + 
                      inventory.get(ResourceType.MEAT.resource_name, 0))
        if not has_well: self.directive = Directive.BUILD_WELL
        elif food_count < num_agents * 5:
            if not any(isinstance(s, (Farm, FishingHut, HuntersLodge)) for s in structures):
                if world.is_terrain_present(TerrainType.WATER): self.directive = Directive.BUILD_FISHING_HUT
                else: self.directive = Directive.BUILD_FARM
        elif inventory.get(ResourceType.WOOD.resource_name, 0) < num_agents * 8 and not any(isinstance(s, LumberMill) for s in structures):
            self.directive = Directive.BUILD_LUMBER_MILL
        elif inventory.get(ResourceType.STONE.resource_name, 0) < num_agents * 5 and not any(isinstance(s, Mine) for s in structures):
            self.directive = Directive.BUILD_MINE
        elif num_shelters < (num_agents / 2) + 1: self.directive = Directive.BUILD_SHELTER
        elif not any(isinstance(s, Blacksmith) for s in structures) and inventory.get(ResourceType.IRON_ORE.resource_name, 0) > 5:
             self.directive = Directive.BUILD_BLACKSMITH
        else: self.directive = Directive.STOCKPILE_RESOURCES
        if old_directive != self.directive: 
            logging.info(f"ORACLE: New directive set to {self.directive.name}")

class World:
    """Manages all objects, terrain, and the main simulation state."""
    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.step_count = 0
        self.time_of_day = 0
        self.terrain: List[List[TerrainType]] = [[TerrainType.GRASS for _ in range(width)] for _ in range(height)]
        self.path_usage: Dict[Point, int] = defaultdict(int)
        self.objects_grid = SpatialHash(CELL_SIZE)
        self.next_agent_id = 0
        self.oracle = Oracle()
        self.global_inventory = defaultdict(int)
        self.water_distance_map: Optional[List[List[int]]] = None
    
    def initialize_world(self):
        self._generate_terrain()
        self._calculate_water_distance_map()
        start_pos = Point(self.width // 2, self.height // 2)
        if self.terrain[start_pos.y][start_pos.x] == TerrainType.WATER:
            empty_spot = self.find_empty_spot_near(start_pos, 10)
            if empty_spot: start_pos = empty_spot
            else: start_pos = Point(1,1)

        logging.info("Initializing global inventory.")
        self.global_inventory[ToolType.AXE.tool_name] += 2
        self.global_inventory[ToolType.PICKAXE.tool_name] += 2
        for _ in range(25):
            self.spawn_resource_near(start_pos, ResourceType.WOOD, 20)
            self.spawn_resource_near(start_pos, ResourceType.STONE, 20)
            
        starter_roles = [r for r in AgentRole if r.is_starter_role]
        for i in range(STARTING_AGENTS):
            # --- MODIFIED: Increased spawn radius from 15 to 20 to prevent spawn failures.
            spawn_pos = self.find_empty_spot_near(start_pos, 20) 
            if not spawn_pos:
                logging.error(f"Could not find a valid spawn location for agent {i}. Skipping.")
                continue
            role = AgentRole.BUILDER if i % 4 == 0 else random.choice(starter_roles)
            self.spawn_agent(pos=spawn_pos, gender=Gender.MALE if i < STARTING_AGENTS / 2 else Gender.FEMALE, role=role, start_age=ADULT_AGE_THRESHOLD)

        for _ in range(40): self.spawn_resource()
        for _ in range(8): self.spawn_animal()

    def update(self):
        self.step_count += 1
        self.time_of_day = (self.time_of_day + 1) % DAY_NIGHT_DURATION
        self.oracle.update_directive(self)
        if self.step_count % RESOURCE_REGEN_INTERVAL == 0: self.spawn_resource()
        if self.step_count % ANIMAL_SPAWN_INTERVAL == 0: self.spawn_animal()
        if self.step_count % ROAD_UPDATE_INTERVAL == 0: self._update_roads()
        
        all_objects = self.get_all_objects()
        for obj in all_objects:
            if hasattr(obj, 'update'): obj.update(self)

        if self.step_count % 10 == 0:
            sites = [obj for obj in all_objects if isinstance(obj, ConstructionSite)]
            if sites:
                num_builders = len([a for a in self.get_all_agents() if a.role == AgentRole.BUILDER]) or 1
                for site in sites:
                    if site.failed_path_attempts > num_builders * 5:
                        logging.warning(f"Removing stuck construction site at {site.pos} after {site.failed_path_attempts} path failures.")
                        self.remove_object(site)
        
        for site in [obj for obj in all_objects if isinstance(obj, ConstructionSite) and obj.is_complete]:
            self.complete_construction(site)

    def spawn_agent(self, gender: Gender, role: AgentRole, pos: Point, start_age: int = 0):
        agent = Agent(pos, self.next_agent_id, role, gender, start_age=start_age)
        self.add_object(agent)
        logging.info(f"AGENT SPAWNED: ID {self.next_agent_id} at ({pos.x},{pos.y}) as a {role.role_name}.")
        self.next_agent_id += 1

    def complete_construction(self, site: 'ConstructionSite'):
        structure_class = site.structure_type.get_class()
        new_building = structure_class(site.pos)
        self.remove_object(site); self.add_object(new_building)
        logging.info(f"CONSTRUCTION COMPLETE: {site.structure_type.name} built at ({site.pos.x},{site.pos.y}).")
        self.oracle.update_directive(self, force_update=True)
        
    def create_construction_site(self, pos: Point, structure_enum: StructureType):
        if pos and self.is_passable(pos, for_building=True):
            site = ConstructionSite(pos, structure_enum)
            self.add_object(site)
        else:
            logging.error(f"ATTEMPTED TO CREATE SITE AT INVALID LOCATION: {pos}")

    def add_object(self, obj): self.objects_grid.add(obj)
    def remove_object(self, obj): self.objects_grid.remove(obj)
    def move_object(self, obj, new_pos: Point):
        old_pos = obj.pos
        obj.set_pos(new_pos)
        self.objects_grid.move(obj, old_pos)

    def get_objects_at(self, pos: Point) -> List: return self.objects_grid.get_at(pos)
    def get_all_objects(self) -> List: return self.objects_grid.get_all()
    def get_all_agents(self) -> List[Agent]: return [o for o in self.get_all_objects() if isinstance(o, Agent)]
    def get_all_structures(self) -> List: return [o for o in self.get_all_objects() if isinstance(o, (ProductionBuilding, Shelter, Well))]
    
    def is_passable(self, pos: Point, for_building: bool = False, ignore_agents: bool = False) -> bool:
        if not (0 <= pos.x < self.width and 0 <= pos.y < self.height): return False
        if self.terrain[pos.y][pos.x] == TerrainType.WATER: return False
        objects_at_pos = self.get_objects_at(pos)
        obstacle_types = [ProductionBuilding, Shelter, ConstructionSite, Well]
        if for_building: obstacle_types.append(Resource)
        if not ignore_agents: obstacle_types.append(Agent)
        return not any(isinstance(o, tuple(obstacle_types)) for o in objects_at_pos)

    def is_night(self) -> bool: return self.time_of_day > DAY_NIGHT_DURATION / 2

    def find_nearest(self, start_pos: Point, condition: Callable[[Any], bool]) -> Optional[Any]:
        valid_targets = [obj for obj in self.objects_grid.query_radius(start_pos, AGENT_VIEW_DISTANCE * 3) if condition(obj)]
        if not valid_targets: return None
        return min(valid_targets, key=lambda obj: start_pos.distance_to(obj.pos))

    def find_adjacent_empty(self, pos: Point) -> Optional[Point]:
        neighbors = [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (1,1), (-1,-1), (1,-1)]
        random.shuffle(neighbors)
        for dx, dy in neighbors:
            check_pos = Point(pos.x + dx, pos.y + dy)
            if self.is_passable(check_pos, ignore_agents=True): return check_pos
        return None

    def find_empty_spot_near(self, pos: Point, radius: int, for_building: bool = False, check_path_from: Optional[Point] = None) -> Optional[Point]:
        for _ in range(100):
            r = random.uniform(radius * 0.2, radius)
            angle = random.uniform(0, 2 * math.pi)
            check_pos = Point(int(pos.x + r * math.cos(angle)), int(pos.y + r * math.sin(angle)))
            if 0 <= check_pos.x < self.width and 0 <= check_pos.y < self.height:
                if self.is_passable(check_pos, for_building=for_building):
                    if for_building:
                        interaction_spot = self.find_adjacent_empty(check_pos)
                        if not interaction_spot: continue
                        if check_path_from and not a_star_search(self, check_path_from, interaction_spot): continue
                    return check_pos
        return None
    
    def find_spot_near_terrain(self, center: Point, radius: int, terrain_type: TerrainType, check_path_from: Optional[Point] = None) -> Optional[Point]:
        for _ in range(150):
            r = random.uniform(radius * 0.2, radius)
            angle = random.uniform(0, 2 * math.pi)
            check_pos = Point(int(center.x + r * math.cos(angle)), int(center.y + r * math.sin(angle)))
            if 0 <= check_pos.x < self.width and 0 <= check_pos.y < self.height:
                if self.is_passable(check_pos, for_building=True):
                    if not self.is_near_terrain(check_pos, terrain_type, distance=2): continue
                    interaction_spot = self.find_adjacent_empty(check_pos)
                    if not interaction_spot: continue
                    if check_path_from and not a_star_search(self, check_path_from, interaction_spot): continue
                    return check_pos
        return None
    
    def is_near_terrain(self, pos: Point, terrain_type: TerrainType, distance: int) -> bool:
        for y in range(pos.y - distance, pos.y + distance + 1):
            for x in range(pos.x - distance, pos.x + distance + 1):
                if 0 <= x < self.width and 0 <= y < self.height:
                    if self.terrain[y][x] == terrain_type: return True
        return False
    
    def is_terrain_present(self, terrain_type: TerrainType) -> bool:
        return any(terrain_type in row for row in self.terrain)

    def get_sprite_for_item_name(self, item_name: str) -> str:
        for res_type in ResourceType:
            if res_type.resource_name == item_name: return res_type.sprite
        for tool_type in ToolType:
            if tool_type.tool_name == item_name: return tool_type.sprite
        return "?"

    def get_global_inventory(self) -> Dict[str, int]:
        return dict(self.global_inventory)

    def _generate_terrain(self):
        for _ in range(5):
            cx, cy, r = random.randint(0, self.width-1), random.randint(0, self.height-1), random.randint(3, 7)
            for y in range(self.height):
                for x in range(self.width):
                    if Point(x,y).distance_to(Point(cx, cy)) <= r: self.terrain[y][x] = TerrainType.WATER
        if random.random() < 0.5:
            ry = random.randint(self.height // 4, self.height * 3 // 4)
            for x in range(self.width):
                if random.random() > 0.2:
                    self.terrain[ry][x] = TerrainType.WATER
                    if ry + 1 < self.height and random.random() > 0.4: self.terrain[ry+1][x] = TerrainType.WATER
        else:
            rx = random.randint(self.width // 4, self.width * 3 // 4)
            for y in range(self.height):
                 if random.random() > 0.2:
                    self.terrain[y][rx] = TerrainType.WATER
                    if rx + 1 < self.width and random.random() > 0.4: self.terrain[y][rx+1] = TerrainType.WATER

    def _calculate_water_distance_map(self):
        logging.info("Calculating water distance map...")
        self.water_distance_map = [[-1 for _ in range(self.width)] for _ in range(self.height)]
        q = deque()
        for y in range(self.height):
            for x in range(self.width):
                if self.terrain[y][x] == TerrainType.WATER:
                    self.water_distance_map[y][x] = 0
                    q.append((Point(x, y), 0))
        while q:
            pos, dist = q.popleft()
            for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
                next_pos = Point(pos.x + dx, pos.y + dy)
                if 0 <= next_pos.x < self.width and 0 <= next_pos.y < self.height and self.water_distance_map[next_pos.y][next_pos.x] == -1:
                    self.water_distance_map[next_pos.y][next_pos.x] = dist + 1
                    q.append((next_pos, dist + 1))
        logging.info("Water distance map calculation complete.")

    def spawn_resource(self):
        res_type = random.choice(list(ResourceType))
        if res_type in [ResourceType.IRON_INGOT, ResourceType.FISH, ResourceType.MEAT]: return
        pos = self.find_empty_spot_near(Point(self.width//2, self.height//2), max(self.width, self.height)//2)
        if pos: self.add_object(Resource(pos, res_type))
    
    def spawn_resource_near(self, center: Point, res_type: ResourceType, radius: int):
        pos = self.find_empty_spot_near(center, radius)
        if pos: self.add_object(Resource(pos, res_type))

    def spawn_animal(self):
        if len([o for o in self.get_all_objects() if isinstance(o, Deer)]) < MAX_ANIMALS:
            pos = self.find_empty_spot_near(Point(self.width//2, self.height//2), max(self.width, self.height)//2)
            if pos: self.add_object(Deer(pos))
        if len([o for o in self.get_all_objects() if isinstance(o, Wolf)]) < MAX_WOLVES and MAX_WOLVES > 0:
            pos = self.find_empty_spot_near(Point(self.width//2, self.height//2), max(self.width, self.height)//2)
            if pos: self.add_object(Wolf(pos))

    def record_path_usage(self, pos: Point): self.path_usage[pos] += 1

    def _update_roads(self):
        for pos, usage in list(self.path_usage.items()):
            if usage > ROAD_BUILD_THRESHOLD and self.terrain[pos.y][pos.x] == TerrainType.GRASS:
                self.terrain[pos.y][pos.x] = TerrainType.ROAD
            self.path_usage[pos] = int(usage * PATH_DECAY_RATE)
            if self.path_usage[pos] == 0: del self.path_usage[pos]