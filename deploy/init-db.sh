#!/bin/bash
# Create additional databases needed by modules
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Form data sync database
    CREATE DATABASE beakform_data OWNER $POSTGRES_USER;
EOSQL

echo "Additional databases created."
