# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview
The application is a Python-based web service using **Flask**.
- **Backend (`/backend`)**: Contains the API logic, database management, and ML recommendation engine.
- **Frontend**: Static files (HTML, CSS, JS) served by the Flask app.
- **Database**: SQLite (for development/testing) or MySQL (for production) managed via a custom `Database` wrapper.

## Development & Common Tasks

### Environment Setup
The backend uses a virtual environment located at `backend/.venv`. Ensure this is activated before running backend commands.

### Running the Application
To start the development server:
```bash
# Set environment variables
$env:FLASK_APP="backend/app.py"; $env:FLASK_DEBUG="1"; 

# Run using Flask
flask run

# Alternatively, run via wsgi.py
python backend/wsgi.py
```

### Database Management
To initialize or check the database schema:
```bash
python backend/init_db.py
python check_tables.py
```

### Admin Management
Use the dedicated CLI tool to manage admin accounts securely:
```bash
python backend/manage_admins.py list
python backend/manage_admins.py create --email <email> --name "<name>"
python backend/manage_admins.py promote --email <email>
```

### Running Tests
Automated tests are located in `backend/tests/`. Run them using `pytest`:
```bash
pytest backend/tests/
```
To run a single test file:
```bash
pytest backend/tests/test_recipes_api.py
```
