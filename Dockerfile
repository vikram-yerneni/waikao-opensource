# Use a slim version of Python as the base image to keep the image size small.
FROM python:3.9-slim

# Set the working directory inside the container.
WORKDIR /app

# Copy the requirements file and install dependencies first.
# This leverages Docker's layer caching for faster builds.
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . .

# Expose the port the app will run on.
EXPOSE 5000

# Define the command to run the application.
# Use gunicorn as a production-ready WSGI server.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]
