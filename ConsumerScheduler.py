# Script that schedules entities based on the simulated average duration and power of each entity.
# The average duration and power are calculated using a Monte Carlo simulation.
# The script is intended to be used with the Home Assistant AppDaemon add-on.

from appdaemon.plugins.hass import hassapi as hass
import numpy as np
from datetime import datetime, time, timedelta

# Magic Words
AMPS_PER_FUSE = 16  # in amps
MAX_PHASE_POWER = 230 * AMPS_PER_FUSE  # in watts
MAX_POWER_LIMIT = 11000  # Set your desired maximum power limit in watts
PHASES = 3
NUM_TRIALS_MONTE_CARLO = 1000

# Define acceptance levels for each priority, 1..7 (1 is lowest, 7 is highest)
# Acceptance level 1..5 means that the entity can be scheduled in timeslots with priority 1..5
ACCEPTANCE_LEVELS = [
    (1, 5),   # Priority 1 accepts class level 5 and below
    (2, 3),   # Priority 2 accepts class level 3 and below
    (3, 2),   # Priority 3 accepts class level 2 and below
    (4, 1),   # Priority 4 accepts class level 1
    (5, 1),   # Priority 5 accepts class level 1
]

class ConsumerScheduler(hass.Hass):

    def initialize(self):
        # Entities configuration
        self.entities = {
            'entity1': {'range': (1, 10), 'priority': 1, 'power': (1000, 11000), 'phases': [1, 2, 3]},  # Ex. Car-charger
            'entity2': {'range': (2, 3.5), 'priority': 2, 'power': (1000, 9000), 'phases': [2]},  # Ex. heatpump
            'entity3': {'range': (0.5, 2), 'priority': 3, 'power': (500, 2000), 'phases': [1]},  # Ex. washing machine
            'entity4': {'range': (0.5, 6), 'priority': 4, 'power': (500, 1200), 'phases': [3]},  # Ex. dishwasher
        }

        # Get the electricity classification sensor entity
        self.electricity_sensor = 'sensor.electricity_twoday_classification'

        # Get the timeslots from the electricity classification sensor
        self.timeslots = self.get_timeslots(self.electricity_sensor)

        # Initialize phase power dictionary
        self.phase_power = {phase: 0 for phase in range(1, PHASES + 1)}

        # Schedule entities based on average durations and powers from Monte Carlo simulation
        self.schedule_entities()

        # Display available time slots and estimated end times
        self.display_schedule_info()

    def check_phase_power_limit(self, entity_info):
        # Check if adding the entity to any of its specified phases exceeds the phase power limit
        for phase in entity_info['phases']:
            max_phase_power_limit = MAX_POWER_LIMIT / len(entity_info['phases'])
            if (self.phase_power[phase] + entity_info['power'][1] / len(entity_info['phases'])) > max_phase_power_limit:
                return False
        return True

    def schedule_entities(self):
        # Sort entities by priority in descending order
        sorted_entities = sorted(self.entities.items(), key=lambda x: x[1]['priority'], reverse=True)

        # Initialize the expected end time to the current time in minutes
        expected_end_time = self.datetime().hour * 60 + self.datetime().minute

        for entity, entity_info in sorted_entities:
            # Add debug log to print assigned priority for each entity
            self.log(f"Entity: {entity}, Assigned Priority: {entity_info['priority']}")
            # Add debug log to print when scheduling starts for a specific entity
            self.log(f"Starting schedule_entities for {entity}")

            # Calculate the expected end time for this entity in minutes
            expected_end_time = max(expected_end_time, datetime.now().hour * 60 + datetime.now().minute)

            # Convert expected_end_time to HH:MM format for logging
            hours, minutes = divmod(expected_end_time, 60)
            expected_end_time_formatted = f"{int(hours)}:{int(minutes):02d}"
            self.log(f"Expected End Time: {expected_end_time_formatted}")

            # Check if the scheduled entity exceeds the maximum power limit
            if entity_info['power'][1] > MAX_POWER_LIMIT or not self.check_phase_power_limit(entity_info):
                self.log(f"Entity '{entity}' exceeds the maximum power limit or phase power limit.")
                continue

            # Determine the allowed class levels for this entity
            allowed_class_levels = range(ACCEPTANCE_LEVELS[entity_info['priority'] - 1][1], 0, -1)

            # Find the next available timeslot after the expected end time
            available_timeslots = [t for t in self.timeslots if
                                   self.get_timeslot_class_level(t) in allowed_class_levels and t >= expected_end_time]

            if not available_timeslots:
                # No available timeslots, log and skip scheduling
                self.log(f"No available timeslots for {entity} after {expected_end_time_formatted}")
                continue

            # Calculate the average duration
            start_timeslot = min(available_timeslots)
            end_time = start_timeslot + (entity_info['range'][0] + entity_info['range'][1]) / 2  # Calculate the end time

            # Calculate the average power
            average_power = (entity_info['power'][0] + entity_info['power'][1]) / 2

            # Update phase power dictionary with the scheduled entity's power
            for phase in entity_info['phases']:
                self.phase_power[phase] += average_power

            # Convert to time objects
            start_time = time(int(start_timeslot), int((start_timeslot % 1) * 60))
            end_time = time(int(end_time), int((end_time % 1) * 60))

            # Log additional start and stop times for debugging
            self.log(f"Scheduling {entity}, Start Time: {start_time}, End Time: {end_time}")

            self.run_daily(self.start_entity, start_time, entity=entity, priority=entity_info['priority'])
            self.run_daily(self.stop_entity, end_time, entity=entity, priority=entity_info['priority'])

            # Log start and stop times for debugging
            self.log(f"Scheduled {entity} to start at {start_time.strftime('%H:%M')} and stop at {end_time.strftime('%H:%M')}")

            # Update the expected end time for the next iteration
            expected_end_time = max(expected_end_time, (datetime.now().hour * 60) + datetime.now().minute)
            expected_end_time = round(expected_end_time, 0)  # Round to the nearest integer
            # Convert expected_end_time to HH:MM format
            expected_end_time_formatted = f"{int(expected_end_time)}:{int((expected_end_time % 1) * 60):02}"
            self.log(f"Expected End Time: {expected_end_time_formatted}")

    def get_timeslot_class_level(self, timeslot):
        try:
            # Extract the class level from the timeslot name
            class_level = int(timeslot.split()[-1])

            # Log class extracted from timeslot for debugging
            self.log(f"Class level extracted from timeslot: {class_level}")

            # Add additional logging
            self.log(f"Current day timeslots: {self.timeslots}")

            return class_level
        except (ValueError, IndexError):
            # Log an error if extraction fails and decide what to do
            self.log(f"Error extracting class level from timeslot: {timeslot}")
            return None  # or raise an exception, or use a default class level

    def get_timeslots(self, electricity_sensor):
        # Retrieve the sensor attribute
        sensor_state = self.get_state(electricity_sensor)

        # Log the sensor name
        self.log(f"Getting timeslots for sensor: {electricity_sensor}")

        # Check if sensor_state is None
        if sensor_state is None:
            self.log("Error: sensor_state is None")
            return []

        # Check if sensor_state is not a dictionary
        if not isinstance(sensor_state, dict):
            self.log(f"Error: sensor_state is not a dictionary, but {type(sensor_state)}")
            return []

        # Initialize an empty list to store the timeslots
        timeslots = []

        # For each item in the sensor_state dictionary
        for timeslot, class_level in sensor_state.items():
            # Add the timeslot to the timeslots list if the class level is in the allowed class levels
            if 'Class' in class_level:
                timeslots.append(timeslot)

        return timeslots

    def display_schedule_info(self):
        # Display available time slots for each priority level
        for priority, level in ACCEPTANCE_LEVELS:
            available_slots = [t for t in self.timeslots if self.get_timeslot_class_level(t) <= level]
            if available_slots:
                self.log(f"Priority {priority} - Available time slots: {available_slots}")
            else:
                self.log(f"Priority {priority} - No available time slots.")

        # Display estimated end times for each entity
        for entity, entity_info in self.entities.items():
            if entity_info['power'][1] > MAX_POWER_LIMIT or not self.check_phase_power_limit(entity_info):
                self.log(f"Entity '{entity}' exceeds the maximum power limit or phase power limit.")
                continue

            allowed_class_levels = range(ACCEPTANCE_LEVELS[entity_info['priority'] - 1][1], 0, -1)
            available_timeslots = [t for t in self.timeslots if
                                   self.get_timeslot_class_level(t) in allowed_class_levels]

            if not available_timeslots:
                self.log(f"No available timeslots for {entity}")
                continue

            start_timeslot = min(available_timeslots)
            end_time = start_timeslot + (entity_info['range'][0] + entity_info['range'][1]) / 2
            estimated_end_time = max(expected_end_time, (datetime.now().hour * 60) + datetime.now().minute)
            estimated_end_time_formatted = f"{int(estimated_end_time)}:{int((estimated_end_time % 1) * 60):02}"
            self.log(f"Estimated end time for {entity}: {estimated_end_time.strftime('%H:%M')}")
