# Author: David Nordin
# Description: This App calculates the two-day mean price for each hour and classifies it into one of five classes.
# The classification is based on the two-day mean price's position in the distribution of all two-day mean prices.
# The classification is then used to set the state of the sensor 'sensor.Electricity_TwoDay_classification'.
# The classification of each hour is also set as an attribute of the sensor.
# The App also prints the two-day mean price and classification for each hour in the AppDaemon log.
# The App is intended to be used with the Nordpool sensor (
# https://www.home-assistant.io/integrations/nordpool/).
# interpolation is used to calculate the adjustment percentage for the current minute and transition period between hours.
# The adjustment percentage is then used to set the state of the sensor 'sensor.Heatpump_ThrottleSignal'.
# The adjustment percentage is also set as an attribute of the sensor.

import hassapi as hass
import csv
from datetime import datetime, timedelta
from dateutil.parser import parse

class ReadPriceData(hass.Hass):

  def initialize(self):
    self.current_data = None
    self.next_data = None
    self.read_price_data(None)  # Run immediately on start
    self.run_every(self.read_price_data, datetime.now(), 5*60)  # Run every 15 minutes

  def read_price_data(self, kwargs):
    file_path = '/homeassistant/price_ranges.csv'
    with open(file_path, 'r') as file:
      reader = csv.reader(file)
      next(reader)  # Skip the header row

      current_time = datetime.now()
      current_hour = current_time.hour
      current_minute = (current_time.minute // 5) * 5  # Round down to the nearest 5 minutes

      rows = list(reader)
      for i, row in enumerate(rows):
        timestamp = parse(row[0])
        hour = timestamp.hour
        minute = timestamp.minute

        if hour == current_hour and minute == current_minute:
          self.current_data = self.parse_row(row)
          if i+1 < len(rows):
            self.next_data = self.parse_row(rows[i+1])
          break

      if self.current_data and self.next_data:
        adjustment = self.interpolate(self.current_data['adjustment'], self.next_data['adjustment'])
        self.set_state("sensor.Heatpump_ThrottleSignal", state=adjustment, attributes={
          "device_class": "measurement",
          "unit_of_measurement": "%",
          "price": self.current_data['price']
        })

  def parse_row(self, row):
    data = row[1].split(',')
    price = float(data[0].split(':')[1].strip())
    adjustment = float(data[2].split(':')[1].strip().replace('%', ''))
    return {'price': price, 'adjustment': adjustment}

  def interpolate(self, start, end):
    current_minute = datetime.now().minute
    current_second = datetime.now().second
    total_seconds = current_minute * 60 + current_second
    transition_progress = total_seconds / (60 * 60)  # Divide by the number of seconds in an hour
    adjustment = start + (end - start) * transition_progress
    return round(adjustment)  # Round to the nearest whole number