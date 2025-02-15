# Storage API Backend

A robust and well-documented RESTful API built with Flask, SQLAlchemy, and Flasgger. This backend serves as the core for managing storage items, basket items, nutrient details, and related resources for the Prepper App.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Requirements](#requirements)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
- [Project Structure](#project-structure)
- [Dependencies](#dependencies)
- [Contributing](#contributing)
- [License](#license)
- [Contact](#contact)

## Overview

The **Storage API Backend** is a RESTful service that enables the management of:
- **Storage Items:** Items stored in the system including details like name, amount, categories, storage location, and optional nutrient data.
- **Basket Items:** Items added to a shopping basket with support for incrementing and decrementing quantities.
- **Nutrients:** Nutrient information related to storage items, including various nutrient values and types.

This API is designed for ease of use, scalability, and integration with modern front-end applications.

## Features

- **CRUD Operations:** Create, read, update, and delete storage items, basket items, and nutrient details.
- **Bulk Insertion:** Add multiple storage items in one request.
- **Swagger Integration:** Fully documented API using Swagger (Swagger 2.0) for easy testing and integration.
- **CORS Support:** Configured to allow cross-origin requests from trusted domains.
- **Lightweight Database:** Utilizes SQLite by default (can be easily adapted to other databases).
- **Modern Implementation:** Built with Flask, SQLAlchemy 2.0 patterns, and enhanced with Flasgger for API documentation.

## Requirements

- Python 3.8+
- Flask 3.1.0
- SQLAlchemy 2.0.38
- Flasgger 0.9.7.1
- Flask-Cors 5.0.0
- PyYAML 6.0.2
- serpapi 0.1.5

Additional dependencies are listed in the [Dependencies](#dependencies) section.

## Setup & Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/storage-api-backend.git
   cd storage-api-backend
   ```

2. **Create and Activate a Virtual Environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Linux/macOS
   venv\Scripts\activate   # On Windows
   ```

3. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

## Environment Variables

### SEARCH_API_KEY

The application uses the SerpAPI service to fetch item icons. To enable this functionality, you must create an environment variable called `SEARCH_API_KEY`.

1. **Sign Up for SerpAPI:**
   - Visit [SerpAPI](https://serpapi.com/) and sign up for an account.
   - After signing up, navigate to your dashboard to obtain your API key.

2. **Set the Environment Variable:**
   ```bash
   export SEARCH_API_KEY=YOUR_API_KEY  # Linux/macOS
   set SEARCH_API_KEY=YOUR_API_KEY      # Windows
   ```

## Running the Application

To start the Flask development server, run:

```bash
python app.py
```

The API will be available at:  
**[http://localhost:5000](http://localhost:5000)**

## API Documentation

Swagger UI is integrated for interactive API documentation. Once the server is running, access the documentation at:

**[http://localhost:5000/apidocs](http://localhost:5000/apidocs)**

## License

This project is licensed under the MIT License.
