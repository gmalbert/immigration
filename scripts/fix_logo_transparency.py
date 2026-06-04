from PIL import Image
import numpy as np

# Load the logo
img = Image.open('data_files/logo.png').convert('RGBA')
data = np.array(img)

# Define gray colors to make transparent (RGB values near gray)
# Adjust threshold as needed
gray_threshold = 30  # How close to pure gray (128,128,128)
value_threshold = 50  # How light/dark from mid-gray

for i in range(data.shape[0]):
    for j in range(data.shape[1]):
        r, g, b, a = data[i, j]
        # Check if pixel is grayish (R≈G≈B) and lightish
        if (abs(r - g) < gray_threshold and 
            abs(g - b) < gray_threshold and 
            abs(r - b) < gray_threshold and
            r > 180 and g > 180 and b > 180):  # Light gray/white
            data[i, j] = [255, 255, 255, 0]  # Make transparent

# Save the new logo
new_img = Image.fromarray(data, 'RGBA')
new_img.save('data_files/logo_transparent.png')
print("Created logo_transparent.png with gray background removed")
