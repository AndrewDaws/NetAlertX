#!/usr/bin/env python

import os
import pathlib
import argparse
import sys
import hashlib
import subprocess
import csv
import sqlite3
from io import StringIO
from datetime import datetime

# Register NetAlertX directories
INSTALL_PATH="/app"
sys.path.extend([f"{INSTALL_PATH}/front/plugins", f"{INSTALL_PATH}/server"])

from plugin_helper import Plugin_Object, Plugin_Objects, decodeBase64, handleEmpty
from logger import mylog, Logger, append_line_to_file
from helper import timeNowTZ, get_setting_value 
from const import logPath, applicationPath, fullDbPath
from scan.device_handling import query_MAC_vendor
import conf
from pytz import timezone

# Make sure the TIMEZONE for logging is correct
conf.tz = timezone(get_setting_value('TIMEZONE'))

# Make sure log level is initialized correctly
Logger(get_setting_value('LOG_LEVEL'))

pluginName = 'VNDRPDT'


LOG_PATH = logPath + '/plugins'
LOG_FILE = os.path.join(LOG_PATH, f'script.{pluginName}.log')
RESULT_FILE = os.path.join(LOG_PATH, f'last_result.{pluginName}.log')

def main():   

    mylog('verbose', ['[VNDRPDT] In script']) 

    # Get newest DB   
    update_vendor_database() 

    # Resolve missing vendors
    plugin_objects = Plugin_Objects(RESULT_FILE)

    plugin_objects = update_vendors(fullDbPath, plugin_objects)

    plugin_objects.write_result_file()
    
    mylog('verbose', ['[VNDRPDT] Update complete'])   
    
    return 0

#===============================================================================
# Update device vendors database
#===============================================================================
def update_vendor_database():

    # Update vendors DB (iab oui)
    mylog('verbose', ['    Updating vendors DB (iab & oui)'])    
    update_args = ['sh', applicationPath + '/services/update_vendors.sh']

    # Execute command     
    try:
        # try runnning a subprocess safely
        update_output = subprocess.check_output (update_args)
    except subprocess.CalledProcessError as e:
        # An error occured, handle it
        mylog('verbose', ['    FAILED: Updating vendors DB, set LOG_LEVEL=debug for more info'])  
        mylog('verbose', [e.output])        

# ------------------------------------------------------------------------------
# resolve missing vendors
def update_vendors (dbPath, plugin_objects): 
   
    # Connect to the App SQLite database
    conn = sqlite3.connect(dbPath)
    sql  = conn.cursor()

    # Initialize variables
    recordsToUpdate = []
    ignored = 0
    notFound = 0

    
    mylog('verbose', ['    Searching devices vendor']) 

    # Get devices without a vendor
    sql.execute  ("""SELECT 
                            devMac, 
                            devLastIP, 
                            devName, 
                            devVendor 
                            FROM Devices
                            WHERE   devVendor      = '(unknown)' 
                                    OR devVendor   = '(Unknown)' 
                                    OR devVendor   = ''
                                    OR devVendor   IS NULL
                        """)
    devices = sql.fetchall() 
    conn.commit()    

    # Close the database connection
    conn.close()  

    # All devices loop
    for device in devices:
        # Search vendor in HW Vendors DB
        vendor = query_MAC_vendor (device[0])
        if vendor == -1 :
            notFound += 1
        elif vendor == -2 :
            ignored += 1
        else :
            plugin_objects.add_object(
                primaryId   = handleEmpty(device[0]),    # MAC (Device Name)
                secondaryId = handleEmpty(device[1]),    # IP Address (always 0.0.0.0)
                watched1    = handleEmpty(vendor),  
                watched2    = handleEmpty(device[2]),    # Device name
                watched3    = "",
                watched4    = "",
                extra       = "",            
                foreignKey  = handleEmpty(device[0])           
            )            
            
    # Print log    
    mylog('verbose', ["    Devices Ignored             : ", ignored])
    mylog('verbose', ["    Devices with missing vendor : ", len(devices)])
    mylog('verbose', ["    Vendors Not Found           : ", notFound])
    mylog('verbose', ["    Vendors updated             : ", len(plugin_objects) ])


    return plugin_objects

    

#===============================================================================
# BEGIN
#===============================================================================
if __name__ == '__main__':
    main()