# Use an official Python image as the base image
FROM python:3.12-slim

# Set working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
  wget \
  libglib2.0-0 \
  libgl1-mesa-glx \
  libglu1-mesa \
  curl \
  prusa-slicer \
  && apt-get clean

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - && \
  ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Copy the pyproject.toml and poetry.lock files to the container
COPY pyproject.toml poetry.lock /app/

# Install Python dependencies using Poetry (without creating virtualenv)
RUN poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi

# Copy the rest of the FastAPI application code
COPY . /app

# Expose port 8000 for FastAPI
EXPOSE 8000

# Command to run FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
