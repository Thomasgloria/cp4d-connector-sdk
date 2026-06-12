# Generic JDBC Connector - Environment Configuration

This document describes the environment variables that can be used to configure the Generic JDBC connector at deployment time.

## Overview

The Generic JDBC connector has been enhanced to support runtime configuration through environment variables. This allows you to create a single connector image that can be configured for different databases without rebuilding the code.

## Supported Environment Variables

### Connector Identity

| Variable | Description | Default Value | Required |
|----------|-------------|---------------|----------|
| `CONNECTOR_DATASOURCE_TYPE` | The unique identifier name for the datasource type | `custom_genericjdbc` | No |
| `CONNECTOR_LABEL` | The display label for the connector | `Generic JDBC (custom)` | No |
| `CONNECTOR_DESCRIPTION` | The description of the connector | Default description from properties | No |

### JDBC Driver Configuration

| Variable | Description | Default Value | Required |
|----------|-------------|---------------|----------|
| `JDBC_DRIVER_CLASS` | Fully qualified class name of the JDBC driver | Auto-detected from JDBC URL | No |
| `JDBC_DRIVER_PATH` | Path to driver JAR file or directory containing JARs | None (uses built-in drivers) | No |

**Notes:**
- When `JDBC_DRIVER_CLASS` is set, the connector will use this driver class instead of auto-detecting from the JDBC URL
- When `JDBC_DRIVER_PATH` is set, the connector will load driver JARs from the specified location using a dynamic ClassLoader
- `JDBC_DRIVER_PATH` can be:
  - A single JAR file: `/opt/drivers/mydriver.jar`
  - A directory containing JAR files: `/opt/drivers` (all `.jar` files will be loaded)
- If `JDBC_DRIVER_CLASS` is specified without `JDBC_DRIVER_PATH`, the driver class must be available in the application's classpath

### Row Limit Configuration

| Variable | Description | Default Value | Required |
|----------|-------------|---------------|----------|
| `ROW_LIMIT_PREFIX` | Custom SQL prefix for row limiting (e.g., `TOP ${row_limit}`) | Auto-detected from driver | No |
| `ROW_LIMIT_SUFFIX` | Custom SQL suffix for row limiting (e.g., `LIMIT ${row_limit}`) | Auto-detected from driver | No |

**Note:** Use `${row_limit}` as a placeholder for the actual row limit value in your custom prefix/suffix.

## Usage Examples

### Example 1: Using Built-in MySQL Driver

```bash
# Environment variables (driver already in classpath)
CONNECTOR_DATASOURCE_TYPE=custom_mysql_prod
CONNECTOR_LABEL=Production MySQL Database
CONNECTOR_DESCRIPTION=MySQL production database connector
JDBC_DRIVER_CLASS=com.mysql.cj.jdbc.Driver
```

### Example 2: Custom Oracle Driver from Directory

```bash
# Environment variables (load driver from directory)
CONNECTOR_DATASOURCE_TYPE=custom_oracle_hr
CONNECTOR_LABEL=Oracle HR Database
CONNECTOR_DESCRIPTION=Oracle database for HR applications
JDBC_DRIVER_CLASS=oracle.jdbc.OracleDriver
JDBC_DRIVER_PATH=/opt/drivers
ROW_LIMIT_SUFFIX=FETCH FIRST ${row_limit} ROWS ONLY
```

### Example 3: Proprietary JDBC Driver from Single JAR

```bash
# Environment variables (load specific JAR file)
CONNECTOR_DATASOURCE_TYPE=custom_proprietary_db
CONNECTOR_LABEL=Proprietary Database
CONNECTOR_DESCRIPTION=Custom proprietary database connector
JDBC_DRIVER_CLASS=com.vendor.jdbc.ProprietaryDriver
JDBC_DRIVER_PATH=/opt/drivers/proprietary-jdbc-1.0.jar
ROW_LIMIT_SUFFIX=LIMIT ${row_limit}
```

### Example 4: Auto-detect Driver (No Custom Configuration)

```bash
# Environment variables (use built-in driver detection)
CONNECTOR_DATASOURCE_TYPE=custom_postgres_analytics
CONNECTOR_LABEL=PostgreSQL Analytics
CONNECTOR_DESCRIPTION=PostgreSQL database for analytics
# JDBC_DRIVER_CLASS not set - will auto-detect from jdbc:postgresql:// URL
```

## Docker Deployment

### Using Docker Run (with Custom Driver)

```bash
docker run -d \
  -e CONNECTOR_DATASOURCE_TYPE=custom_mysql_prod \
  -e CONNECTOR_LABEL="Production MySQL" \
  -e JDBC_DRIVER_CLASS=com.mysql.cj.jdbc.Driver \
  -e JDBC_DRIVER_PATH=/opt/drivers \
  -v /path/to/drivers:/opt/drivers \
  your-connector-image:latest
```

### Using Docker Run (with Single JAR)

```bash
docker run -d \
  -e CONNECTOR_DATASOURCE_TYPE=custom_proprietary \
  -e CONNECTOR_LABEL="Proprietary DB" \
  -e JDBC_DRIVER_CLASS=com.vendor.jdbc.Driver \
  -e JDBC_DRIVER_PATH=/opt/drivers/vendor-jdbc.jar \
  -v /path/to/vendor-jdbc.jar:/opt/drivers/vendor-jdbc.jar \
  your-connector-image:latest
```

### Using Docker Compose

```yaml
version: '3.8'
services:
  jdbc-connector:
    image: your-connector-image:latest
    environment:
      CONNECTOR_DATASOURCE_TYPE: custom_mysql_prod
      CONNECTOR_LABEL: Production MySQL
      CONNECTOR_DESCRIPTION: MySQL production database
      JDBC_DRIVER_CLASS: com.mysql.cj.jdbc.Driver
      JDBC_DRIVER_PATH: /opt/drivers
      ROW_LIMIT_SUFFIX: LIMIT $${row_limit}
    volumes:
      - /path/to/drivers:/opt/drivers
```

### Using Environment File

Create a `.env` file:

```bash
# .env file
CONNECTOR_DATASOURCE_TYPE=custom_postgres_analytics
CONNECTOR_LABEL=PostgreSQL Analytics
CONNECTOR_DESCRIPTION=PostgreSQL database for analytics
JDBC_DRIVER_CLASS=org.postgresql.Driver
JDBC_DRIVER_PATH=/opt/drivers
ROW_LIMIT_SUFFIX=LIMIT ${row_limit}
```

Then use it with Docker:

```bash
docker run -d \
  --env-file .env \
  -v /path/to/drivers:/opt/drivers \
  your-connector-image:latest
```

## Kubernetes Deployment

### Using ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: jdbc-connector-config
data:
  CONNECTOR_DATASOURCE_TYPE: custom_mysql_prod
  CONNECTOR_LABEL: Production MySQL
  CONNECTOR_DESCRIPTION: MySQL production database
  JDBC_DRIVER_CLASS: com.mysql.cj.jdbc.Driver
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jdbc-connector
spec:
  template:
    spec:
      containers:
      - name: connector
        image: your-connector-image:latest
        envFrom:
        - configMapRef:
            name: jdbc-connector-config
        volumeMounts:
        - name: drivers
          mountPath: /opt/drivers
      volumes:
      - name: drivers
        hostPath:
          path: /path/to/drivers
```

### Using Secrets (for sensitive data)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: jdbc-connector-secret
type: Opaque
stringData:
  JDBC_DRIVER_CLASS: com.mysql.cj.jdbc.Driver
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jdbc-connector
spec:
  template:
    spec:
      containers:
      - name: connector
        image: your-connector-image:latest
        env:
        - name: CONNECTOR_DATASOURCE_TYPE
          value: custom_mysql_prod
        - name: CONNECTOR_LABEL
          value: Production MySQL
        - name: JDBC_DRIVER_CLASS
          valueFrom:
            secretKeyRef:
              name: jdbc-connector-secret
              key: JDBC_DRIVER_CLASS
        - name: JDBC_DRIVER_PATH
          value: /opt/drivers
        volumeMounts:
        - name: drivers
          mountPath: /opt/drivers
      volumes:
      - name: drivers
        hostPath:
          path: /path/to/drivers
```

## Driver JAR Files

The connector now supports **dynamic driver loading** using the `JDBC_DRIVER_PATH` environment variable. You have two options:

### Option 1: Mount Driver Directory (Recommended)

Mount a volume containing driver JARs and set `JDBC_DRIVER_PATH`:

```bash
# Docker
docker run -d \
  -e JDBC_DRIVER_CLASS=com.vendor.jdbc.Driver \
  -e JDBC_DRIVER_PATH=/opt/drivers \
  -v /host/path/to/drivers:/opt/drivers \
  your-connector-image:latest
```

### Option 2: Build Drivers into Image

Include driver JARs in the Docker image:

```dockerfile
FROM your-base-image

# Create drivers directory
RUN mkdir -p /opt/drivers

# Copy driver JARs into the image
COPY drivers/*.jar /opt/drivers/

# Set default environment variables (can be overridden at runtime)
ENV CONNECTOR_DATASOURCE_TYPE=custom_genericjdbc
ENV CONNECTOR_LABEL="Generic JDBC (custom)"
ENV JDBC_DRIVER_PATH=/opt/drivers
```

### How It Works

The connector uses a **URLClassLoader** to dynamically load driver JARs:

1. If `JDBC_DRIVER_PATH` points to a **directory**, all `.jar` files in that directory are loaded
2. If `JDBC_DRIVER_PATH` points to a **single JAR file**, only that file is loaded
3. If `JDBC_DRIVER_PATH` is not set, the driver class must be in the application's classpath
4. The driver class specified in `JDBC_DRIVER_CLASS` is then loaded from the custom ClassLoader

## Validation

After deployment, verify the configuration:

1. Check connector registration in CP4D
2. Verify the datasource type name matches `CONNECTOR_DATASOURCE_TYPE`
3. Verify the label appears correctly in the UI
4. Test connection with the configured driver

## Troubleshooting

### Driver Class Not Found

**Error**: `ClassNotFoundException` for the JDBC driver

**Solution**: 
- Ensure driver JAR is in `/opt/drivers` or classpath
- Verify `JDBC_DRIVER_CLASS` is the correct fully qualified class name
- Check volume mounts in Docker/Kubernetes configuration

### Invalid Datasource Type

**Error**: Datasource type not recognized

**Solution**:
- Verify `CONNECTOR_DATASOURCE_TYPE` follows naming conventions
- Check for special characters or spaces
- Ensure the connector has been properly registered

### Row Limit Not Working

**Error**: Row limit clause not applied correctly

**Solution**:
- Verify `ROW_LIMIT_PREFIX` or `ROW_LIMIT_SUFFIX` syntax
- Ensure `${row_limit}` placeholder is used correctly
- Check database-specific SQL syntax requirements

## Notes

- Environment variables take precedence over default values
- Changes to environment variables require container restart
- The connector must be re-registered in CP4D if `CONNECTOR_DATASOURCE_TYPE` changes
- Driver JARs must be compatible with the Java version used in the connector image