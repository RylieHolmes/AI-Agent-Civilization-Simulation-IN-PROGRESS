from __future__ import annotations
import random
import logging
import math
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Optional, Dict, List, Callable

from utils import Point, AgentRole, AgentState, ResourceType, ToolType, Gender, StructureType, a_star_search, TerrainType, Directive
from config import *

if TYPE_CHECKING:
    from simulation import World

class WorldObject:
    """Base class for anything that exists in the world grid."""
    def __init__(self, pos: Point):
        self.x, self.y = pos.x, pos.y
    @property
    def pos(self) -> Point: return Point(self.x, self.y)
    def set_pos(self, new_pos: Point): self.x, self.y = new_pos.x, new_pos.y

class Resource(WorldObject):
    def __init__(self, pos: Point, resource_type: ResourceType):
        super().__init__(pos)
        self.resource_type = resource_type; self.name = resource_type.resource_name; self.sprite = resource_type.sprite
        self.claimed_by: Optional[Agent] = None

class Tool:
    def __init__(self, tool_type: ToolType):
        self.tool_type = tool_type; self.name = tool_type.tool_name; self.sprite = tool_type.sprite
        self.durability = TOOL_DURABILITY
    def use(self): self.durability -= 1; return self.durability > 0

class Deer(WorldObject):
    def __init__(self, pos: Point):
        super().__init__(pos); self.state_timer = 0; self.target_pos: Optional[Point] = None
        self.move_cooldown = 0; self.health = 20
        self.claimed_by: Optional[Agent] = None

    def update(self, world: 'World'):
        self.state_timer -= 1; self.move_cooldown = max(0, self.move_cooldown - 1)
        if self.state_timer <= 0:
            self.target_pos = Point(self.x + random.randint(-7, 7), self.y + random.randint(-7, 7)) if random.random() < 0.8 else None
            self.state_timer = random.randint(50, 150)
        if self.move_cooldown == 0 and self.target_pos and self.pos != self.target_pos:
            dx = self.target_pos.x - self.x; dy = self.target_pos.y - self.y
            move_x = 1 if dx > 0 else -1 if dx < 0 else 0; move_y = 1 if dy > 0 else -1 if dy < 0 else 0
            next_pos = Point(self.x + move_x, self.y + move_y)
            if world.is_passable(next_pos): world.move_object(self, next_pos); self.move_cooldown = ANIMAL_MOVE_COOLDOWN
            else: self.target_pos = None

class Wolf(WorldObject):
    def __init__(self, pos: Point):
        super().__init__(pos); self.move_cooldown = 0; self.target: Optional[Agent] = None; self.health = 30
    
    def update(self, world: 'World'):
        self.move_cooldown = max(0, self.move_cooldown - 1)
        if self.move_cooldown > 0: return
        if self.target and (self.target.health <= 0 or self.pos.distance_to(self.target.pos) > 10): self.target = None
        if not self.target: self.target = world.find_nearest(self.pos, lambda o: isinstance(o, Agent) and o.is_adult())
        if self.target:
            if self.pos.distance_to(self.target.pos) < 2:
                 self.target.health -= 5
                 if self.target.health <= 0: self.target = None
                 self.move_cooldown = 10
            else:
                dx = self.target.pos.x - self.x; dy = self.target.pos.y - self.y
                move_x = 1 if dx > 0 else -1 if dx < 0 else 0; move_y = 1 if dy > 0 else -1 if dy < 0 else 0
                next_pos = Point(self.x + move_x, self.y + move_y)
                if world.is_passable(next_pos): world.move_object(self, next_pos); self.move_cooldown = ANIMAL_MOVE_COOLDOWN

class Agent(WorldObject):
    def __init__(self, pos: Point, agent_id: int, role: AgentRole, gender: Gender, start_age: int = 0):
        super().__init__(pos); self.agent_id=agent_id; self.role=role; self.gender=gender; self.age=start_age
        self.is_adult_val = self.age >= ADULT_AGE_THRESHOLD; self.energy=AGENT_MAX_ENERGY; self.hydration=AGENT_MAX_HYDRATION
        self.health=AGENT_MAX_HEALTH; self.state=AgentState.IDLE; self.state_timer=0; self.path:List[Point]=[];
        self.target_object:Optional[WorldObject]=None; self.target_pos:Optional[Point]=None; self.on_arrival:Optional[Callable]=None
        self.partner:Optional[Agent]=None; self.home:Optional[Shelter]=None; self.is_pregnant=False; self.pregnancy_timer=0
        self.inventory:Dict[str, int]=defaultdict(int); self.tool:Optional[Tool]=None

    def is_adult(self) -> bool: return self.is_adult_val

    def update(self, world: 'World'):
        self.age += 1
        if not self.is_adult_val and self.age >= ADULT_AGE_THRESHOLD: self.is_adult_val = True; self.state = AgentState.IDLE
        self.energy -= 0.1; self.hydration -= 0.12
        self.state_timer = max(0, self.state_timer - 1)
        if self.health <= 0 or self.energy <= 0 or self.hydration <= 0:
            reason = "health" if self.health<=0 else "energy" if self.energy<=0 else "hydration"
            logging.warning(f"AGENT DEATH: ID {self.agent_id} died from low {reason}.")
            self.release_claim(); world.remove_object(self); return
        if self.state == AgentState.MOVING and not self._execute_move(world):
            arrived = self.on_arrival and ((self.target_object and self.pos.distance_to(self.target_object.pos)<2) or (self.target_pos and self.pos==self.target_pos))
            callback, target = self.on_arrival, self.target_object or self.target_pos
            if not arrived: logging.debug(f"Agent {self.agent_id}: Path failed or target moved. Resetting state.")
            self.reset_task()
            if arrived and callback: callback(world, target)
            else: self.state = AgentState.IDLE; self.state_timer = ACTION_COOLDOWN
        if self.state_timer == 0: self.run_state_machine(world)

    def release_claim(self):
        if self.target_object and hasattr(self.target_object, 'claimed_by') and self.target_object.claimed_by == self:
            self.target_object.claimed_by = None
            
    def reset_task(self):
        self.release_claim()
        self.path, self.target_object, self.target_pos, self.on_arrival = [], None, None, None

    def run_state_machine(self, world: 'World'):
        if self.state == AgentState.MOVING: return
        is_builder = self.role == AgentRole.BUILDER
        has_directive = isinstance(world.oracle.directive.value, StructureType)
        if is_builder and has_directive and self._do_builder_tasks(world): return
        if not self.is_adult(): self._handle_child_state(world); return
        if self.hydration < AGENT_LOW_HYDRATION_THRESHOLD: self._seek_water(world); return
        if self.energy < AGENT_LOW_ENERGY_THRESHOLD: self._seek_food(world); return
        if world.is_night() and self.home: self._go_home_to_rest(world); return
        if not self._perform_role_task(world): self._wander(world)

    def _execute_move(self, world: 'World') -> bool:
        if not self.path: return False
        next_pos = self.path[0]
        if world.is_passable(next_pos, ignore_agents=True) or (len(self.path) == 1 and self.target_object):
            world.record_path_usage(self.pos); world.move_object(self, self.path.pop(0)); self.energy -= 0.5; return bool(self.path)
        else:
            logging.debug(f"Agent {self.agent_id}: Path blocked at {next_pos}. Aborting move."); self.path = []; return False

    def _handle_child_state(self, world: 'World'):
        if not self.home: self.home = world.find_nearest(self.pos, lambda o: isinstance(o, Shelter) and len(o.occupants) < 2)
        if self.home and self.pos.distance_to(self.home.pos) > CHILD_WANDER_RADIUS: self._set_target_pos(world, self.home.pos)
        elif random.random() < 0.1:
            target = Point(self.home.pos.x + random.randint(-CHILD_WANDER_RADIUS, CHILD_WANDER_RADIUS), self.home.pos.y + random.randint(-CHILD_WANDER_RADIUS, CHILD_WANDER_RADIUS))
            self._set_target_pos(world, target)
        else: self.state_timer = random.randint(20, 50)

    def _seek_food(self, world: 'World'):
        self.state = AgentState.SEEKING_FOOD
        food_key = ResourceType.FOOD.resource_name; meat_key = ResourceType.MEAT.resource_name; fish_key = ResourceType.FISH.resource_name
        if self.home and self.home.inventory[food_key] > 0: self._eat_from_storage(world, self.home); return
        if world.global_inventory[food_key] > 0 or world.global_inventory[meat_key] > 0 or world.global_inventory[fish_key] > 0:
            self._eat_from_storage(world, None); return
        self.state_timer = 20

    def _eat_from_storage(self, world: 'World', storage):
        food_key = ResourceType.FOOD.resource_name
        if storage:
            storage.inventory[food_key] -= 1
            self.energy = min(AGENT_MAX_ENERGY, self.energy + ENERGY_PER_FOOD)
            logging.info(f"Agent {self.agent_id}: Ate food from shelter. Energy now {self.energy:.1f}.")
        else:
            for food_type in [ResourceType.FOOD, ResourceType.MEAT, ResourceType.FISH]:
                if world.global_inventory[food_type.resource_name] > 0:
                    world.global_inventory[food_type.resource_name] -= 1
                    self.energy = min(AGENT_MAX_ENERGY, self.energy + ENERGY_PER_FOOD)
                    logging.info(f"Agent {self.agent_id}: Ate {food_type.resource_name}. Energy now {self.energy:.1f}."); break
        self.state = AgentState.IDLE

    def _seek_water(self, world: 'World'):
        self.state = AgentState.SEEKING_WATER
        well = world.find_nearest(self.pos, lambda o: isinstance(o, Well))
        if well: self._set_target_object(world, well, on_arrival=self._drink_water); return
        water_pos = self._find_nearest_water_source(world)
        if water_pos: self._set_target_pos(world, water_pos, on_arrival=self._drink_water); return
        logging.warning(f"Agent {self.agent_id}: Cannot find a water source!"); self.state_timer = 20
        
    def _drink_water(self, world: 'World', target):
        self.hydration = min(AGENT_MAX_HYDRATION, self.hydration + HYDRATION_PER_DRINK)
        logging.info(f"Agent {self.agent_id}: Drank water. Hydration now {self.hydration:.1f}."); self.state = AgentState.IDLE

    def _go_home_to_rest(self, world: 'World'):
        if self.home:
            if self.pos.distance_to(self.home.pos) < 2: self.energy=min(AGENT_MAX_ENERGY, self.energy + 1); self.state_timer = 2
            else: self._set_target_object(world, self.home)
        else: self.state = AgentState.IDLE
    
    def _perform_role_task(self, world: 'World') -> bool:
        if self.role.required_tool and not self.tool: self._get_tool(world); return True
        role_tasks={AgentRole.LUMBERJACK:lambda:self._gather_resource(world,ResourceType.WOOD),
                    AgentRole.MINER:lambda:self._gather_resource(world,random.choice([ResourceType.STONE,ResourceType.IRON_ORE])),
                    AgentRole.BUILDER:lambda:self._do_builder_tasks(world),
                    AgentRole.FARMER:lambda:self._work_at_building(world,Farm,StructureType.FARM),
                    AgentRole.BLACKSMITH:lambda:self._work_at_building(world,Blacksmith,StructureType.BLACKSMITH),
                    AgentRole.HUNTER:lambda:self._hunt_animal(world),
                    AgentRole.FISHERMAN:lambda:self._work_at_building(world,FishingHut,StructureType.FISHING_HUT)}
        task = role_tasks.get(self.role); return task() if task else False

    def _get_tool(self, world: 'World'):
        tool_type = self.role.required_tool
        if world.global_inventory[tool_type.tool_name] > 0:
            world.global_inventory[tool_type.tool_name] -= 1; self.tool = Tool(tool_type)
            logging.info(f"Agent {self.agent_id} took {tool_type.tool_name} from global inventory.")
        else: self.state_timer = 30

    def _gather_resource(self, world: 'World', res_type: ResourceType) -> bool:
        resource = world.find_nearest(self.pos, lambda o: isinstance(o, Resource) and o.resource_type == res_type and o.claimed_by is None)
        if resource: resource.claimed_by = self; self._set_target_object(world, resource, on_arrival=self._harvest_resource); return True
        return False

    def _harvest_resource(self, world: 'World', resource: Resource):
        if resource not in world.get_objects_at(resource.pos): return
        if self.tool and not self.tool.use(): self.tool = None
        world.remove_object(resource); world.global_inventory[resource.name] += 1
        logging.info(f"Agent {self.agent_id}: Harvested {resource.name}, global stock: {world.global_inventory[resource.name]}.")
        self._gather_resource(world, resource.resource_type)

    def _hunt_animal(self, world: 'World') -> bool:
        deer = world.find_nearest(self.pos, lambda o: isinstance(o, Deer) and o.claimed_by is None)
        if deer: deer.claimed_by = self; self._set_target_object(world, deer, on_arrival=self._harvest_animal); return True
        return False

    def _harvest_animal(self, world: 'World', deer: Deer):
        if deer not in world.get_objects_at(deer.pos): return
        world.remove_object(deer); world.global_inventory[ResourceType.MEAT.resource_name] += 5
        logging.info(f"Agent {self.agent_id}: Hunted deer, global meat stock: {world.global_inventory[ResourceType.MEAT.resource_name]}.")
        
    def _do_builder_tasks(self, world: 'World') -> bool:
        site = world.find_nearest(self.pos, lambda o: isinstance(o, ConstructionSite) and o.needed_resources)
        if site:
            needed_res_name = next(iter(site.needed_resources.keys()))
            if self.inventory.get(needed_res_name, 0) > 0:
                self._set_target_object(world, site, on_arrival=self._deliver_to_site); return True
            else:
                if world.global_inventory[needed_res_name] > 0:
                    world.global_inventory[needed_res_name] -= 1; self.inventory[needed_res_name] += 1
                    logging.info(f"Agent {self.agent_id} took {needed_res_name} for construction.")
                    self._set_target_object(world, site, on_arrival=self._deliver_to_site); return True
                else:
                    try:
                        resource_to_gather = next(res for res in ResourceType if res.resource_name == needed_res_name)
                        logging.debug(f"Agent {self.agent_id}: No {needed_res_name} in inventory, will go gather it.")
                        return self._gather_resource(world, resource_to_gather)
                    except StopIteration:
                        logging.warning(f"Agent {self.agent_id}: Needed resource {needed_res_name} is not gatherable. Waiting.")
                        self.state_timer = 30
                        return True
        directive = world.oracle.directive
        if isinstance(directive.value, StructureType):
            structure_to_build = directive.value
            if not any(isinstance(s, ConstructionSite) and s.structure_type == structure_to_build for s in world.get_all_objects()):
                self._build_structure(world, structure_to_build); return True
        return self._gather_resource(world, ResourceType.WOOD)

    def _deliver_to_site(self, world: 'World', site: ConstructionSite):
        for name, amount in self.inventory.items():
            if name in site.needed_resources:
                delivered = min(amount, site.needed_resources[name])
                site.add_resource(name, delivered)
                logging.info(f"Agent {self.agent_id} delivered {delivered} {name} to {site.structure_type.name} site.")
        self.inventory.clear()
        if site.is_complete:
            self.state_timer = ACTION_COOLDOWN * 2
            logging.info(f"Site at {site.pos} is now complete!")

    def _build_structure(self, world: 'World', structure_type: StructureType):
        world_center = Point(world.width // 2, world.height // 2); pos = None
        if structure_type == StructureType.FISHING_HUT:
            logging.debug("Using specialized terrain search for Fishing Hut.")
            pos = world.find_spot_near_terrain(world_center, 40, TerrainType.WATER, check_path_from=self.pos)
        else:
            pos = world.find_empty_spot_near(world_center, 40, for_building=True, check_path_from=self.pos)
        if pos: 
            logging.info(f"Agent {self.agent_id}: Found a spot at {pos}. Creating construction site.")
            world.create_construction_site(pos, structure_type)
        else:
            logging.error(f"Agent {self.agent_id}: CRITICAL - Could not find any reachable location to build {structure_type.name}.")
            # --- MODIFIED: This is the critical fix for the "obsession" loop. ---
            # If a builder fails to find a spot, force it to wait before trying again.
            self.state_timer = 50 

    def _work_at_building(self, world: 'World', building_class: type, structure_type: StructureType) -> bool:
        building = world.find_nearest(self.pos, lambda o: isinstance(o, building_class) and not o.worker)
        if building: self._set_target_object(world, building, on_arrival=self._arrive_at_workplace); return True
        if self.role == AgentRole.BUILDER: self._build_structure(world, structure_type); return True
        return False

    def _arrive_at_workplace(self, world: 'World', building):
        building.set_worker(self); self.state = AgentState.WORKING
        logging.info(f"Agent {self.agent_id} has started working at {building.__class__.__name__}.")
        
    def _wander(self, world: 'World'):
        if random.random() < 0.05:
            target = Point(self.x + random.randint(-5, 5), self.y + random.randint(-5, 5))
            self._set_target_pos(world, target)
        else: self.state_timer = 20

    def _set_target_object(self, world: 'World', target: WorldObject, on_arrival: Optional[Callable] = None):
        if self.pos.distance_to(target.pos) < 2:
            if on_arrival: self.reset_task(); on_arrival(world, target)
            return
        path = a_star_search(world, self.pos, target.pos)
        if path: 
            self.reset_task()
            self.path, self.target_object, self.state, self.on_arrival = path, target, AgentState.MOVING, on_arrival
        else: 
            logging.warning(f"Agent {self.agent_id}: Could not find path to {target.__class__.__name__} at {target.pos}.")
            if isinstance(target, ConstructionSite):
                target.failed_path_attempts += 1
                logging.warning(f"Agent {self.agent_id}: Incremented failure count for site at {target.pos} to {target.failed_path_attempts}.")
            self.reset_task(); self.state_timer = 10

    def _set_target_pos(self, world: 'World', target_pos: Point, on_arrival: Optional[Callable] = None):
        path = a_star_search(world, self.pos, target_pos)
        if path: self.reset_task(); self.path, self.target_pos, self.state, self.on_arrival = path, target_pos, AgentState.MOVING, on_arrival
        else: self.state_timer = 10

    def _find_nearest_water_source(self, world: 'World') -> Optional[Point]:
        if not world.water_distance_map: return None
        best_pos, min_dist = None, float('inf')
        for dx, dy in [(-1,0), (1,0), (0,-1), (0,1)]:
            check_pos = Point(self.x + dx, self.y + dy)
            if 0 <= check_pos.x < world.width and 0 <= check_pos.y < world.height:
                dist = world.water_distance_map[check_pos.y][check_pos.x]
                if dist < min_dist: min_dist, best_pos = dist, check_pos
        return best_pos
        
class Storage(WorldObject):
    def __init__(self, pos: Point, capacity: int = 10):
        super().__init__(pos); self.inventory = defaultdict(int); self.capacity = capacity
    def has_space(self) -> bool: return sum(self.inventory.values()) < self.capacity
    def add_item(self, name: str, amount: int): self.inventory[name] += amount
    def remove_item(self, name: str, amount: int): self.inventory[name] -= amount; self.inventory = defaultdict(int, {k:v for k,v in self.inventory.items() if v>0})
    
class Shelter(Storage):
    def __init__(self, pos: Point):
        super().__init__(pos); self.occupants: List[Agent] = []
    def add_occupant(self, agent: Agent):
        if agent not in self.occupants: self.occupants.append(agent)
    def remove_occupant(self, agent: Agent):
        if agent in self.occupants: self.occupants.remove(agent)

class ProductionBuilding(WorldObject):
    def __init__(self, pos: Point):
        super().__init__(pos); self.worker: Optional[Agent] = None; self.production_progress = 0
    def set_worker(self, agent: Agent): self.worker = agent
    def remove_worker(self): self.worker = None
    def update(self, world: 'World'):
        if self.worker and (self.worker.pos.distance_to(self.pos) > 2 or self.worker.state not in [AgentState.WORKING, AgentState.MOVING]):
            self.remove_worker()

class Farm(ProductionBuilding):
    def update(self, world: 'World'):
        super().update(world)
        if self.worker and not world.is_night():
            self.production_progress += 1
            if self.production_progress >= FARM_PRODUCTION_CYCLE:
                self.production_progress = 0; world.global_inventory[ResourceType.FOOD.resource_name] += 5
                logging.info(f"Farm at ({self.pos.x},{self.pos.y}) produced 5 food.")

class LumberMill(ProductionBuilding): pass
class Mine(ProductionBuilding): pass
class Well(WorldObject): pass
class FishingHut(ProductionBuilding):
     def update(self, world: 'World'):
        super().update(world)
        if self.worker and self._is_near_water(world):
            self.production_progress += 1
            if self.production_progress >= 100:
                self.production_progress = 0; world.global_inventory[ResourceType.FISH.resource_name] += 2
                logging.info(f"Fishing Hut at ({self.pos.x},{self.pos.y}) produced 2 fish.")
     def _is_near_water(self, world: 'World'):
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            p = Point(self.x+dx, self.y+dy)
            if 0<=p.x<world.width and 0<=p.y<world.height and world.terrain[p.y][p.x]==TerrainType.WATER: return True
        return False

class HuntersLodge(ProductionBuilding): pass

class Blacksmith(ProductionBuilding):
    def update(self, world: 'World'):
        super().update(world)
        if not self.worker: return
        iron_ore_key = ResourceType.IRON_ORE.resource_name; iron_ingot_key = ResourceType.IRON_INGOT.resource_name; wood_key = ResourceType.WOOD.resource_name
        if world.global_inventory[iron_ore_key] > 0:
            self.production_progress += 1
            if self.production_progress >= BLACKSMITH_SMELT_TIME:
                self.production_progress = 0; world.global_inventory[iron_ore_key] -= 1; world.global_inventory[iron_ingot_key] += 1
                logging.info(f"Blacksmith smelted 1 Iron Ingot.")
        elif world.global_inventory[iron_ingot_key] >= 3 and world.global_inventory[wood_key] >= 1:
            self.production_progress += 1
            if self.production_progress >= BLACKSMITH_CRAFT_TIME:
                self.production_progress = 0
                tool = random.choice([ToolType.AXE, ToolType.PICKAXE])
                can_craft = all(world.global_inventory[res] >= amt for res, amt in tool.recipe.items())
                if can_craft:
                    for res, amt in tool.recipe.items(): world.global_inventory[res] -= amt
                    world.global_inventory[tool.tool_name] += 1
                    logging.info(f"Blacksmith at ({self.pos.x},{self.pos.y}) crafted 1 {tool.tool_name}.")

class ConstructionSite(WorldObject):
    def __init__(self, pos: Point, structure_type: StructureType):
        super().__init__(pos)
        self.structure_type = structure_type
        self.needed_resources = defaultdict(int, structure_type.recipe)
        self.is_complete = not self.needed_resources
        self.failed_path_attempts = 0
        
    def add_resource(self, name: str, amount: int):
        self.needed_resources[name] -= amount
        if self.needed_resources[name] <= 0: del self.needed_resources[name]
        if not self.needed_resources: self.is_complete = True