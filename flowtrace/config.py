_CONFIG = {
    "show_args": True,
    "show_result": True,
    "show_timing": True,
}

def get_config() -> dict:
    return _CONFIG

def config(**kwargs):
    _CONFIG.update(kwargs)