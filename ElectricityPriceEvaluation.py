import hassapi as hass
import numpy as np
from datetime import datetime, time

from hassapi import Hass

class ElectricityPriceEvaluation(Hass):
    def initialize(self):
        self.event_cache = set()
        self.listen_state(self.evaluate_and_update_price_range, "sensor.nordpool_kwh_se4_sek_3_10_025", attribute="tomorrow_valid")

        # Get the current state of the 'tomorrow_valid' attribute
        tomorrow_valid = self.get_state("sensor.nordpool_kwh_se4_sek_3_10_025", attribute="tomorrow_valid")

        # Call evaluate_and_update_price_range with the current state of 'tomorrow_valid'
        self.evaluate_and_update_price_range("sensor.nordpool_kwh_se4_sek_3_10_025", "tomorrow_valid", None, tomorrow_valid, {})

    def evaluate_and_update_price_range(self, entity, attribute, old, new, kwargs):
        try:
            if new is True:
                self.log("Tomorrow's data is valid: Turning on the price evaluation logic.")

                # Get the 'raw_today' attribute of the sensor
                raw_today = self.get_state("sensor.nordpool_kwh_se4_sek_3_10_025", attribute="raw_tomorrow")

                # Collect all the prices
                prices = [float(entry['value']) for entry in raw_today]

                # Calculate the average price
                average_price = np.mean(prices)

                # Calculate the 25% lowest and highest prices
                prices_sorted = sorted(prices)
                lower_25_percentile = np.percentile(prices_sorted, 25)
                upper_25_percentile = np.percentile(prices_sorted, 75)

                # Define the ranges
                lowest_range = (min(prices_sorted), lower_25_percentile)
                lower_middle_range = (lower_25_percentile, average_price)
                upper_middle_range = (average_price, upper_25_percentile)
                highest_range = (upper_25_percentile, max(prices_sorted))

                # Define the sensor entity
                sensor_entity = "sensor.weighed_price_range"

                # Set the state and attributes of the sensor
                self.set_state(sensor_entity, state=prices, attributes={
                    "25% lowest price": lower_25_percentile,
                    "25% highest price": upper_25_percentile,
                    "Lowest range": lowest_range,
                    "Lower-middle range": lower_middle_range,
                    "Upper-middle range": upper_middle_range,
                    "Highest range": highest_range,
                })

                # Create a calendar event for each entry in 'raw_today'
                for i, entry in enumerate(raw_today):
                    # Extract the 'start' and 'end' keys
                    start_time = entry['start']
                    end_time = entry['end']

                    # Define the range according to the price
                    if prices[i] <= lower_25_percentile:
                        range_name = "Lowest range"
                    elif prices[i] <= average_price:
                        range_name = "Lower-middle range"
                    elif prices[i] <= upper_25_percentile:
                        range_name = "Upper-middle range"
                    else:
                        range_name = "Highest range"

                    summary = f"{range_name} at {start_time}"  # Include the start time in the summary
                    description = f"Price: {prices[i]}, Range: {range_name}"

                    # Check if the event is in the cache
                    if summary not in self.event_cache:
                        self.call_service("calendar/create_event", 
                                          entity_id="calendar.hourly_weighed_range", 
                                          summary=range_name,  # Use range_name as the summary
                                          description=description,
                                          start_date_time=start_time, 
                                          end_date_time=end_time)

                        # Add the event to the cache
                        self.event_cache.add(summary)

            else:
                self.log("Tomorrow's data is not valid.")

        except Exception as e:
            self.log(f"Error during evaluate_and_update_price_range: {e}", level="ERROR")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", level="ERROR")
            raise

    # ... any other methods ...