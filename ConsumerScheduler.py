# Script that schedules entities based on the simulated average duration and power of each entity.
# The average duration and power are calculated using a Monte Carlo simulation.
# The script is intended to be used with the Home Assistant AppDaemon add-on.

from appdaemon.plugins.hass import hassapi as hass
import numpy as np
from datetime import datetime, time, timedelta
import json

# Magic Words
AMPS_PER_FUSE = 16  # in amps
MAX_PHASE_POWER = 230 * AMPS_PER_FUSE  # in watts
MAX_POWER_LIMIT = 11000  # Set your desired maximum power limit in watts
PHASES = 3
NUM_TRIALS_MONTE_CARLO = 1000

# Define acceptance levels for each priority, 1..7 (1 is lowest, 7 is highest)
# Acceptance level 1..5 means that the entity can be scheduled in timeslots with priority 1..5
ACCEPTANCE_LEVELS = [
    range(1, 6),   # Priority 1 accepts class level 1 to 5
    range(1, 4),   # Priority 2 accepts class level 1 to 3
    range(1, 3),   # Priority 3 accepts class level 1 to 2
    (1, 2),        # Priority 4 accepts class level 1
    range(1, 2),   # Priority 5 accepts class level 1
]

def is_accepted(class_level, acceptance):
    if isinstance(acceptance, range):
        return class_level in acceptance
    elif isinstance(acceptance, tuple):
        start, end = acceptance
        return start <= class_level <= end
    return False

class ConsumerScheduler(hass.Hass):

    def extract_available_hours(self):
        # Display available time slots for each priority level
        for priority, level_spec in enumerate(ACCEPTANCE_LEVELS, start=1):
            available_slots = []
            for t in self.timeslots:
                class_level = self.get_timeslot_class_level(t)
                if class_level and any(is_accepted(class_level, r) for r in level_spec):
                    available_slots.append(t)
            if available_slots:
                self.log(f"Priority {priority} - Available time slots: {available_slots}")
            else:
                self.log(f"Priority {priority} - No available time slots.")


    def get_timeslots(self, electricity_sensor):
        # Retrieve the sensor state object
        sensor_state_obj = self.get_state(electricity_sensor, attribute="all")

        # Log the sensor name
        self.log(f"Getting timeslots for sensor: {electricity_sensor}")

        # Check if sensor_state_obj is None
        if sensor_state_obj is None:
            self.log("Error: sensor_state_obj is None")
            return []

        # Check if sensor_state_obj is a dictionary
        if isinstance(sensor_state_obj, dict):
            # Log the received sensor state object
            self.log(f"Received sensor state object: {sensor_state_obj}")

            # Try to extract the attributes from the sensor state object
            try:
                sensor_attributes = sensor_state_obj['attributes']
            except KeyError:
                self.log("Error: sensor_state_obj does not contain 'attributes'")
                return []

            # Extract the timeslots from the attributes
            timeslots = list(sensor_attributes.keys())

            # Log the extracted timeslots for debugging
            self.log(f"Extracted timeslots: {timeslots}")

            return timeslots

        # Log an error if the sensor state format is unexpected
        self.log(f"Unexpected sensor state format: {sensor_state_obj}")
        return []

        # Log an error if the sensor state format is unexpected
        self.log(f"Unexpected sensor state format: {sensor_state_str}")
        return []

        # Log the extracted timeslot for debugging
        self.log(f"Extracted timeslot: {timeslot}")

        return [timeslot]

        try:
            # Convert the string representation of JSON data to a dictionary
            sensor_state = json.loads(sensor_state_str)

            # Log the decoded sensor state for debugging
            self.log(f"Decoded sensor state: {sensor_state}")
        except json.JSONDecodeError as e:
            # Log the error and return an empty list
            self.log(f"Error decoding JSON: {e}")
            return []

        # Additional logging to check sensor_state structure
        self.log(f"Sensor state structure: {sensor_state}")

        timeslots = []

        for timeslot, class_level in sensor_state.items():
            try:
                # Extract the timeslot from the string
                timeslot_str = timeslot.split(":")[1].strip()  # Fixed the index here
                timeslots.append(timeslot_str)
            except IndexError:
                self.log(f"Error extracting timeslot from the sensor state: {timeslot}")

        return timeslots
    
    def get_timeslot_class_level(self, timeslot):
        # Retrieve the sensor state object
        sensor_state_obj = self.get_state(self.electricity_sensor, attribute="all")

        # Check if sensor_state_obj is a dictionary
        if isinstance(sensor_state_obj, dict):
            # Try to extract the attributes from the sensor state object
            try:
                sensor_attributes = sensor_state_obj['attributes']
            except KeyError:
                self.log("Error: sensor_state_obj does not contain 'attributes'")
                return None

            # Extract the class level from the attributes using the timeslot as the key
            class_level_str = sensor_attributes.get(timeslot)

            # Try to convert the class level to an integer
            try:
                class_level = int(class_level_str.split(" ")[-1])
            except (ValueError, AttributeError):
                self.log(f"Error: Unable to convert class level '{class_level_str}' to integer")
                return None

            return class_level

        # Log an error if the sensor state format is unexpected
        self.log(f"Unexpected sensor state format: {sensor_state_obj}")
        return None


    def extract_available_hours(self):
        total_hours_per_priority = {priority: 0 for priority in range(1, len(ACCEPTANCE_LEVELS) + 1)}

        # Display available time slots for each priority level
        for priority, level_spec in enumerate(ACCEPTANCE_LEVELS, start=1):
            available_slots = []
            if isinstance(level_spec, int):
                level_spec = [level_spec]  # Convert the integer to a list
            for t in self.timeslots:
                if isinstance(self.get_timeslot_class_level(t), int) and self.get_timeslot_class_level(t) in level_spec:
                    available_slots.append(t)
                    total_hours_per_priority[priority] += self.calculate_timeslot_duration(t)

            if available_slots:
                self.log(f"Priority {priority} - Available time slots: {available_slots}")
            else:
                self.log(f"Priority {priority} - No available time slots.")

        # Display total available hours per priority
        for priority, total_hours in total_hours_per_priority.items():
            self.log(f"Priority {priority} - Total available hours: {total_hours} hours")

    def calculate_timeslot_duration(self, timeslot):
        # Assuming timeslot is in the format 'YYYYMMDD HH:mm-HH:mm'
        start_str, end_str = timeslot.split(' ')[1].split('-')
        start_time = datetime.strptime(start_str, '%H:%M')
        end_time = datetime.strptime(end_str, '%H:%M')
        duration = (end_time - start_time).total_seconds()
        if duration < 0:
            # If the duration is negative, add 24 hours to it (convert to next day)
            duration += 24 * 3600
        return duration / 3600  # Convert seconds to hours

    def initialize(self):
        # Entities configuration
        self.entities = {
            'entity1': {'range': (1, 10), 'priority': int(1), 'power': (1000, 11000), 'phases': [1, 2, 3]},
            'entity2': {'range': (2, 3.5), 'priority': int(2), 'power': (1000, 9000), 'phases': [2]},
            'entity3': {'range': (0.5, 2), 'priority': int(3), 'power': (500, 2000), 'phases': [1]},
            'entity4': {'range': (0.5, 6), 'priority': int(4), 'power': (500, 1200), 'phases': [3]},
        }

        # Get the electricity classification sensor entity
        self.electricity_sensor = 'sensor.electricity_twoday_classification'

        # Get the timeslots from the electricity classification sensor
        self.timeslots = self.get_timeslots(self.electricity_sensor)

        # Extract and display available hours for each priority
        self.extract_available_hours()
