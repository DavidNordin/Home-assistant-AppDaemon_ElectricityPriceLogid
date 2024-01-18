# Script that schedules entities based on the simulated average duration of each entity.
# The average duration is calculated using a Monte Carlo simulation.
# The script is intended to be used with the Home Assistant AppDaemon add-on.
#   
# and the current power consumption per phase.
#

from appdaemon.plugins.hass import hassapi as hass
import numpy as np
import threading
from datetime import datetime, time, timedelta

# Magic Words
MAX_POWER_LIMIT = 11000  # in watts
AMPS_PER_FUSE = 16  # in amps
NUM_TRIALS_MONTE_CARLO = 1000
SLEEP_INTERVAL_SECONDS = 5

class ConsumerScheduler(hass.Hass):

    def initialize(self):
        # Define the entities and their estimated Monte Carlo ranges
        self.entities = {
            'entity1': (1, 8),  # estimated range for entity1
            'entity2': (2, 3.5),  # estimated range for entity2
            # Add more entities and their ranges as needed
        }

        # Get the electricity classification sensor entity
        self.electricity_sensor = 'sensor.electricity_twoday_classification'

        # Get the current power consumption and current consumption per phase
        self.update_sensor_values()

        # Get the timeslots from the electricity classification sensor
        self.timeslots = self.get_timeslots(self.electricity_sensor)

        # Dictionary to store the average duration for each entity
        self.average_durations = {}

        for entity, (min_range, max_range) in self.entities.items():
            # Array to store the durations for each trial
            durations = np.zeros(NUM_TRIALS_MONTE_CARLO)

            for trial in range(NUM_TRIALS_MONTE_CARLO):
                # Generate a random duration for this trial
                durations[trial] = np.random.uniform(min_range, max_range)

            # Calculate the average duration for this entity
            self.average_durations[entity] = np.mean(durations)

        # Schedule entities based on average durations from Monte Carlo simulation
        self.schedule_entities()

        # Start a new thread that updates the sensor values every few seconds
        threading.Thread(target=self.update_sensor_values_loop, daemon=True).start()

    def update_sensor_values(self):
        # Get the current power consumption
        self.total_power = self.get_sensor_value('sensor.power_abilds_ry_santetorp_106')

        # Get the current current consumption per phase
        self.current_l1 = self.get_sensor_value('sensor.current_l1_abilds_ry_santetorp_106')
        self.current_l2 = self.get_sensor_value('sensor.current_l2_abilds_ry_santetorp_106')
        self.current_l3 = self.get_sensor_value('sensor.current_l3_abilds_ry_santetorp_106')

    def update_sensor_values_loop(self):
        while True:
            self.update_sensor_values()
            # Sleep for a few seconds
            time.sleep(SLEEP_INTERVAL_SECONDS)

def schedule_entities(self):
    # Calculate the total available amps based on the fuse limit
    total_available_amps = self.amps_per_fuse * len(self.entities)

    # Calculate the maximum power that can be used at any given time
    max_power = min(self.max_power_limit, total_available_amps * 230)  # assuming 230V power supply

    # Count the number of available timeslots
    available_timeslots = 0

    # Schedule each entity based on its average duration and priority
    for entity, average_duration in self.average_durations.items():
        priority = self.get_entity_priority(entity)

        # Check if the scheduled entity exceeds the maximum power limit
        if average_duration * max_power > self.max_power_limit:
            self.log(f"Entity '{entity}' exceeds the maximum power limit.")

        # Determine the allowed priority levels for this entity
        allowed_priorities = range(priority, 6)

        # Generate a random start time within the available timeslots and allowed priority levels
        start_timeslot = np.random.choice([t for t in self.timeslots if self.get_timeslot_priority(t) in allowed_priorities])
        start_time = start_timeslot * (24 / len(self.timeslots))

        end_time = start_time + average_duration

        # Schedule the entity to start and stop within the calculated timeslots
        self.run_daily(self.start_entity, start_time, entity=entity)
        self.run_daily(self.stop_entity, end_time, entity=entity)

def get_entity_priority(self, entity):
    # Implement logic to get the priority level for the specified entity
    # Example: return 1, 2, or 3 based on your classification rules
    pass

def get_timeslot_priority(self, timeslot):
    # Implement logic to get the priority level for the specified timeslot
    # Example: return 1, 2, or 3 based on your classification rules
    pass

def get_sensor_value(self, entity):
    # Implement logic to get the sensor value from Home Assistant
    # Example: return self.get_state(entity)
    pass

def get_timeslots(self, electricity_sensor):
    # Implement logic to get timeslots from the electricity classification sensor
    # Example: return some_list_of_timeslots
    pass

def start_entity(self, kwargs):
    # Implement logic to start the specified entity
    # Example: self.turn_on(kwargs['entity'])
    pass

def stop_entity(self, kwargs):
    # Implement logic to stop the specified entity
    # Example: self.turn_off(kwargs['entity'])
    pass