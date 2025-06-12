from datetime import datetime
import pytz # Make sure to install this: `pip install pytz`

def format_local_time(utc_timestamp_str: str, target_timezone_name: str) -> str:
    """
    Converts a UTC ISO 8601 timestamp string (e.g., '2025-06-11T11:52:47Z')
    to a formatted local time string based on the provided IANA timezone name.

    Args:
        utc_timestamp_str (str): The UTC timestamp string from GitHub.
        target_timezone_name (str): The IANA timezone name (e.g., 'Asia/Kolkata', 'America/New_York').

    Returns:
        str: The formatted local time string, or the original UTC string on error.
    """
    try:
        # 1. Parse the UTC timestamp string into a datetime object
        # The 'Z' at the end means UTC. datetime.strptime handles ISO 8601 parsing.
        utc_dt = datetime.strptime(utc_timestamp_str, "%Y-%m-%dT%H:%M:%SZ")

        # 2. Make the datetime object explicitly timezone-aware as UTC
        # pytz.utc represents the UTC timezone object.
        utc_dt = pytz.utc.localize(utc_dt)

        # 3. Define the target local timezone using pytz
        local_tz = pytz.timezone(target_timezone_name)

        # 4. Convert the UTC datetime to the local timezone
        local_dt = utc_dt.astimezone(local_tz)

        # 5. Format the local datetime object into a readable string
        # Example format: "June 11, 2025, 05:22 PM IST"
        # %B: Full month name, %d: Day of month, %Y: Year, %I: Hour (12-hour), %M: Minute, %p: AM/PM, %Z: Timezone name
        formatted_time = local_dt.strftime("%B %d, %Y, %I:%M %p %Z")
        return formatted_time

    except pytz.UnknownTimeZoneError:
        # If the provided timezone name is invalid, print a warning and fall back to UTC.
        print(f"⚠️ Warning: Unknown timezone '{target_timezone_name}' specified. Falling back to UTC.")
        # Re-parse as UTC and format simply
        utc_dt = datetime.strptime(utc_timestamp_str, "%Y-%m-%dT%H:%M:%SZ")
        utc_dt = pytz.utc.localize(utc_dt) # Still localize as UTC for consistency
        return utc_dt.strftime("%B %d, %Y, %I:%M %p UTC")
    except Exception as e:
        # Catch any other potential errors during parsing or conversion.
        print(f"❌ Error during time conversion for '{utc_timestamp_str}': {e}. Falling back to original UTC string.")
        return utc_timestamp_str # Return original string if conversion fails or for unexpected errors.