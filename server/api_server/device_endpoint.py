#!/usr/bin/env python

import json
import subprocess
import argparse
import os
import pathlib
import sys
from datetime import datetime
from flask import jsonify, request

# Register NetAlertX directories
INSTALL_PATH="/app"
sys.path.extend([f"{INSTALL_PATH}/front/plugins", f"{INSTALL_PATH}/server"])

from database import get_temp_db_connection
from helper import row_to_json, get_date_from_period, is_random_mac, format_date, get_setting_value


# --------------------------
# Device Endpoints Functions
# --------------------------

def get_device_data(mac):
    """Fetch device info with children, event stats, and presence calculation."""

    # Open temporary connection for this request
    conn = get_temp_db_connection()
    cur = conn.cursor()
    
    # Special case for new device
    if mac.lower() == "new":
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        device_data = {
            "devMac": "",
            "devName": "",
            "devOwner": "",
            "devType": "",
            "devVendor": "",
            "devFavorite": 0,
            "devGroup": "",
            "devComments": "",
            "devFirstConnection": now,
            "devLastConnection": now,
            "devLastIP": "",
            "devStaticIP": 0,
            "devScan": 0,
            "devLogEvents": 0,
            "devAlertEvents": 0,
            "devAlertDown": 0,
            "devParentRelType": "default",
            "devReqNicsOnline": 0,
            "devSkipRepeated": 0,
            "devLastNotification": "",
            "devPresentLastScan": 0,
            "devIsNew": 1,
            "devLocation": "",
            "devIsArchived": 0,
            "devParentMAC": "",
            "devParentPort": "",
            "devIcon": "",
            "devGUID": "",
            "devSite": "",
            "devSSID": "",
            "devSyncHubNode": "",
            "devSourcePlugin": "",
            "devCustomProps": "",
            "devStatus": "Unknown",
            "devIsRandomMAC": False,
            "devSessions": 0,
            "devEvents": 0,
            "devDownAlerts": 0,
            "devPresenceHours": 0,
            "devFQDN": ""
        }
        return jsonify(device_data)

    # Compute period date for sessions/events
    period = request.args.get('period', '')  # e.g., '7 days', '1 month', etc.
    period_date_sql = get_date_from_period(period)
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Fetch device info + computed fields
    sql = f"""
    SELECT
        d.*,
        CASE
            WHEN d.devAlertDown != 0 AND d.devPresentLastScan = 0 THEN 'Down'
            WHEN d.devPresentLastScan = 1 THEN 'On-line'
            ELSE 'Off-line'
        END AS devStatus,

        (SELECT COUNT(*) FROM Sessions 
         WHERE ses_MAC = d.devMac AND (
            ses_DateTimeConnection >= {period_date_sql} OR 
            ses_DateTimeDisconnection >= {period_date_sql} OR 
            ses_StillConnected = 1
         )) AS devSessions,

        (SELECT COUNT(*) FROM Events
         WHERE eve_MAC = d.devMac AND eve_DateTime >= {period_date_sql}
           AND eve_EventType NOT IN ('Connected','Disconnected')) AS devEvents,

        (SELECT COUNT(*) FROM Events
         WHERE eve_MAC = d.devMac AND eve_DateTime >= {period_date_sql}
           AND eve_EventType = 'Device Down') AS devDownAlerts,

        (SELECT CAST(MAX(0, SUM(
            julianday(IFNULL(ses_DateTimeDisconnection,'{current_date}')) -
            julianday(CASE WHEN ses_DateTimeConnection < {period_date_sql}
                           THEN {period_date_sql} ELSE ses_DateTimeConnection END)
        ) * 24) AS INT)
         FROM Sessions
         WHERE ses_MAC = d.devMac
           AND ses_DateTimeConnection IS NOT NULL
           AND (ses_DateTimeDisconnection IS NOT NULL OR ses_StillConnected = 1)
           AND (ses_DateTimeConnection >= {period_date_sql}
                OR ses_DateTimeDisconnection >= {period_date_sql} OR ses_StillConnected = 1)
        ) AS devPresenceHours

    FROM Devices d
    WHERE d.devMac = ? OR CAST(d.rowid AS TEXT) = ?
    """
    # Fetch device
    cur.execute(sql, (mac, mac))
    row = cur.fetchone()
    if not row:
        return jsonify({"error": "Device not found"}), 404

    device_data = row_to_json(list(row.keys()), row)
    device_data['devFirstConnection'] = format_date(device_data['devFirstConnection'])
    device_data['devLastConnection'] = format_date(device_data['devLastConnection'])
    device_data['devIsRandomMAC'] = is_random_mac(device_data['devMac'])

    # Fetch children
    cur.execute("SELECT * FROM Devices WHERE devParentMAC = ? ORDER BY devPresentLastScan DESC", ( device_data['devMac'],))
    children_rows = cur.fetchall()
    children = [row_to_json(list(r.keys()), r) for r in children_rows]
    children_nics = [c for c in children if c.get("devParentRelType") == "nic"]

    device_data['devChildrenDynamic'] = children
    device_data['devChildrenNicsDynamic'] = children_nics

    conn.close()

    return jsonify(device_data)


def set_device_data(mac, data):
    """Update or create a device."""
    if data.get("createNew", False):
        sql = """
        INSERT INTO Devices (
            devMac, devName, devOwner, devType, devVendor, devIcon,
            devFavorite, devGroup, devLocation, devComments,
            devParentMAC, devParentPort, devSSID, devSite,
            devStaticIP, devScan, devAlertEvents, devAlertDown,
            devParentRelType, devReqNicsOnline, devSkipRepeated,
            devIsNew, devIsArchived, devLastConnection,
            devFirstConnection, devLastIP, devGUID, devCustomProps,
            devSourcePlugin
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = (
            mac,
            data.get("name", ""),
            data.get("owner", ""),
            data.get("type", ""),
            data.get("vendor", ""),
            data.get("icon", ""),
            data.get("favorite", 0),
            data.get("group", ""),
            data.get("location", ""),
            data.get("comments", ""),
            data.get("networknode", ""),
            data.get("networknodeport", ""),
            data.get("ssid", ""),
            data.get("networksite", ""),
            data.get("staticIP", 0),
            data.get("scancycle", 0),
            data.get("alertevents", 0),
            data.get("alertdown", 0),
            data.get("relType", "default"),
            data.get("reqNics", 0),
            data.get("skiprepeated", 0),
            data.get("newdevice", 0),
            data.get("archived", 0),
            data.get("devLastConnection", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            data.get("devFirstConnection", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            data.get("ip", ""),
            data.get("devGUID", ""),
            data.get("devCustomProps", ""),
            "DUMMY"
        )
    else:
        sql = """
        UPDATE Devices SET
            devName=?, devOwner=?, devType=?, devVendor=?, devIcon=?,
            devFavorite=?, devGroup=?, devLocation=?, devComments=?,
            devParentMAC=?, devParentPort=?, devSSID=?, devSite=?,
            devStaticIP=?, devScan=?, devAlertEvents=?, devAlertDown=?,
            devParentRelType=?, devReqNicsOnline=?, devSkipRepeated=?,
            devIsNew=?, devIsArchived=?, devCustomProps=?
        WHERE devMac=?
        """
        values = (
            data.get("name", ""),
            data.get("owner", ""),
            data.get("type", ""),
            data.get("vendor", ""),
            data.get("icon", ""),
            data.get("favorite", 0),
            data.get("group", ""),
            data.get("location", ""),
            data.get("comments", ""),
            data.get("networknode", ""),
            data.get("networknodeport", ""),
            data.get("ssid", ""),
            data.get("networksite", ""),
            data.get("staticIP", 0),
            data.get("scancycle", 0),
            data.get("alertevents", 0),
            data.get("alertdown", 0),
            data.get("relType", "default"),
            data.get("reqNics", 0),
            data.get("skiprepeated", 0),
            data.get("newdevice", 0),
            data.get("archived", 0),
            data.get("devCustomProps", ""),
            mac
        )

    conn = get_temp_db_connection()
    cur = conn.cursor()
    cur.execute(sql, values)
    conn.commit()
    conn.close()
    return jsonify({"success": True})



def delete_device(mac):
    """Delete a device by MAC."""
    conn = get_temp_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM Devices WHERE devMac=?", (mac,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


def delete_device_events(mac):
    """Delete all events for a device."""
    conn = get_temp_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM Events WHERE eve_MAC=?", (mac,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


def reset_device_props(mac, data=None):
    """Reset device custom properties to default."""
    default_props = get_setting_value("NEWDEV_devCustomProps")
    conn = get_temp_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE Devices SET devCustomProps=? WHERE devMac=?",
        (default_props, mac),
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})

