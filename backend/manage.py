
import os
import sys
import platform
from django.core.exceptions import ImproperlyConfigured

GDAL_LIBRARY_PATH = os.environ.get("GDAL_LIBRARY_PATH")

if GDAL_LIBRARY_PATH is None:
    if platform.system() == "Windows":
        GDAL_LIBRARY_PATH = "C:\\Users\\user\\miniconda3\\envs\\geo_env\\Library\\bin\\gdal.dll"
    else:
        # Linux default, you can also try "/usr/lib/libgdal.so" or similar
        GDAL_LIBRARY_PATH = "/usr/lib/libgdal.so"

# Check if the GDAL lib exists (only optionally — remove this check if not reliable)
if not os.path.exists(GDAL_LIBRARY_PATH):
    raise ImproperlyConfigured(f"GDAL library not found at {GDAL_LIBRARY_PATH}")



# GDAL_LIBRARY_PATH = r"C:\Users\user\miniconda3\envs\geo_env\Library\bin\gdal.dll"
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
