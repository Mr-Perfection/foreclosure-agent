# SF Recorder Scraper

This application scrapes property records from the San Francisco Recorder's Office website.

## Features
- Scrapes all pages of search results
- Saves each page of data (up to 100 records per page) to individual CSV files
- Saves all data to a combined CSV file
- Stores data in a local PostgreSQL database

## Requirements
- Python 3.7+
- Chrome or Firefox browser
- PostgreSQL database server

## Setup

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up PostgreSQL Locally

#### Install PostgreSQL
```sh
psql --version
psql (PostgreSQL) 17.5 (Homebrew)
```
- **macOS**: `brew install postgresql` or download from [PostgreSQL website](https://www.postgresql.org/download/macosx/)
- **Linux**: `sudo apt-get install postgresql` or equivalent for your distribution
- **Windows**: Download installer from [PostgreSQL website](https://www.postgresql.org/download/windows/)

#### Start PostgreSQL Service
- **macOS**: `brew services start postgresql` or `pg_ctl -D /usr/local/var/postgres start`
- **Linux**: `sudo service postgresql start` or `sudo systemctl start postgresql`
- **Windows**: PostgreSQL should run as a service after installation

#### Create a User (Optional)
By default, the scraper will use `postgres` user with password `postgres`. To create a custom user:

```bash
# Login to PostgreSQL
sudo -u postgres psql

# Create user (change username and password as needed)
CREATE USER myuser WITH PASSWORD 'mypassword';

# Grant privileges
ALTER USER myuser WITH SUPERUSER;

# Exit PostgreSQL
\q
```

### 3. Configure Environment Variables
Create a `.env` file in the project root with:

```
SF_RECORDER_EMAIL=your_email@example.com
SF_RECORDER_PASSWORD=your_password
```

## Usage

Basic usage:
```bash
python scraper/scraper.py
```

With options:
```bash
python scraper/scraper.py --headless --db-name sf_recorder --db-user postgres --db-password postgres
```

### Available Options:
- `--email`: Login email (can also be set in .env)
- `--password`: Login password (can also be set in .env)
- `--headless`: Run browser in headless mode
- `--output`: Base path for output files
- `--csv-output`: Base path for CSV files
- `--temp-dir`: Directory for temporary files
- `--log-level`: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `--db-name`: PostgreSQL database name
- `--db-user`: PostgreSQL username
- `--db-password`: PostgreSQL password
- `--db-host`: PostgreSQL host
- `--db-port`: PostgreSQL port

## Output
- Individual CSV files will be saved per page as: `data/sf_recorder_YYYYMMDD_HHMMSS_page1.csv`, `_page2.csv`, etc.
- Combined CSV with all data: `data/sf_recorder_all_YYYYMMDD_HHMMSS.csv`
- PostgreSQL database table: `recorder_records`
