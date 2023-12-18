import hassapi as hass
import csv
from datetime import datetime, time
from dateutil.parser import parse

class ReadPriceData(hass.Hass):

  def initialize(self):
    self.read_price_data(None)  # Run immediately on start
    self.run_hourly(self.read_price_data, datetime.now())

  def read_price_data(self, kwargs):
    file_path = '/homeassistant/price_ranges.csv'
    with open(file_path, 'r') as file:
      reader = csv.reader(file)
      next(reader)  # Skip the header row

      current_hour = datetime.now().hour
      for row in reader:
        timestamp = parse(row[0])
        hour = timestamp.hour
        if hour == current_hour:
          data = row[1].split(',')
          price = data[0].split(':')[1].strip()
          adjustment = data[2].split(':')[1].strip()
          self.set_state("sensor.Heatpump_ThrottleSignal", state="on", attributes={"price": price, "adjustment": adjustment})