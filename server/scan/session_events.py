import sys

# Register NetAlertX directories
INSTALL_PATH="/app"
sys.path.extend([f"{INSTALL_PATH}/server"])

import conf
from scan.device_handling import create_new_devices, print_scan_stats, save_scanned_devices, exclude_ignored_devices, update_devices_data_from_scan
from helper import timeNowTZ, get_setting_value
from db.db_helper import print_table_schema
from logger import mylog, Logger
from messaging.reporting import skip_repeated_notifications


# Make sure log level is initialized correctly
Logger(get_setting_value('LOG_LEVEL'))

#===============================================================================
# SCAN NETWORK
#===============================================================================

def process_scan (db):

    # Apply exclusions
    mylog('verbose','[Process Scan]  Exclude ignored devices')     
    exclude_ignored_devices (db)    

    # Load current scan data
    mylog('verbose','[Process Scan]  Processing scan results')     
    save_scanned_devices (db)    

    db.commitDB()
    
    # Print stats
    mylog('none','[Process Scan] Print Stats')
    print_scan_stats(db)
    mylog('none','[Process Scan] Stats end')

    # Create Events    
    mylog('verbose','[Process Scan] Sessions Events (connect / disconnect)')
    insert_events(db)

    # Create New Devices
    # after create events -> avoid 'connection' event
    mylog('verbose','[Process Scan] Creating new devices')
    create_new_devices (db)

    # Update devices info
    mylog('verbose','[Process Scan] Updating Devices Info')
    update_devices_data_from_scan (db)

    # Pair session events (Connection / Disconnection)
    mylog('verbose','[Process Scan] Pairing session events (connection / disconnection) ')
    pair_sessions_events(db)  
  
    # Sessions snapshot
    mylog('verbose','[Process Scan] Creating sessions snapshot')
    create_sessions_snapshot (db)

    # Sessions snapshot
    mylog('verbose','[Process Scan] Inserting scan results into Online_History')
    insertOnlineHistory(db)
  
    # Skip repeated notifications
    mylog('verbose','[Process Scan] Skipping repeated notifications')
    skip_repeated_notifications (db)

    # Clear current scan as processed 
    # 🐛 CurrentScan DEBUG: comment out below when debugging to keep the CurrentScan table after restarts/scan finishes
    db.sql.execute ("DELETE FROM CurrentScan") 
  
    # Commit changes    
    db.commitDB()

#-------------------------------------------------------------------------------
def pair_sessions_events (db):

    sql = db.sql #TO-DO
    # Pair Connection / New Device events

    mylog('debug','[Pair Session] - 1 Connections / New Devices')
    sql.execute ("""UPDATE Events
                    SET eve_PairEventRowid =
                       (SELECT ROWID
                        FROM Events AS EVE2
                        WHERE EVE2.eve_EventType IN ('New Device', 'Connected', 'Down Reconnected',
                            'Device Down', 'Disconnected')
                           AND EVE2.eve_MAC = Events.eve_MAC
                           AND EVE2.eve_Datetime > Events.eve_DateTime
                        ORDER BY EVE2.eve_DateTime ASC LIMIT 1)
                    WHERE eve_EventType IN ('New Device', 'Connected', 'Down Reconnected')
                    AND eve_PairEventRowid IS NULL
                 """ )

    # Pair Disconnection / Device Down
    mylog('debug','[Pair Session] - 2 Disconnections')
    sql.execute ("""UPDATE Events
                    SET eve_PairEventRowid =
                        (SELECT ROWID
                         FROM Events AS EVE2
                         WHERE EVE2.eve_PairEventRowid = Events.ROWID)
                    WHERE eve_EventType IN ('Device Down', 'Disconnected')
                      AND eve_PairEventRowid IS NULL
                 """ )


    mylog('debug','[Pair Session] Pair session end')
    db.commitDB()


#-------------------------------------------------------------------------------
def create_sessions_snapshot (db):
    sql = db.sql #TO-DO

    # Clean sessions snapshot
    mylog('debug','[Sessions Snapshot] - 1 Clean')
    sql.execute ("DELETE FROM SESSIONS" )

    # Insert sessions
    mylog('debug','[Sessions Snapshot] - 2 Insert')
    sql.execute ("""INSERT INTO Sessions
                    SELECT * FROM Convert_Events_to_Sessions""" )

    mylog('debug','[Sessions Snapshot] Sessions end')
    db.commitDB()


#-------------------------------------------------------------------------------
def insert_events (db):
    sql = db.sql #TO-DO
    startTime = timeNowTZ()    
    
    # Check device down
    mylog('debug','[Events] - 1 - Devices down')
    sql.execute (f"""INSERT INTO Events (eve_MAC, eve_IP, eve_DateTime,
                        eve_EventType, eve_AdditionalInfo,
                        eve_PendingAlertEmail)
                    SELECT devMac, devLastIP, '{startTime}', 'Device Down', '', 1
                    FROM Devices 
                    WHERE devAlertDown != 0
                      AND devPresentLastScan = 1                      
                      AND NOT EXISTS (SELECT 1 FROM CurrentScan
                                      WHERE devMac = cur_MAC
                                         ) """)

    # Check new Connections or Down Reconnections
    mylog('debug','[Events] - 2 - New Connections')
    sql.execute (f"""    INSERT INTO Events (eve_MAC, eve_IP, eve_DateTime,
                                            eve_EventType, eve_AdditionalInfo,
                                            eve_PendingAlertEmail)
                        SELECT DISTINCT c.cur_MAC, c.cur_IP, '{startTime}', 
                                        CASE 
                                            WHEN last_event.eve_EventType = 'Device Down' and  last_event.eve_PendingAlertEmail = 0 THEN 'Down Reconnected' 
                                            ELSE 'Connected' 
                                        END,
                                        '',
                                        1
                        FROM CurrentScan AS c 
                        LEFT JOIN LatestEventsPerMAC AS last_event ON c.cur_MAC = last_event.eve_MAC 
                        WHERE last_event.devPresentLastScan = 0 OR last_event.eve_MAC IS NULL
                        """)

    # Check disconnections
    mylog('debug','[Events] - 3 - Disconnections')
    sql.execute (f"""INSERT INTO Events (eve_MAC, eve_IP, eve_DateTime,
                        eve_EventType, eve_AdditionalInfo,
                        eve_PendingAlertEmail)
                    SELECT devMac, devLastIP, '{startTime}', 'Disconnected', '',
                        devAlertEvents
                    FROM Devices
                    WHERE devAlertDown = 0
                      AND devPresentLastScan = 1
                      AND NOT EXISTS (SELECT 1 FROM CurrentScan
                                      WHERE devMac = cur_MAC
                                         ) """)

    # Check IP Changed
    mylog('debug','[Events] - 4 - IP Changes')
    sql.execute (f"""INSERT INTO Events (eve_MAC, eve_IP, eve_DateTime,
                        eve_EventType, eve_AdditionalInfo,
                        eve_PendingAlertEmail)
                    SELECT cur_MAC, cur_IP, '{startTime}', 'IP Changed',
                        'Previous IP: '|| devLastIP, devAlertEvents
                    FROM Devices, CurrentScan
                    WHERE devMac = cur_MAC                        
                      AND devLastIP <> cur_IP """ )
    mylog('debug','[Events] - Events end')
    
    
#-------------------------------------------------------------------------------
def insertOnlineHistory(db):
    sql = db.sql  # TO-DO: Implement sql object

    scanTimestamp = timeNowTZ()

    # Query to fetch all relevant device counts in one go
    query = """
    SELECT
        COUNT(*) AS allDevices,
        COALESCE(SUM(CASE WHEN devIsArchived = 1 THEN 1 ELSE 0 END), 0) AS archivedDevices,
        COALESCE(SUM(CASE WHEN devPresentLastScan = 1 THEN 1 ELSE 0 END), 0) AS onlineDevices,
        COALESCE(SUM(CASE WHEN devPresentLastScan = 0 AND devAlertDown = 1 THEN 1 ELSE 0 END), 0) AS downDevices
    FROM Devices
    """
    
    deviceCounts = db.read(query)[0]  # Assuming db.read returns a list of rows, take the first (and only) row

    allDevices = deviceCounts['allDevices']
    archivedDevices = deviceCounts['archivedDevices']
    onlineDevices = deviceCounts['onlineDevices']
    downDevices = deviceCounts['downDevices']
    
    offlineDevices = allDevices - archivedDevices - onlineDevices

    # Prepare the insert query using parameterized inputs
    insert_query = """
        INSERT INTO Online_History (Scan_Date, Online_Devices, Down_Devices, All_Devices, Archived_Devices, Offline_Devices)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    
    mylog('debug', f'[Presence graph] Sql query: {insert_query} with values: {scanTimestamp}, {onlineDevices}, {downDevices}, {allDevices}, {archivedDevices}, {offlineDevices}')

    # Debug output 
    print_table_schema(db, "Online_History")

    # Insert the gathered data into the history table
    sql.execute(insert_query, (scanTimestamp, onlineDevices, downDevices, allDevices, archivedDevices, offlineDevices))

    db.commitDB()


