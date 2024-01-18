import appdaemon.plugins.hass.hassapi as hass
import numpy as np
from scipy.integrate import odeint

# Constants
M_INITIAL = 0.5
T_INITIAL = 0
DT = 0.1
DURATION = 10
M_MAX = 6
T1 = 3
K2_MAX = 2.3

class MoldGrowthIndex(hass.Hass):
    def initialize(self):
        # Schedule the update_mold_growth_index method to run every hour
        self.run_every(self.update_mold_growth_index, "now", 60*60)

    def update_mold_growth_index(self, kwargs):
        # Get the current indoor temperature and humidity from Home Assistant sensors
        T = float(self.get_state("sensor.indoor_temperature"))  # Replace with your sensor
        RH = float(self.get_state("sensor.indoor_humidity"))  # Replace with your sensor

        # Function for the differential equation with correction coefficient k2
        def dM_dt_with_correction(M, t):
            # Define the correction coefficient k2 based on the current mold growth level
            k2 = K2_MAX * (1 - 2.3 * (M / M_MAX)**2)

            # Define the delay of mold growth when conditions become unfavorable
            if t < T1 - 6:
                delay_factor = 0.032
            elif T1 - 6 <= t <= T1 - 24:
                delay_factor = 0
            elif t > T1 - 24:
                delay_factor = 0.016

            # Differential equation with correction coefficient and delay factor
            return (1 / 7) * np.exp(0.68 * (-np.log(T) - 13.9 * RH)) * (1 - k2) - delay_factor

        # Time points for the simulation
        time_points = np.arange(T_INITIAL, DURATION, DT)

        # Solve the differential equation with correction coefficient using odeint
        M_values = odeint(dM_dt_with_correction, M_INITIAL, time_points)

        # Map the mold growth levels to categories
        growth_categories = [self.map_to_growth_category(M) for M in M_values.flatten()]

        # Log the final mold growth index and category
        self.log(f"Mold Growth Index: {M_values[-1]}")
        self.log(f"Growth Category: {growth_categories[-1]}")

        # Output the mold growth index and category to a sensor
        self.set_state("sensor.mold_growth_index", state=M_values[-1], attributes={
        "growth_category": growth_categories[-1]
        })

    @staticmethod
    def map_to_growth_category(M):
        # Map the mold growth level to a category
        if M < 1:
            return 0  # No growth
        elif 1 <= M < 2:
            return 1  # Small amounts of mold
        elif 2 <= M < 3:
            return 2  # <10% coverage
        elif 3 <= M < 4:
            return 3  # 10%-30% coverage
        elif 4 <= M < 5:
            return 4  # 30%-70% coverage
        elif 5 <= M < 6:
            return 5  # >70% coverage
        else:
            return 6  # Very heavy and tight growth