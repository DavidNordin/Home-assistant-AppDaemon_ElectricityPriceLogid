import hassapi as hass
from datetime import datetime, timedelta
import numpy as np

class hvacControl(hass.Hass):
    def initialize(self):
        self.calculate_adjustment(skip_state_check=True)
        self.run_in(self.start_run_every_15, 1)  # Start run_every_15 after 1 second
        self.run_in(self.start_run_every, 1)  # Start run_every after 1 second
        self.listen_state(self.calculate_classification_adjustment, "sensor.electricity_twoday_classification")
        self.calculate_classification_adjustment(skip_state_check=True)

    def start_run_every_15(self, kwargs):
        self.log("start_run_every_15 called")  # Log when the method is called
        now = datetime.now()
        minutes = (now.minute // 15 + 1) * 15
        if minutes >= 60:
            minutes = 0
        start_time = now.replace(minute=minutes, second=0, microsecond=0)
        if minutes == 0:
            start_time += timedelta(hours=1)
        self.run_every(self.update_weighed_price_range, start_time, 15*60)  # Run every 15 minutes
        self.log("update_weighed_price_range scheduled")  # Log when the scheduling is done

    def start_run_every(self, kwargs):
        now = datetime.now()
        minutes = (now.minute // 5 + 1) * 5
        if minutes >= 60:
            minutes = 0
        start_time = now.replace(minute=minutes, second=0, microsecond=0)
        if minutes == 0:
            start_time += timedelta(hours=1)
        self.run_every(self.calculate_adjustment, start_time, 5*60)  # Run every 5 minutes

    def calculate_adjustment(self, entity=None, attribute=None, old=None, new=None, kwargs=None, skip_state_check=False, now=None):
        prices_today = self.get_state("sensor.nordpool_kwh_se4_sek_3_10_025", attribute="today")
        current_price = self.get_state("sensor.nordpool_kwh_se4_sek_3_10_025", attribute="current_price")
        
        if not prices_today or current_price is None:  # Check if the list is empty or current_price is None
            self.log("No data available for today or current price. Using default values for adjustment calculation.")
            current_price = 0
            lowest_price = 0
            highest_price = 1
        else:
            prices_sorted = sorted(prices_today)
            lowest_price = min(prices_sorted)
            highest_price = max(prices_sorted)

        # Calculate the adjustment percentage linearly from the absolute highest price to the absolute lowest price
        # Adjust the range from +100% to -100%
        adjustment_percentage = round(((highest_price - current_price) / (highest_price - lowest_price)) * 200 - 100)

        self.log(f"Current price: {current_price}, Lowest price: {lowest_price}, Highest price: {highest_price}, Adjustment percentage: {adjustment_percentage}")

        self.set_state("sensor.electricity_PriceOptSignal", state=adjustment_percentage, attributes={"unit_of_measurement": "%"})
        
        self.log(f"Updated state: {self.get_state('sensor.electricity_PriceOptSignal')}")

    def calculate_classification_adjustment(self, entity=None, attribute=None, old=None, new=None, kwargs=None, skip_state_check=False):
        self.log("calculate_classification_adjustment called")  # Add this line
        classification = self.get_state("sensor.electricity_twoday_classification")
        self.log(f"classification: {classification}")  # Add this line
        if not classification:  # Check if the state is empty
            self.log("No data available for two-day classification. Skipping adjustment calculation.")
            # Schedule this method to be called again in 1 minute
            self.run_in(self.calculate_classification_adjustment, 60)
            return

        # Check if the classification string contains a space
        if " " in classification:
            # Extract the class number from the state
            class_number = int(classification.split(" ")[1])
            self.log(f"class_number: {class_number}")  # Add this line
        else:
            self.log(f"Unexpected classification value: {classification}")
            return

        # Calculate the adjustment percentage linearly from class 1 to class 7
        # Adjust the range from +100% to -100%
        adjustment_percentage = round((1 - class_number) * (200 / (7 - 1)) + 100)
        
        self.set_state("sensor.electricity_ClassificationOptSignal", state=adjustment_percentage, attributes={"unit_of_measurement": "%"})

    def update_weighed_price_range(self, kwargs):
        try:
            self.log("update_weighed_price_range called")  # Log when the method is called

            prices_today = self.get_state("sensor.nordpool_kwh_se4_sek_3_10_025", attribute="today")
            current_price = self.get_state("sensor.nordpool_kwh_se4_sek_3_10_025", attribute="current_price")
            
            self.log(f"Current price: {current_price}, Prices today: {prices_today}")  # Log the fetched data
        except Exception as e:
            self.log(f"Exception in update_weighed_price_range: {e}")  # Log any exceptions