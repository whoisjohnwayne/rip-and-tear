"""
Drive database for overread capability
"""

# Example drive database (expand as needed)
DRIVE_DB = {
    # 'drive_id': {'overread': True/False}
    'PLEXTOR_DVDR_PX-230A': {'overread': True},
    'TSSTcorp_CDDVDW_SH-S223C': {'overread': False},
    # Add more drives here
}

def get_drive_id(device_path):
    """Stub: Return a unique drive ID string for the given device path"""
    # In real code, use e.g. 'cd-drive' or 'sg_inq' to get vendor/model
    # Here, just return a placeholder
    return 'PLEXTOR_DVDR_PX-230A'


def drive_supports_overread(device_path):
    drive_id = get_drive_id(device_path)
    info = DRIVE_DB.get(drive_id, {})
    return info.get('overread', False)
