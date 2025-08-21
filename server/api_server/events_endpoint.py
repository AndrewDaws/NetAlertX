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
from helper import is_random_mac, format_date, get_setting_value, format_date_iso, format_event_date, timeNowTZ, mylog, ensure_datetime
from db.db_helper import row_to_json


# --------------------------
# Events Endpoints Functions
# --------------------------


def create_event(
    mac: str, 
    ip: str, 
    event_type: str = "Device Down", 
    additional_info: str = "", 
    pending_alert: int = 1,
    event_time: datetime | None = None
):
    """
    Insert a single event into the Events table and return a standardized JSON response.
    Exceptions will propagate to the caller.
    """
    conn = get_temp_db_connection()
    cur = conn.cursor()
    if isinstance(event_time, str):
        start_time = ensure_datetime(event_time)

    start_time = ensure_datetime(event_time)

    cur.execute("""
        INSERT INTO Events (eve_MAC, eve_IP, eve_DateTime, eve_EventType, eve_AdditionalInfo, eve_PendingAlertEmail)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (mac, ip, start_time, event_type, additional_info, pending_alert))

    conn.commit()
    conn.close()

    mylog("debug", f"[Events] Created event for {mac} ({event_type})")
    return jsonify({"success": True, "message": f"Created event for {mac}"})


def get_events(mac=None):
    """
    Fetch all events, or events for a specific MAC if provided.
    Returns JSON list of events.
    """
    conn = get_temp_db_connection()
    cur = conn.cursor()

    if mac:
        sql = "SELECT * FROM Events WHERE eve_MAC=? ORDER BY eve_DateTime DESC"
        cur.execute(sql, (mac,))
    else:
        sql = "SELECT * FROM Events ORDER BY eve_DateTime DESC"
        cur.execute(sql)

    rows = cur.fetchall()
    events = [row_to_json(list(r.keys()), r) for r in rows]

    conn.close()
    return jsonify({"success": True, "events": events})

def delete_events_30():
    """Delete all events older than 30 days"""

    conn = get_temp_db_connection()
    cur = conn.cursor()

    sql = "DELETE FROM Events WHERE eve_DateTime <= date('now', '-30 days')"
    cur.execute(sql)
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Deleted events older than 30 days"})

def delete_events():
    """Delete all events"""

    conn = get_temp_db_connection()
    cur = conn.cursor()

    sql = "DELETE FROM Events"
    cur.execute(sql)
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Deleted all events"})



