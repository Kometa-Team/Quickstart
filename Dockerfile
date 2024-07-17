FROM python:3-alpine

# Create app directory
WORKDIR /app

# Install app dependencies
COPY requirements.txt ./

RUN pip install -r requirements.txt

# Bundle app source
COPY . .

EXPOSE 5000
# Define the command to run the Flask application using Gunicorn
CMD ["gunicorn", "app:app", "-b", "0.0.0.0:5000", "-w", "4"]
