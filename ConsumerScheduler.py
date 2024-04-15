# Script that schedules entities based on the simulated average duration and power of each entity.
# The average duration and power are calculated using a Monte Carlo simulation.
# The script is intended to be used with the Home Assistant AppDaemon add-on.

from appdaemon.plugins.hass import hassapi as hass
import numpy as np
from datetime import datetime, time, timedelta, date
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
    [1, 2, 3, 4, 5],   # Priority 1 accepts class levels 1 to 5
    [1, 2, 3, 4],      # Priority 2 accepts class levels 1 to 4
    [1, 2, 3],         # Priority 3 accepts class levels 1 to 3
    [1, 2],            # Priority 4 accepts class levels 1 to 2
    [1],               # Priority 5 accepts only class level 1
]

def is_accepted(class_level, acceptance):
    try:
        class_level = int(class_level)
    except ValueError:
        return False

    return class_level in acceptance

class ConsumerScheduler(hass.Hass):

    def sensor_changed(self, entity, attribute, old, new, kwargs):
        # Get the new timeslots from the electricity classification sensor
        self.timeslots = self.get_timeslots(self.electricity_sensor)

        # Extract and display the new available hours for each priority
        self.extract_available_hours()

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

            # Filter out timeslots that are not for today or tomorrow
            today = date.today()
            tomorrow = today + timedelta(days=1)
            timeslots = [ts for ts in timeslots if today.strftime('%Y-%m-%d') in ts or tomorrow.strftime('%Y-%m-%d') in ts]

            return timeslots

        # Log an error if the sensor state format is unexpected
        self.log(f"Unexpected sensor state format: {sensor_state_obj}")
        return []

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
                return None, None

            # Extract the class level from the attributes
            for key, value in sensor_attributes.items():
                if timeslot in key:
                    class_level_str = value
                    break
            else:
                self.log(f"Error: No class level found for timeslot '{timeslot}'")
                return None, None

            # Check if the class level is None or cannot be converted to an integer
            if class_level_str is None:
                return None, None
            try:
                class_level = int(class_level_str.split(" ")[-1])
            except (ValueError, AttributeError):
                self.log(f"Error: Unable to convert class level '{class_level_str}' to integer")
                return None, None

            # Extract the class from the class level string
            class_name = class_level_str.split(":")[0].strip()

            return class_level, class_name

        # Log an error if the sensor state format is unexpected
        self.log(f"Unexpected sensor state format: {sensor_state_obj}")
        return None, None


    def extract_available_hours(self):
        total_hours_per_priority = {priority: 0 for priority in range(1, len(ACCEPTANCE_LEVELS) + 1)}
        timeslots_per_priority = {priority: [] for priority in range(1, len(ACCEPTANCE_LEVELS) + 1)}

        # Display available time slots for each priority level
        for priority, level_spec in enumerate(ACCEPTANCE_LEVELS, start=1):
            available_slots = []
            for t in self.timeslots:
                class_level, class_name = self.get_timeslot_class_level(t)
                if class_level is not None:
                    for r in level_spec:
                        if isinstance(r, int):
                            r = range(r, r+1)
                        if class_level in r:
                            available_slots.append(t)
                            total_hours_per_priority[priority] += self.calculate_timeslot_duration(t)
                            break  # Break the inner loop as soon as we find a match

            if available_slots:
                # Group consecutive hours into a single timeslot, separated by date
                grouped_slots = []
                start_slot = end_slot = available_slots[0]
                for slot in available_slots[1:]:
                    date_str = end_slot.split(' ')[0]
                    if self.calculate_timeslot_duration(f"{date_str} {end_slot.split(' ')[1].split('-')[1]}-{slot.split(' ')[1].split('-')[0]}") == 0:
                        end_slot = slot
                    else:
                        grouped_slots.append(f"{start_slot.split(' ')[0]} {start_slot.split(' ')[1].split('-')[0]}-{end_slot.split(' ')[1].split('-')[1]}")
                        start_slot = end_slot = slot
                end_time = end_slot.split(' ')[1].split('-')[1]
                if end_time == '00:00':
                    end_time = '24:00'
                grouped_slots.append(f"{start_slot.split(' ')[0]} {start_slot.split(' ')[1].split('-')[0]}-{end_time}")

                timeslots_per_priority[priority] = ', '.join(grouped_slots)
            else:
                self.log(f"Priority {priority} - No available time slots.")

        # Set the state of the sensor.consumer_scheduler entity
        self.set_state("sensor.consumer_scheduler", state="on", attributes={f"Priority {p} unit timeslots": slots for p, slots in timeslots_per_priority.items()})

        # Display total available hours per priority
        for priority, total_hours in total_hours_per_priority.items():
            self.log(f"Priority {priority} - Total available hours: {total_hours} hours")
    
    def calculate_timeslot_duration(self, timeslot):
        # Assuming timeslot is in the format 'YYYY-MM-DD HH:mm-HH:mm'
        date_str, time_str = timeslot.split(' ', 1)  # Split at the first space
        start_str, end_str = time_str.split('-', 1)  # Split at the first '-'
        start_time = datetime.strptime(f"{date_str} {start_str}", '%Y-%m-%d %H:%M')
        end_time = datetime.strptime(f"{date_str} {end_str}", '%Y-%m-%d %H:%M')
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
        sensor_data = self.get_state(self.electricity_sensor, attribute="all")
        if isinstance(sensor_data, dict):
            for time_slot, classification in sensor_data['attributes'].items():
                self.log(f"Time Slot: {time_slot}, Classification: {classification}")
        else:
            self.log("Error: sensor_data is not a dictionary")
        
        # Get the timeslots from the electricity classification sensor
        self.timeslots = self.get_timeslots(self.electricity_sensor)

        # Extract and display available hours for each priority
        self.extract_available_hours()

        # Listen for changes in the electricity classification sensor
        self.listen_state(self.sensor_changed, self.electricity_sensor)
