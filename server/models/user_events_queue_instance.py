import os
import sys

# Register NetAlertX directories
INSTALL_PATH="/app"
sys.path.extend([f"{INSTALL_PATH}/server"])

# Register NetAlertX modules
from const import pluginsPath, logPath, applicationPath, reportTemplatesPath
from logger import mylog

class UserEventsQueueInstance:
    """
    Handles the execution queue log file, allowing reading, writing,
    and removing processed events.
    """

    def __init__(self):
        self.log_path = logPath
        self.log_file = os.path.join(self.log_path, "execution_queue.log")


    def has_update_devices(self):
        lines = self.read_log()

        for line in lines:
            if 'update_api|devices' in line:
                return True

        return False

    def read_log(self):
        """
        Reads the log file and returns all lines.
        Returns an empty list if the file doesn't exist.
        """
        if not os.path.exists(self.log_file):
            mylog('none', ['[UserEventsQueueInstance] Log file not found: ', self.log_file])
            return []  # No log file, return empty list
        with open(self.log_file, "r") as file:
            return file.readlines()

    def write_log(self, lines):
        """
        Overwrites the log file with the provided lines.
        """
        with open(self.log_file, "w") as file:
            file.writelines(lines)

    def finalize_event(self, event):
        """
        Removes the first occurrence of the specified event from the log file.
        Retains all other lines untouched.

        Returns:
            bool: True if the event was found and removed, False otherwise.
        """
        if not os.path.exists(self.log_file):
            return False  # No log file to process

        updated_lines = []
        removed = False

        # Process the log file line by line
        with open(self.log_file, "r") as file:
            for line in file:
                columns = line.strip().split('|')[2:4]  # Extract event and param columns
                if len(columns) == 2:
                    event_name, _ = columns
                    if event_name == event and not removed:
                        # Skip this line (remove the processed event)
                        removed = True
                        continue
                updated_lines.append(line)

        # Write back the remaining lines
        self.write_log(updated_lines)


        mylog('minimal', ['[UserEventsQueueInstance] Processed event: ', event])

        return removed



