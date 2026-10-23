This is a ETL Pipeline to load RechargeDump in database.

In any Telecommunication company, the Charging System generate RechargeDump on frequency set (It can be very 30 min , 1 hour or daily). It is a csv file that contains records data of subscribers that purchased Airtime with others details such as RechargeTime, Amount, RechargeType,...

To run this pipeline, some steps have to be done before as follow:

## Database setup (PostgreSQL)

### 1. Create the database

```sql
CREATE DATABASE recharge_db;
```

Then connect to it before creating the table. In `psql`:

```
\c recharge_db
```

### 2. Create the raw table

```sql
CREATE TABLE recharge_dump_raw (
    recharge_id         INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subscriber_id       VARCHAR(15)   NOT NULL,
    recharge_date_time  TIMESTAMP     NOT NULL,
    card_number         VARCHAR(20),
    face_value          NUMERIC(18,2),
    expiration_offset   INTEGER,
    voucher_type        VARCHAR(20),
    batch_number        VARCHAR(30),
    serial_number       VARCHAR(30),
    recharge_comment    VARCHAR(255),
    unit_type_id        SMALLINT,
    rchg_src            VARCHAR(20),
    identity_id         BIGINT,
    group_id            SMALLINT,
    charge_code         VARCHAR(10),
    billed_bal_amt      NUMERIC(18,2),
    account_type        VARCHAR(20),
    currency_conv_rate  NUMERIC(12,4),
    iso_code            CHAR(3),
    voucher_iso_code    CHAR(3),
    sp_id               SMALLINT,
    balances_info       TEXT,
    filedate            DATE
);
```

> All data in this project is fictional and randomly generated.

2.  copy this repo on your Linux distro

3.  Enter the repo

4.  Create Python environment : python3 -m venv .venv

5.  Install dependencies : pip install -r requirements.txt

6.  copy the RechargeDump file (s) in a folder named dumps (currently there is one for demo)

7.  Run the pipeline : python loadingFile.py
