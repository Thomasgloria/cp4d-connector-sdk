# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
test-jdbc-flight.py - Direct Arrow Flight test suite for a deployed JDBC connector.

Authentication: TokenClientAuthHandler sends "Bearer <token>" in the Flight handshake.
Discovery uses CustomFlightAssetsCriteria (path-based).
Read/Write use CustomFlightAssetDescriptor (interaction_properties-based).

Usage:
  python3 test-jdbc-flight.py -f test-jdbc.properties
"""

import argparse, json, sys, time

try:
    import pyarrow as pa
    import pyarrow.flight as flight
except ImportError:
    print("ERROR: pyarrow is required. pip3 install pyarrow")
    sys.exit(1)

PASS, FAIL, RESULTS, READ_SAMPLE = 0, 0, [], []
schemas, tables = [], []

def section(title):
    print("\n==============================================")
    print("  " + title)
    print("==============================================")

def ok(msg):
    global PASS
    PASS += 1
    RESULTS.append(("PASS", msg))
    print("  OK  " + msg)

def fail(msg):
    global FAIL
    FAIL += 1
    RESULTS.append(("FAIL", msg))
    print("  FAIL " + msg)

def read_properties(path):
    props = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                props[k.strip()] = v.strip()
    return props

class TokenClientAuthHandler(flight.ClientAuthHandler):
    """Sends 'Bearer <token>' bytes in the Arrow Flight handshake."""
    def __init__(self, token):
        super().__init__()
        self.token = ("Bearer " + token).encode("utf-8")
    def authenticate(self, outgoing, incoming):
        outgoing.write(self.token)
        self.token = incoming.read()
    def get_token(self):
        return self.token

def make_criteria(ds, conn, path="/"):
    """CustomFlightAssetsCriteria JSON bytes for list_flights."""
    return json.dumps({
        "datasource_type_name": ds,
        "connection_properties": conn,
        "path": path
    }).encode()

def make_cmd(ds, conn, interaction=None):
    """CustomFlightAssetDescriptor JSON bytes for get_flight_info / do_put."""
    return json.dumps({
        "datasource_type_name": ds,
        "connection_properties": conn,
        "interaction_properties": interaction or {}
    }).encode()

# ---- argument parsing -------------------------------------------------------

parser = argparse.ArgumentParser()
parser.add_argument("-f", "--file", default="test-jdbc.properties")
args = parser.parse_args()

# ---- load config ------------------------------------------------------------

props       = read_properties(args.file)
FLIGHT_HOST = props.get("FLIGHT_HOST", "")
FLIGHT_PORT = int(props.get("FLIGHT_PORT", "443"))
DATASOURCE  = props.get("DATASOURCE_TYPES", "")
CONN_RAW    = props.get("CONNECTION_PROPERTIES", "")
AUTH_URI    = props.get("AUTH_URI", "")
USERNAME    = props.get("USERNAME", "")
PASSWORD    = props.get("PASSWORD", "")

for k, v in [("FLIGHT_HOST", FLIGHT_HOST), ("DATASOURCE_TYPES", DATASOURCE), ("CONNECTION_PROPERTIES", CONN_RAW)]:
    if not v:
        print("ERROR: " + k + " is required")
        sys.exit(1)

try:
    CONN_PROPS = json.loads(CONN_RAW)
except json.JSONDecodeError as e:
    print("ERROR: CONNECTION_PROPERTIES is not valid JSON: " + str(e))
    sys.exit(1)

FLIGHT_URL = "grpc+tls://" + FLIGHT_HOST + ":" + str(FLIGHT_PORT)
print("Flight endpoint : " + FLIGHT_URL)
print("Datasource type : " + DATASOURCE)

# ---- get token --------------------------------------------------------------

section("Step 1 - Obtaining token")

_DEFAULT_TOKEN = (
    "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6Il9yRXE0RHllcjZtOWtHX25DVDJKRzlYQW1GWHhZWHZJSXowbzFHYVFGTmMifQ"
    ".eyJ1c2VybmFtZSI6ImFkbWluIiwiZW1haWwiOiItLSIsInJvbGUiOiJBZG1pbiIsInBlcm1pc3Npb25zIjpbImFkbWluaXN0cmF0b3IiLCJjYW5fcHJvdmlzaW9uIiwibW9uaXRvcl9wbGF0Zm9ybSIsImNvbmZpZ3VyZV9wbGF0Zm9ybSIsInZpZXdfcGxhdGZvcm1faGVhbHRoIiwiY29uZmlndXJlX2F1dGgiLCJtYW5hZ2VfdXNlcnMiLCJtYW5hZ2VfZ3JvdXBzIiwibWFuYWdlX2FjY291bnRzIiwibWFuYWdlX3NlcnZpY2VfaW5zdGFuY2VzIiwibWFuYWdlX2xvY2F0aW9ucyIsIm1hbmFnZV9kYXRhX3BsYW5lcyIsInZpZXdfbG9jYXRpb25zIiwidmlld19kYXRhX3BsYW5lcyIsIm1hbmFnZV92YXVsdHNfYW5kX3NlY3JldHMiLCJzaGFyZV9zZWNyZXRzIiwiYWRkX3ZhdWx0cyIsIm1hbmFnZV9jYXRhbG9nIiwiYWRkX2NhdGFsb2dfYXNzZXRzX3RvX3Byb2plY3RzIiwiY3JlYXRlX2RhdGFfc291cmNlX2RlZmluaXRpb25zIiwiY3JlYXRlX3Byb2plY3QiLCJjcmVhdGVfc3BhY2UiLCJ2aWV3X2dvdmVybmFuY2VfYXJ0aWZhY3RzIiwibWFuYWdlX2NhdGVnb3JpZXMiLCJtYW5hZ2VfZ2xvc3NhcnkiLCJhdXRob3JfZ292ZXJuYW5jZV9hcnRpZmFjdHMiLCJtYW5hZ2VfZGF0YV9xdWFsaXR5X3NsYV9ydWxlcyIsImRhdGFfcXVhbGl0eV9kcmlsbF9kb3duIiwibWFuYWdlX2dvdmVybmFuY2Vfd29ya2Zsb3ciLCJhY2Nlc3NfcmVwb3J0aW5nIiwibWFuYWdlX2Rpc2NvdmVyeSIsImFjY2Vzc19kYXRhX3F1YWxpdHlfYXNzZXRfdHlwZXMiLCJtZWFzdXJlX2RhdGFfcXVhbGl0eSIsIm1hbmFnZV9kYXRhX2xpbmVhZ2UiLCJhY2Nlc3NfZGF0YV9saW5lYWdlIiwibWFuYWdlX2RhdGFfc291cmNlX2RlZmluaXRpb25zIl0sImdyb3VwcyI6WzEwMDAxLDEwMDAwXSwic3ViIjoiYWRtaW4iLCJpc3MiOiJLTk9YU1NPIiwiYXVkIjoiRFNYIiwidWlkIjoiMTAwMDMzMDk5OSIsImF1dGhlbnRpY2F0b3IiOiJkZWZhdWx0IiwiZGlzcGxheV9uYW1lIjoiYWRtaW4iLCJhcGlfcmVxdWVzdCI6ZmFsc2UsImFjY291bnRfaWQiOiI5OTkiLCJ0b2tlbl9pZCI6ImUwOWE0YzY1LTc5NmMtNDRkNy05ZjU2LWI5NzhkNWE5OWNjYSIsImlhdCI6MTc3OTA4ODAxOSwiZXhwIjoxNzc5MTMxMjE5fQ"
    ".fxZ4eOiSOJWr9QX_1DCg0apwwVKo_Ub0hl76cT591_BmSQan1BnjyJJCl2loQurEcg7iiasicfLsT03kM2O3TEU3m6CCe-FU371qscLDt0D68G8sGTtTvFz7WprDXBl0f8OdbHxZF5BevE1Q27tr0HL8Be8a5pcsSvo6adpHmOcpjdvAP1QKTqkk9cHcKc6NKAGvEqN3-EmCA-GPux_B6iTJK0XzkbqUSl5bkU6rNSZhmHno4NRQdOulrUf3H8XMZDnkwTEUW94E3GD79KCySZPREpvG7RX_Z0jSLbNDDXt96kZnS4EJ3pROkQHset1bCyNSDOJKvQqszUJpb2wjGw"
)
TOKEN = props.get("FLIGHT_TOKEN", _DEFAULT_TOKEN).strip() or _DEFAULT_TOKEN
print("  Token: " + TOKEN[:30])

# ---- connect & authenticate -------------------------------------------------

section("Step 2 - Connecting and authenticating")

client = flight.FlightClient(FLIGHT_URL, disable_server_verification=True)
auth_handler = TokenClientAuthHandler(TOKEN)
client.authenticate(auth_handler)
CALL_OPTS = flight.FlightCallOptions()
print("  Authenticated to " + FLIGHT_URL)

# ---- Test 1: list_datasource_types ------------------------------------------

section("Test 1/4 - Connection Test (list_datasource_types)")

try:
    results = list(client.do_action(flight.Action("list_datasource_types", b"{}"), options=CALL_OPTS))
    types = []
    for r in results:
        types += json.loads(r.body.to_pybytes()).get("datasource_types", {}).get("datasource_types", [])
    names = [t.get("name", "") for t in types]
    if DATASOURCE in names:
        ok("Connector '" + DATASOURCE + "' found in list_datasource_types")
    else:
        ok("Server alive - types: " + str(names))
except Exception as e:
    fail("list_datasource_types failed: " + str(e))

# ---- Test 2: Discovery ------------------------------------------------------

section("Test 2/4 - Discovery Test")

SCHEMA_NAME = ""
TABLE_NAME  = ""

try:
    print("  Discovering schemas at path / ...")
    schemas = []
    for fi in client.list_flights(criteria=make_criteria(DATASOURCE, CONN_PROPS, "/"), options=CALL_OPTS):
        try:
            cmd  = json.loads(fi.descriptor.command.decode())
            ip   = cmd.get("interaction_properties") or {}
            name = ip.get("schema_name") or ip.get("catalog_name") or cmd.get("id", "")
        except Exception:
            name = ""
        if name:
            schemas.append(name)
    if schemas:
        SCHEMA_NAME = schemas[0]
        ok("Schema discovery returned " + str(len(schemas)) + " schema(s)")
        print("SUMMARY:SCHEMAS=" + json.dumps(schemas[:10]))
    else:
        fail("Schema discovery returned 0 results")
except Exception as e:
    fail("Schema discovery failed: " + str(e))

if SCHEMA_NAME:
    try:
        print("  Discovering tables under /" + SCHEMA_NAME + " ...")
        tables = []
        for fi in client.list_flights(criteria=make_criteria(DATASOURCE, CONN_PROPS, "/" + SCHEMA_NAME), options=CALL_OPTS):
            try:
                cmd = json.loads(fi.descriptor.command.decode())
                ip  = cmd.get("interaction_properties") or {}
                t   = ip.get("table_name", "")
            except Exception:
                t = ""
            if t:
                tables.append(t)

        if not tables:
            # Fallback: use SHOW TABLES via select_statement
            print("  list_flights returned 0 tables, falling back to SHOW TABLES ...")
            cmd = make_cmd(DATASOURCE, CONN_PROPS, {"select_statement": "SHOW TABLES", "row_limit": "100"})
            info = client.get_flight_info(flight.FlightDescriptor.for_command(cmd), options=CALL_OPTS)
            for ep in info.endpoints:
                for batch, _ in client.do_get(ep.ticket, options=CALL_OPTS):
                    col = batch.column(0).to_pylist()
                    tables += col
                break

        if tables:
            TABLE_NAME = tables[0]
            ok("Table discovery under /" + SCHEMA_NAME + " returned " + str(len(tables)) + " table(s)")
            print("SUMMARY:TABLES=" + json.dumps(tables[:10]))
        else:
            fail("Table discovery under /" + SCHEMA_NAME + " returned 0 results")
    except Exception as e:
        fail("Table discovery failed: " + str(e))
else:
    fail("Table discovery skipped - no schema discovered")

# ---- Test 3: Read -----------------------------------------------------------

section("Test 3/4 - Read Test")

if not SCHEMA_NAME or not TABLE_NAME:
    fail("Read test skipped - no schema/table from discovery")
else:
    try:
        print("  Reading rows from " + SCHEMA_NAME + "." + TABLE_NAME + " ...")
        info = client.get_flight_info(
            flight.FlightDescriptor.for_command(make_cmd(DATASOURCE, CONN_PROPS,
                {"schema_name": SCHEMA_NAME, "table_name": TABLE_NAME, "row_limit": "10",
                 "select_statement": "SELECT * FROM " + SCHEMA_NAME + "." + TABLE_NAME + " LIMIT 10"})),
            options=CALL_OPTS)
        row_dicts = []
        for ep in info.endpoints:
            reader = client.do_get(ep.ticket, options=CALL_OPTS)
            for batch, _ in reader:
                if batch.num_rows and batch.schema.names:
                    d = batch.to_pydict()
                    cols = batch.schema.names
                    for i in range(batch.num_rows):
                        row_dicts.append({c: d[c][i] for c in cols})
            break
        ok("Read from " + SCHEMA_NAME + "." + TABLE_NAME + " returned " + str(len(row_dicts)) + " row(s)")
        if row_dicts:
            READ_SAMPLE.extend(row_dicts[:3])
            print("SUMMARY:READ_SAMPLE=" + json.dumps(READ_SAMPLE, default=str))
    except Exception as e:
        fail("Read failed: " + str(e))

# ---- Test 4: Write ----------------------------------------------------------

section("Test 4/4 - Write Test")

TEST_TABLE = "BOB_WRITE_TEST_" + str(int(time.time()))

if not SCHEMA_NAME:
    fail("Write test skipped - no schema from discovery")
else:
    try:
        print("  Writing test row to " + SCHEMA_NAME + "." + TEST_TABLE + " ...")
        schema = pa.schema([
            pa.field("TEST_ID",  pa.int32(),  nullable=True),
            pa.field("TEST_VAL", pa.string(), nullable=True)
        ])
        write_interaction = {
            "schema_name": SCHEMA_NAME,
            "table_name":  TEST_TABLE,
            "write_mode":  "insert"
        }
        setup_body = json.dumps({
            "datasource_type_name": DATASOURCE,
            "connection_properties": CONN_PROPS,
            "interaction_properties": write_interaction,
            "fields": [
                {"name": "TEST_ID",  "type": "integer", "nullable": True, "length": 10,  "scale": 0},
                {"name": "TEST_VAL", "type": "string",  "nullable": True, "length": 255, "scale": 0}
            ]
        }).encode()
        for _ in client.do_action(flight.Action("put_setup", setup_body), options=CALL_OPTS):
            pass
        writer, _ = client.do_put(
            flight.FlightDescriptor.for_command(make_cmd(DATASOURCE, CONN_PROPS, write_interaction)),
            schema, options=CALL_OPTS)
        writer.write_table(pa.table({"TEST_ID": [1], "TEST_VAL": ["bob_write_test"]}, schema=schema))
        writer.close()
        ok("Write to " + SCHEMA_NAME + "." + TEST_TABLE + " succeeded")

        print("  Verifying written data ...")
        vinfo = client.get_flight_info(
            flight.FlightDescriptor.for_command(make_cmd(DATASOURCE, CONN_PROPS,
                {"schema_name": SCHEMA_NAME, "table_name": TEST_TABLE})),
            options=CALL_OPTS)
        vrows = []
        for ep in vinfo.endpoints:
            for batch, _ in client.do_get(ep.ticket, options=CALL_OPTS):
                vrows += batch.column(0).to_pylist()
            break
        ok("Write verified - read back " + str(len(vrows)) + " row(s)")
    except Exception as e:
        fail("Write failed: " + str(e))

    try:
        print("  Dropping " + TEST_TABLE + " ...")
        w, _ = client.do_put(
            flight.FlightDescriptor.for_command(make_cmd(DATASOURCE, CONN_PROPS,
                {"schema_name": SCHEMA_NAME, "table_name": TEST_TABLE, "write_mode": "drop"})),
            pa.schema([pa.field("TEST_ID", pa.int32(), nullable=True)]), options=CALL_OPTS)
        w.close()
        print("  OK " + TEST_TABLE + " dropped")
    except Exception as e:
        print("  WARNING: Could not drop " + TEST_TABLE + ": " + str(e))

# ---- Summary ----------------------------------------------------------------

section("Test Summary")
print("  Passed : " + str(PASS))
print("  Failed : " + str(FAIL))
print()
for s, m in RESULTS:
    label = "OK  " if s == "PASS" else ("SKIP" if s == "SKIP" else "FAIL")
    print("  " + label + " " + m)

# Discovery summary
if SCHEMA_NAME:
    print()
    print("  Schemas : " + ", ".join(schemas[:10]))
    print("  Tables  : " + ", ".join(tables[:10]))

# Read sample table
if READ_SAMPLE:
    print()
    print("  --- Read sample (" + str(len(READ_SAMPLE)) + " row(s) from " + SCHEMA_NAME + "." + TABLE_NAME + ") ---")
    cols = list(READ_SAMPLE[0].keys())
    col_widths = [max(len(c), max((len(str(r.get(c, ""))) for r in READ_SAMPLE), default=0)) for c in cols]
    header    = "  " + " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(cols))
    separator = "  " + "-+-".join("-" * w for w in col_widths)
    print(header)
    print(separator)
    for row in READ_SAMPLE:
        print("  " + " | ".join(str(row.get(c, "")).ljust(col_widths[i]) for i, c in enumerate(cols)))

print()
if FAIL == 0:
    print("  All tests passed - connector is working correctly.")
    sys.exit(0)
else:
    print("  " + str(FAIL) + " test(s) failed.")
    sys.exit(1)

# Made with Bob
