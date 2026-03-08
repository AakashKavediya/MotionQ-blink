"""
Profile manager: load/save/list/create profiles in MotionQ/profiles/ as JSON.
No internet. Each profile holds calibration data, dwell preferences, language.
"""
import json
import os

# MotionQ/profiles/ relative to this package (motionq/)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROFILES_DIR = os.path.join(_SCRIPT_DIR, "..", "MotionQ", "profiles")
_current_profile_path = None


def _ensure_profiles_dir():
    """Create profiles directory if it doesn't exist."""
    os.makedirs(_PROFILES_DIR, exist_ok=True)


def _profile_path(profile_name):
    """Get the full path for a profile JSON file."""
    return os.path.join(_PROFILES_DIR, f"{profile_name}.json")


def load_profile(profile_name):
    """
    Load profile by name. Returns dict with calibration, dwell, language, etc.
    Sets internal current profile path for calibration_manager.
    """
    global _current_profile_path
    path = _profile_path(profile_name)
    _current_profile_path = path
    
    if not os.path.exists(path):
        print(f"Profile '{profile_name}' not found, using defaults")
        return _default_profile_data()
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"Loaded profile: {profile_name}")
        return data
    except json.JSONDecodeError as e:
        print(f"Error parsing profile {profile_name}: {e}")
        return _default_profile_data()
    except Exception as e:
        print(f"Error loading profile {profile_name}: {e}")
        return _default_profile_data()


def save_profile(profile_name, data):
    """Save profile dict to MotionQ/profiles/<profile_name>.json."""
    try:
        _ensure_profiles_dir()
        path = _profile_path(profile_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved profile: {profile_name}")
        return True
    except Exception as e:
        print(f"Error saving profile {profile_name}: {e}")
        return False


def list_profiles():
    """Return list of profile names (without .json)."""
    _ensure_profiles_dir()
    names = []
    try:
        for f in os.listdir(_PROFILES_DIR):
            if f.endswith(".json"):
                names.append(f[:-5])
    except Exception as e:
        print(f"Error listing profiles: {e}")
    
    return sorted(names)


def create_profile(profile_name):
    """Create a new profile with default data."""
    try:
        _ensure_profiles_dir()
        path = _profile_path(profile_name)
        if os.path.exists(path):
            print(f"Profile '{profile_name}' already exists")
            return False
        
        data = _default_profile_data()
        return save_profile(profile_name, data)
    except Exception as e:
        print(f"Error creating profile {profile_name}: {e}")
        return False


def get_current_profile_path():
    """Return path to current profile file (for calibration_manager)."""
    return _current_profile_path


def _default_profile_data():
    """Return default profile data structure."""
    return {
        "gaze": {
            "calibration_points": [],
            "screen_width": 1920,
            "screen_height": 1080,
        },
        "head": {
            "neutral_y": None,
            "tilt_threshold": 20.0,  # Balanced default between 15 and 25
        },
        "dwell": {
            "duration_ms": 800,
            "entry_delay_ms": 300,
            "stability_radius": 25,
        },
        "lighting": {
            "brightness_offset": 0,
            "contrast_scale": 1.0,
        },
        "language": "EN",
    }


def delete_profile(profile_name):
    """Delete a profile by name."""
    try:
        path = _profile_path(profile_name)
        if os.path.exists(path):
            os.remove(path)
            print(f"Deleted profile: {profile_name}")
            return True
        else:
            print(f"Profile '{profile_name}' not found")
            return False
    except Exception as e:
        print(f"Error deleting profile {profile_name}: {e}")
        return False


def update_profile(profile_name, updates):
    """
    Update specific fields in a profile.
    updates should be a dict with nested structure matching profile schema.
    """
    try:
        data = load_profile(profile_name)
        
        # Deep merge updates
        for key, value in updates.items():
            if key in data and isinstance(data[key], dict) and isinstance(value, dict):
                data[key].update(value)
            else:
                data[key] = value
        
        return save_profile(profile_name, data)
    except Exception as e:
        print(f"Error updating profile {profile_name}: {e}")
        return False


def profile_exists(profile_name):
    """Check if a profile exists."""
    path = _profile_path(profile_name)
    return os.path.exists(path)