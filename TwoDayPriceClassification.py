import numpy as np
from datetime import datetime, time, timedelta
from appdaemon.plugins.hass.hassapi import Hass

STATE_UNKNOWN = 'unknown'

class TwoDayPriceClassification(Hass):
    def initialize(self):
        # Schedule the update method to run every hour
        self.run_hourly(self.update, time(minute=0, second=0))
        # Call the update method at the start
        self.update({})

    from datetime import datetime, timedelta

    def binned_classification(self, today_prices, tomorrow_prices=None):
        # Convert single float value to a list
        if isinstance(today_prices, float):
            today_prices = [today_prices]

        # If tomorrow's prices are available, concatenate today's and tomorrow's prices
        if tomorrow_prices is not None:
            prices = np.concatenate((today_prices, tomorrow_prices))
        # If tomorrow's prices are not available, use today's prices
        else:
            prices = np.array(today_prices)

        # Round down to two decimal places
        prices = np.floor(prices * 100) / 100

        # Divide the prices into 7 bins based on the range of the prices
        bins = np.linspace(min(prices), max(prices) + 0.01, 8)  # Add a small buffer to the maximum value

        # Classify the prices based on which bin they fall into
        classified_prices_binned_today = np.digitize(today_prices, bins)  # Classes from 1 to 7
        if tomorrow_prices is not None:
            classified_prices_binned_tomorrow = np.digitize(tomorrow_prices, bins)
        else:
            classified_prices_binned_tomorrow = None

        # Set the state of the sensor with timeslots as keys and class levels as values
        date_str_today = datetime.now().strftime("%Y-%m-%d")
        date_str_tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        hourly_data_binned_today = {}
        for hour, value in enumerate(classified_prices_binned_today):
            time_slot = f"{date_str_today} {hour:02d}:00-{(hour+1)%24:02d}:00"
            hourly_data_binned_today[time_slot] = f"Class {value}"

        hourly_data_binned_tomorrow = {}
        if classified_prices_binned_tomorrow is not None:
            for hour, value in enumerate(classified_prices_binned_tomorrow):
                time_slot = f"{date_str_tomorrow} {hour:02d}:00-{(hour+1)%24:02d}:00"
                hourly_data_binned_tomorrow[time_slot] = f"Class {value}"

        # Concatenate classifications for both days
        attributes = {**hourly_data_binned_today, **hourly_data_binned_tomorrow}
        current_hour_value = attributes.get(f"{date_str_today} {datetime.now().hour:02d}:00-{(datetime.now().hour+1)%24:02d}:00", STATE_UNKNOWN)        
        self.set_state('sensor.Electricity_TwoDay_classification', state=current_hour_value.strip(), attributes=attributes)

    def update(self, kwargs):
        # Fetch today's prices from your sensor
        today_prices = self.get_state('sensor.nordpool_kwh_se4_sek_3_10_025', attribute='today')

        # Check if the sensor data is valid
        if today_prices == STATE_UNKNOWN:
            self.log("Today's sensor data is not available")
            return

        # Convert the prices from string to float and replace 'unknown' with np.nan
        if isinstance(today_prices, list):
            today_prices = [float(price) if price != 'unknown' else np.nan for price in today_prices]
        else:
            today_prices = [float(price) if price != 'unknown' else np.nan for price in today_prices.split(',')]

        # Fetch tomorrow's prices from your sensor
        tomorrow_prices_partial = self.get_state('sensor.nordpool_kwh_se4_sek_3_10_025', attribute='tomorrow')

        # Check if tomorrow's prices are available
        if tomorrow_prices_partial is not None:
            # Convert tomorrow's prices from string to float and replace 'unknown' with np.nan
            if isinstance(tomorrow_prices_partial, list):
                tomorrow_prices_partial = [float(price) if price != 'unknown' else np.nan for price in tomorrow_prices_partial]
            else:
                tomorrow_prices_partial = [float(price) if price != 'unknown' else np.nan for price in tomorrow_prices_partial.split(',')]

            # Call the classification methods for today
            self.binned_classification(today_prices)

            # Call the classification methods for tomorrow if prices are available
            self.binned_classification(today_prices, tomorrow_prices_partial)
        else:
            # Call the classification methods for today if tomorrow's prices are not available
            self.binned_classification(today_prices)
