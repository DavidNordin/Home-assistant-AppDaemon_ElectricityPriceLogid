import numpy as np
import matplotlib.pyplot as plt

# Parameters for the bell curve
mu = 0  # Mean
sigma = 1  # Standard deviation

# Generate data points for the bell curve
x = np.linspace(mu - 3*sigma, mu + 3*sigma, 100)
y = 1/(sigma * np.sqrt(2 * np.pi)) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)

# Plot the bell curve
plt.plot(x, y)
plt.title('Bell Curve (Normal Distribution)')
plt.xlabel('X')
plt.ylabel('Probability Density')
plt.grid(True)
plt.show()