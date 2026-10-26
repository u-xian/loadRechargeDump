import os
import pandas as pd
import csv
from pathlib import Path
from io import StringIO
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

db_table = os.getenv('DB_TABLE')

csv_directory = os.path.join(BASE_DIR, os.getenv('DIR_PATH'))

connection_url = URL.create(
      "postgresql+psycopg2",
      username=os.getenv("DB_USERNAME"),
      password=os.getenv("DB_PASSWORD"),
      host=os.getenv("DB_HOST"),
      port=int(os.getenv("DB_PORT", 5432)),
      database=os.getenv("DB_NAME"),
  )

# Create a database engine 
db = create_engine(connection_url)

def psql_insert_copy(table, conn, keys, data_iter):
    dbapi_conn = conn.connection
    with dbapi_conn.cursor() as cur:
        buf = StringIO()
        csv.writer(buf).writerows(data_iter)
        buf.seek(0)
        columns = ', '.join(f'"{k}"' for k in keys)
        table_name = f'{table.schema}.{table.name}' if table.schema else table.name
        cur.copy_expert(f'COPY {table_name} ({columns}) FROM STDIN WITH CSV', buf)


# Get a list of CSV files in the specified directory
csv_files = [file for file in os.listdir(csv_directory) if file.endswith('.csv')]

# Iterate through each CSV file and load it into PostgreSQL without table creation
for file in csv_files:
    # Read the CSV file into a pandas DataFrame
    df = pd.read_csv(   os.path.join(csv_directory, file))

    df.columns = df.columns.str.strip().str.lower()

    # Write the DataFrame to the PostgreSQL database without explicit table creation
    #df.to_sql(db_table, con=conn, if_exists='replace', index=False, method='multi')
    df.to_sql(db_table, con=db, if_exists='append', index=False, chunksize=1000, method=psql_insert_copy)