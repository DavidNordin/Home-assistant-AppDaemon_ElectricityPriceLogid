import appdaemon.plugins.hass.hassapi as hass
import requests

class NasdaqAPI(hass.Hass):

    def initialize(self):
        self.api_key = 'cjyEo98gAEGbGyAxnAw-'  # Replace with your actual API key
        self.run_in(self.get_data, 0)  # Run the get_data method immediately

    def get_data(self, kwargs):
        series = 'ENOFUTBLQ1-25'
        url = f'https://data.nasdaq.com/api/v3/datatables/ETFG/FUND.json?series={series}&api_key={self.api_key}'

        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            self.log(data)
        else:
            self.log(f"Error: {response.status_code}, {response.text}")