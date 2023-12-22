import hassapi as hass
import csv
import numpy as np
from datetime import datetime, timedelta

class hvacControl(hass.Hass):
    def initialize(self):
        self.run_every(self.calculate_adjustment, datetime.now(), 5*60)  # Run every 5 minutes

    def evaluate_and_update_price_range(self, entity, attribute, old, new, kwargs):
        if new is True:
            self.log("Tomorrow's data is valid: Turning on the price evaluation logic.")

            raw_today = self.get_state("sensor.nordpool_kwh_se4_sek_3_10_025", attribute="raw_tomorrow")
            self.log(f"raw_today: {raw_today}")

            prices = [float(entry['value']) for entry in raw_today]
            self.log(f"prices: {prices}")

            average_price = np.mean(prices)

            prices_sorted = sorted(prices)
            lower_25_percentile = np.percentile(prices_sorted, 25)
            upper_25_percentile = np.percentile(prices_sorted, 75)

            lowest_range = min(prices_sorted)
            lower_middle_range = lower_25_percentile
            upper_middle_range = upper_25_percentile
            highest_range = max(prices_sorted)

            try:
                with open('/homeassistant/price_ranges.csv', 'a', newline='') as file:
                    writer = csv.writer(file)
                    for i, entry in enumerate(raw_today):
                        start_time = entry['start']
                        end_time = entry['end']
                        current_price = prices[i]

                        if current_price <= lower_middle_range:
                            adjustment_percentage = round(100 - ((current_price - lowest_range) / (lower_middle_range - lowest_range)) * 100)
                        elif current_price <= upper_middle_range:
                            adjustment_percentage = round(((current_price - lower_middle_range) / (upper_middle_range - lower_middle_range)) * -100)
                        elif current_price <= highest_range:
                            adjustment_percentage = -100
                        else:
                            adjustment_percentage = round(((current_price - highest_range) / (highest_range - lowest_range)) * 100)

                        if current_price <= lower_25_percentile:
                            range_name = "Lowest range"
                        elif current_price <= average_price:
                            range_name = "Lower-middle range"
                        elif current_price <= upper_25_percentile:
                            range_name = "Upper-middle range"
                        else:
                            range_name = "Highest range"

                        summary = f"{range_name} at {start_time}"
                        description = f"Price: {current_price}, Range: {range_name}, Adjustment: {adjustment_percentage}%"
                        writer.writerow([start_time, description])
            except Exception as e:
                self.log(f"Error writing to CSV file: {e}")

    def calculate_adjustment(self, entity=None, attribute=None, old=None, new=None, kwargs=None, skip_state_check=False, now=None):
        # Rest of the code...
        if not skip_state_check and (new is None or new == "true"):
            return
        raw_tomorrow = self.get_state("sensor.nordpool_kwh_se4_sek_3_10_025", attribute="raw_tomorrow")
        if not raw_tomorrow:  # Check if the list is empty
            self.log("No data available for tomorrow. Skipping adjustment calculation.")
            return

        prices = [float(entry['value']) for entry in raw_tomorrow]
        prices_sorted = sorted(prices)

        current_event = raw_tomorrow[0]
        current_price = float(current_event['value'])

        lowest_price = min(prices_sorted)
        highest_price = max(prices_sorted)

        lower_25_percentile = np.percentile(prices_sorted, 25)
        upper_25_percentile = np.percentile(prices_sorted, 75)

        lowest_range = min(prices_sorted)
        lower_middle_range = lower_25_percentile
        upper_middle_range = upper_25_percentile
        highest_range = max(prices_sorted)

        # Calculate the adjustment percentage based on the defined ranges
        if current_price <= lower_middle_range:
            adjustment_percentage = round(100 - ((current_price - lowest_range) / (lower_middle_range - lowest_range)) * 100)
        elif current_price <= upper_middle_range:
            adjustment_percentage = round(((current_price - lower_middle_range) / (upper_middle_range - lower_middle_range)) * -100)
        elif current_price <= highest_range:
            adjustment_percentage = -100
        else:
            adjustment_percentage = round(((current_price - highest_range) / (highest_range - lowest_range)) * 100)

        self.log("hvac adjusted for {}% adjustment".format(adjustment_percentage))