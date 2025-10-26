#!/usr/bin/env python

import json
import subprocess
import argparse
import os
import pathlib
import sys
from datetime import datetime

# Register NetAlertX directories
INSTALL_PATH = "/app"
sys.path.extend([f"{INSTALL_PATH}/front/plugins", f"{INSTALL_PATH}/server"])

import conf
from const import confFileName, logPath
from plugin_helper import Plugin_Objects
from logger import mylog, Logger, append_line_to_file
from helper import timeNowTZ, get_setting_value
from models.notification_instance import NotificationInstance
from database import DB
from pytz import timezone

# Make sure the TIMEZONE for logging is correct
conf.tz = timezone(get_setting_value('TIMEZONE'))

# Make sure log level is initialized correctly
Logger(get_setting_value('LOG_LEVEL'))

pluginName = 'TELEGRAM'

LOG_PATH = logPath + '/plugins'
RESULT_FILE = os.path.join(LOG_PATH, f'last_result.{pluginName}.log')




def main():
    mylog('verbose', [f'[{pluginName}](publisher) In script'])

    # Check if basic config settings supplied
    if check_config() == False:
        mylog('none', [
            f'[{pluginName}] ⚠ ERROR: Publisher notification gateway not set up correctly. Check your {confFileName} {pluginName}_* variables.'])
        return

    # Create a database connection
    db = DB()  # instance of class DB
    db.open()

    # Initialize the Plugin obj output file
    plugin_objects = Plugin_Objects(RESULT_FILE)

    # Create a NotificationInstance instance
    notifications = NotificationInstance(db)

    # Retrieve new notifications
    new_notifications = notifications.getNew()

    # Process the new notifications (see the Notifications DB table for structure or check the /php/server/query_json.php?file=table_notifications.json endpoint)
    for notification in new_notifications:
        # Send notification
        result = send(notification["Text"])

        # Log result
        plugin_objects.add_object(
            primaryId=pluginName,
            secondaryId=timeNowTZ(),
            watched1=notification["GUID"],
            watched2=result,
            watched3='null',
            watched4='null',
            extra='null',
            foreignKey=notification["GUID"]
        )

    plugin_objects.write_result_file()


# -------------------------------------------------------------------------------
def check_config():
    return True


# -------------------------------------------------------------------------------
def send(text):
    # limit = 1024 * 1024  # 1MB limit (1024 bytes * 1024 bytes = 1MB)
    limit = get_setting_value('TELEGRAM_SIZE')

    if len(text) > limit:
        payloadData = text[:limit] + " (text was truncated)"
    else:
        payloadData = text

    try:
        # try runnning a subprocess

        req = """curl --location 'https://api.telegram.org/bot%s/sendMessage' \\
        --header 'Content-Type: application/json' \\
        --data '{
            "chat_id": "%s",
            "text": "%s",
            "disable_notification": false
        }'""" % (get_setting_value('TELEGRAM_URL'), get_setting_value('TELEGRAM_HOST'), payloadData)

        mylog('debug', [req])

        p = subprocess.Popen(req, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        stdout, stderr = p.communicate()

        # write stdout and stderr into .log files for debugging if needed
        # Log the stdout and stderr
        mylog('debug', [stdout, stderr])

        # log result
        result = stdout

    except subprocess.CalledProcessError as e:
        # An error occurred, handle it
        mylog('none', [e.output])

        # log result
        result = e.output

    return result


if __name__ == '__main__':
    sys.exit(main())
