/* *************************************************** */
/*                                                     */
/* (C) Copyright IBM Corp. 2022, 2025                  */
/*                                                     */
/* *************************************************** */
package com.ibm.connect.sdk.jdbc.generic;

import java.io.File;
import java.io.Reader;
import java.io.StringReader;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.sql.Driver;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import org.apache.arrow.flight.Ticket;

import com.google.common.collect.HashBasedTable;
import com.google.common.collect.ImmutableMap;
import com.ibm.connect.sdk.jdbc.JdbcConnector;
import com.ibm.connect.sdk.jdbc.JdbcSourceInteraction;
import com.ibm.connect.sdk.jdbc.JdbcTargetInteraction;
import com.ibm.connect.sdk.util.Utils;
import com.ibm.wdp.connect.common.sdk.api.models.ConnectionProperties;
import com.ibm.wdp.connect.common.sdk.api.models.CustomFlightAssetDescriptor;

/**
 * A connector for connecting to a generic JDBC data source.
 */
public class GenericJdbcConnector extends JdbcConnector
{
    private static final Map<String, Class<? extends Driver>> DRIVER_CLASS_MAP = new HashMap<>();

    static {
        DRIVER_CLASS_MAP.put("db2", com.ibm.db2.jcc.DB2Driver.class);
        DRIVER_CLASS_MAP.put("derby", getDerbyDriverClass());
        DRIVER_CLASS_MAP.put("informix-sqli", com.informix.jdbc.IfxDriver.class);
        DRIVER_CLASS_MAP.put("mariadb", org.mariadb.jdbc.Driver.class);
        DRIVER_CLASS_MAP.put("mysql", com.mysql.cj.jdbc.Driver.class);
        DRIVER_CLASS_MAP.put("oracle", oracle.jdbc.OracleDriver.class);
        DRIVER_CLASS_MAP.put("postgresql", org.postgresql.Driver.class);
        DRIVER_CLASS_MAP.put("snowflake", net.snowflake.client.jdbc.SnowflakeDriver.class);
        DRIVER_CLASS_MAP.put("sqlserver", com.microsoft.sqlserver.jdbc.SQLServerDriver.class);
    }

    private static final HashBasedTable<String, String, String> LIMIT_CLAUSE_TABLE = HashBasedTable.create();

    static {
        LIMIT_CLAUSE_TABLE.put("db2", "suffix", "FETCH FIRST ${row_limit} ROWS ONLY");
        LIMIT_CLAUSE_TABLE.put("derby", "suffix", "FETCH FIRST ${row_limit} ROWS ONLY");
        LIMIT_CLAUSE_TABLE.put("informix-sqli", "suffix", "LIMIT ${row_limit}");
        LIMIT_CLAUSE_TABLE.put("mariadb", "suffix", "LIMIT ${row_limit}");
        LIMIT_CLAUSE_TABLE.put("mysql", "suffix", "LIMIT ${row_limit}");
        LIMIT_CLAUSE_TABLE.put("oracle", "suffix", "FETCH FIRST ${row_limit} ROWS ONLY");
        LIMIT_CLAUSE_TABLE.put("postgresql", "suffix", "LIMIT ${row_limit}");
        LIMIT_CLAUSE_TABLE.put("snowflake", "suffix", "LIMIT ${row_limit}");
        LIMIT_CLAUSE_TABLE.put("sqlserver", "prefix", "TOP ${row_limit}");
    }

    @SuppressWarnings("unchecked")
    private static Class<? extends Driver> getDerbyDriverClass()
    {

        try {
            return (Class<? extends Driver>) Class.forName("org.apache.derby.jdbc.ClientDriver");
        }
        catch (ClassNotFoundException e) {
            try {
                return (Class<? extends Driver>) Class.forName("org.apache.derby.client.ClientAutoloadedDriver");
            }
            catch (ClassNotFoundException e1) {
                return null;
            }
        }
    }

    /**
     * Creates a generic JDBC connector.
     *
     * @param properties
     *            connection properties
     */
    public GenericJdbcConnector(ConnectionProperties properties)
    {
        super(properties);

        // Validate the JDBC URL.
        final String jdbcUrl = connectionProperties.getProperty("jdbc_url");
        if (jdbcUrl == null) {
            throw new IllegalArgumentException(GenericJdbcMsgs.MISSING_PROPERTY.format("jdbc_url"));
        }
        final String driverName = getDriverName(jdbcUrl);
        if (!LIMIT_CLAUSE_TABLE.rowKeySet().contains(driverName)) {
            throw new IllegalArgumentException(GenericJdbcMsgs.INVALID_DRIVER.format(driverName, LIMIT_CLAUSE_TABLE.rowKeySet()));
        }
        final String rowLimitSupport = connectionProperties.getProperty("row_limit_support", "none");
        if ("prefix".equals(rowLimitSupport)) {
            if (connectionProperties.getProperty("row_limit_prefix") == null) {
                throw new IllegalArgumentException(GenericJdbcMsgs.MISSING_PROPERTY.format("row_limit_prefix"));
            }
        } else if ("suffix".equals(rowLimitSupport)) {
            if (connectionProperties.getProperty("row_limit_suffix") == null) {
                throw new IllegalArgumentException(GenericJdbcMsgs.MISSING_PROPERTY.format("row_limit_suffix"));
            }
        }
    }

    static String getDriverName(String jdbcUrl)
    {
        final Pattern pattern = Pattern.compile("jdbc:([^:]+):.*");
        final Matcher matcher = pattern.matcher(jdbcUrl);
        if (!matcher.matches()) {
            throw new IllegalArgumentException(GenericJdbcMsgs.INVALID_JDBC_URL.format(jdbcUrl));
        }
        return matcher.group(1);
    }

    static String getRowLimitPrefix(String driverName)
    {
        // Check for custom row limit prefix from environment variable
        final String customPrefix = System.getenv("ROW_LIMIT_PREFIX");
        if (customPrefix != null && !customPrefix.isEmpty()) {
            return customPrefix;
        }
        return LIMIT_CLAUSE_TABLE.get(driverName, "prefix");
    }

    static String getRowLimitSuffix(String driverName)
    {
        // Check for custom row limit suffix from environment variable
        final String customSuffix = System.getenv("ROW_LIMIT_SUFFIX");
        if (customSuffix != null && !customSuffix.isEmpty()) {
            return customSuffix;
        }
        return LIMIT_CLAUSE_TABLE.get(driverName, "suffix");
    }

    /**
     * Load JDBC driver JARs from a specified path or directory.
     *
     * @param driverPath Path to a JAR file or directory containing JAR files
     * @return Array of URLs for the ClassLoader
     * @throws Exception if path is invalid or JARs cannot be loaded
     */
    private URL[] loadDriverJars(String driverPath) throws Exception
    {
        final List<URL> urls = new ArrayList<>();
        final Path path = Paths.get(driverPath);
        
        if (!Files.exists(path)) {
            throw new IllegalArgumentException(
                GenericJdbcMsgs.INVALID_PROPERTY.format("JDBC_DRIVER_PATH: Path does not exist: " + driverPath));
        }
        
        if (Files.isDirectory(path)) {
            // Load all JAR files from directory
            try (Stream<Path> files = Files.list(path)) {
                files.filter(p -> p.toString().toLowerCase().endsWith(".jar"))
                     .forEach(p -> {
                         try {
                             urls.add(p.toUri().toURL());
                         } catch (Exception e) {
                             throw new RuntimeException("Failed to load JAR: " + p, e);
                         }
                     });
            }
            if (urls.isEmpty()) {
                throw new IllegalArgumentException(
                    GenericJdbcMsgs.INVALID_PROPERTY.format("JDBC_DRIVER_PATH: No JAR files found in directory: " + driverPath));
            }
        } else if (driverPath.toLowerCase().endsWith(".jar")) {
            // Single JAR file
            urls.add(path.toUri().toURL());
        } else {
            throw new IllegalArgumentException(
                GenericJdbcMsgs.INVALID_PROPERTY.format("JDBC_DRIVER_PATH: Must be a JAR file or directory: " + driverPath));
        }
        
        return urls.toArray(new URL[0]);
    }

    /**
     * {@inheritDoc}
     */
    @Override
    protected Driver getDriver() throws Exception
    {
        // Check for custom driver class from environment variable
        final String customDriverClass = System.getenv("JDBC_DRIVER_CLASS");
        final String customDriverPath = System.getenv("JDBC_DRIVER_PATH");
        
        if (customDriverClass != null && !customDriverClass.isEmpty()) {
            try {
                ClassLoader classLoader = getClass().getClassLoader();
                
                // If custom driver path is specified, create a URLClassLoader
                if (customDriverPath != null && !customDriverPath.isEmpty()) {
                    final URL[] urls = loadDriverJars(customDriverPath);
                    classLoader = new URLClassLoader(urls, classLoader);
                }
                
                // Load custom driver class dynamically
                final Class<?> driverClass = classLoader.loadClass(customDriverClass);
                return (Driver) driverClass.getDeclaredConstructor().newInstance();
            }
            catch (Exception e) {
                throw new IllegalArgumentException(
                    GenericJdbcMsgs.INVALID_PROPERTY.format("JDBC_DRIVER_CLASS: " + customDriverClass +
                        (customDriverPath != null ? ", JDBC_DRIVER_PATH: " + customDriverPath : "")), e);
            }
        }
        
        // Fall back to existing logic for known drivers
        final String jdbcUrl = connectionProperties.getProperty("jdbc_url");
        final String driverName = getDriverName(jdbcUrl);
        final Class<? extends Driver> driverClass = DRIVER_CLASS_MAP.get(driverName);
        if (driverClass == null) {
            throw new IllegalArgumentException(
                GenericJdbcMsgs.INVALID_DRIVER.format(driverName, DRIVER_CLASS_MAP.keySet()));
        }
        return driverClass.getDeclaredConstructor().newInstance();
    }

    /**
     * {@inheritDoc}
     */
    @Override
    protected String getConnectionURL()
    {
        return connectionProperties.getProperty("jdbc_url");
    }

    private Properties getJdbcProperties()
    {
        final Properties jdbcProperties = new Properties();
        String propertiesStr = connectionProperties.getProperty("jdbc_properties");
        if (propertiesStr != null) {
            final String truststoreFile = getTruststoreFile();
            if (truststoreFile != null) {
                final Map<String, String> tokens
                        = ImmutableMap.of("truststore_file", truststoreFile, "truststore_password", getTruststorePassword());
                propertiesStr = Utils.substituteTokens(propertiesStr, tokens);
            }
            propertiesStr = propertiesStr.replaceAll("\\\\", "\\\\\\\\");
            try (Reader reader = new StringReader(propertiesStr)) {
                jdbcProperties.load(reader);
            }
            catch (Exception e) {
                throw new IllegalArgumentException(GenericJdbcMsgs.INVALID_PROPERTY.format("jdbc_properties"), e);
            }
        }
        return jdbcProperties;
    }

    /**
     * {@inheritDoc}
     */
    @Override
    protected Properties getDriverConnectionProperties()
    {
        final Properties properties = super.getDriverConnectionProperties();
        properties.putAll(getJdbcProperties());
        return properties;
    }

    /**
     * {@inheritDoc}
     */
    @Override
    public JdbcSourceInteraction getSourceInteraction(CustomFlightAssetDescriptor asset, Ticket ticket) throws Exception
    {
        return new GenericJdbcSourceInteraction(this, asset, ticket);
    }

    /**
     * {@inheritDoc}
     */
    @Override
    public JdbcTargetInteraction getTargetInteraction(CustomFlightAssetDescriptor asset) throws Exception
    {
        return new GenericJdbcTargetInteraction(this, asset);
    }
}
