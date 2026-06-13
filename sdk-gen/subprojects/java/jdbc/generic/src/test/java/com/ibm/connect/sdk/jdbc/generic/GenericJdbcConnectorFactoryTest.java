/* *************************************************** */
/*                                                     */
/* (C) Copyright IBM Corp. 2026                        */
/*                                                     */
/* *************************************************** */
package com.ibm.connect.sdk.jdbc.generic;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

import org.junit.Test;

import com.ibm.wdp.connect.common.sdk.api.models.CustomFlightDatasourceTypes;

public class GenericJdbcConnectorFactoryTest
{
    @Test
    public void testGetDatasourceTypesInitializesDatasourceTypesList()
    {
        final CustomFlightDatasourceTypes datasourceTypes = new GenericJdbcConnectorFactory().getDatasourceTypes();

        assertNotNull(datasourceTypes);
        assertNotNull(datasourceTypes.getDatasourceTypes());
        assertEquals(1, datasourceTypes.getDatasourceTypes().size());
        assertNotNull(datasourceTypes.getDatasourceTypes().get(0));
        assertNotNull(datasourceTypes.getDatasourceTypes().get(0).getName());
    }
}

// Made with Bob
