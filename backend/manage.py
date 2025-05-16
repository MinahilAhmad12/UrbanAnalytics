
import os
import sys
from django.core.exceptions import ImproperlyConfigured
from django.contrib.gis import gdal

if not gdal.HAS_GDAL:
    raise ImproperlyConfigured("GDAL is required but not properly configured.")




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
