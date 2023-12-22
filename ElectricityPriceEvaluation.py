from appdaemon.plugins.hass import hassapi as hass
import numpy as np
from datetime import datetime, time

class ElectricityPriceEvaluation(hass.Hass):
    def initialize(self):
        self.event_cache = set()
        self.listen_state(self.evaluate_and_update_price_range, "sensor.nordpool_kwh_se4_sek_3_10_025", attribute="tomorrow_valid")

        # Get the current state of the 'tomorrow_valid' attribute
        tomorrow_valid = self.get_state("sensor.nordpool_kwh_se4_sek_3_10_025", attribute="tomorrow_valid")

        # Call evaluate_and_update_price_range with the current state of 'tomorrow_valid'
        self.evaluate_and_update_price_range("sensor.nordpool_kwh_se4_sek_3_10_025", "tomorrow_valid", None, tomorrow_valid, {})

        # Schedule evaluate_and_update_price_range to run every 15 minutes
        now = datetime.now()
        minutes = (now.minute // 15 + 1) * 15
        start_time = now.replace(minute=minutes%60, second=0, microsecond=0)
        if minutes > 59:
            start_time += timedelta(hours=1)
        self.run_every(self.update_price_range, start_time, 15*60)  # 15 minutes = 900 seconds

    def update_price_range(self, kwargs):
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

                # Create a calendar event for each entry in 'raw_today'
                for i, entry in enumerate(raw_today):
                    # Extract the 'start' and 'end' keys
                    start_time = entry['start']
                    end_time = entry['end']

                    summary = f"Price at {start_time}"  # Include the start time in the summary
                    description = f"Price: {prices[i]}"

                    # Check if the event is in the cache
                    if summary not in self.event_cache:
                        self.call_service("calendar/create_event", 
                                          entity_id="calendar.hourly_weighed_range", 
                                          summary=summary,  # Use summary as the summary
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