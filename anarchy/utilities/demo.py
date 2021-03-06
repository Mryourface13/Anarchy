from dataclasses import dataclass
from typing import List

import numpy as np
from scipy.optimize import curve_fit
from rlbot.utils.structures.game_data_struct import GameTickPacket, PlayerInfo as Car
from rlbot.agents.base_agent import BaseAgent

from utilities.vectors import *


max_time = 3.5
dt = 1 / 30
render_dt = 1 / 5
polynomial_degree = 3


@dataclass
class Slice:
    time: float
    position: Vector3


def displacement(x, b, c, d, e): return (x ** 3) * b + (x ** 2) * c + x * d + e
def displacement_curve(x, curve): return displacement(x, curve[0], curve[1], curve[2], curve[3])


class Demolition:
    def __init__(self, agent: BaseAgent, victim_index: int):
        self.agent = agent
        self.victim_index = victim_index
        self.positions: List[Slice] = [] # Keeps track of the victim's position (and time!)

    def get_destination(self, packet: GameTickPacket):
        my_car_location = Vector3(packet.game_cars[self.agent.index].physics.location)
        victim = packet.game_cars[self.victim_index]
        if not Demolition.is_valid_victim(self.agent, victim): return None, 0
        time_now = packet.game_info.seconds_elapsed
        
        self.positions.append(Slice(time = time_now, position = Vector3(victim.physics.location)))
        self.limit_data_time(max(dt * (polynomial_degree + 1), 0.35))

        # Fit the curves
        data_x, data_y, data_z, data_t = self.get_data()
        popt_x, popt_y, popt_z = (curve_fit(displacement, data_t, data_x)[0], curve_fit(displacement, data_t, data_y)[0], curve_fit(displacement, data_t, data_z)[0])

        destination = None
        victim_locations = []
        t = time_now + dt
        while t < time_now + max_time:
            victim_locations.append(Vector3(displacement_curve(t, popt_x), displacement_curve(t, popt_y), displacement_curve(t, popt_z)))
            if ((victim_locations[len(victim_locations) - 1] - my_car_location).length - 50) / (t - time_now) < 2200:
                destination = victim_locations[len(victim_locations) - 1]
                break
            t += dt

        # Render
        if destination is not None:
            self.agent.renderer.begin_rendering(Demolition.get_render_name(self.agent))
            if len(victim_locations) > 1: self.agent.renderer.draw_polyline_3d([victim_locations[i] for i in np.linspace(0, len(victim_locations) - 1, len(victim_locations) / int(render_dt / dt)).astype(int)], self.agent.renderer.orange())
            self.agent.renderer.draw_string_3d(destination, 1, 1, str(round(t - time_now, 2)) + "s", self.agent.renderer.yellow())
            self.agent.renderer.end_rendering()
            return destination, t - time_now
        return None, 0

    @staticmethod
    def get_render_name(agent: BaseAgent):
        return 'Demo (' + agent.name + ')'

    def get_data(self):
        return ([p.position.x for p in self.positions], [p.position.y for p in self.positions], [p.position.z for p in self.positions], [p.time for p in self.positions])

    def limit_data_time(self, max_time: float):
        while True:
            if self.positions[len(self.positions) - 1].time - self.positions[0].time > max_time:
                del self.positions[0]
            else: return

    @staticmethod
    def start_demo(agent: BaseAgent, packet: GameTickPacket):
        # Get the tastiest victim (aka slowest)
        victim_index: int = -1
        slowest_vel: float = 0
        for index, car in enumerate(packet.game_cars[:packet.num_cars]):
            if not Demolition.is_valid_victim(agent, car): continue
            velocity = Vector3(car.physics.velocity).length
            if victim_index == -1 or velocity < slowest_vel:
                victim_index = index
                slowest_vel = velocity

        if victim_index == -1: return None
        return Demolition(agent, victim_index)

    @staticmethod
    def is_valid_victim(agent: BaseAgent, car: Car):
        return car.team != agent.team and not car.is_demolished
