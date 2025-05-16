from django.core.management.base import BaseCommand
from django.contrib.gis.gdal import DataSource
from urbananalytics.models import UnionCouncil
from django.contrib.gis.geos import MultiPolygon, Polygon

class Command(BaseCommand):
    help = 'Load union councils from shapefile into the database'

    def add_arguments(self, parser):
        parser.add_argument('shapefile', type=str, help='Path to the .shp file')

    def handle(self, *args, **kwargs):
        shapefile_path = kwargs['shapefile']
        ds = DataSource(shapefile_path)
        layer = ds[0]

        print("Fields in shapefile:", layer.fields)

        count = 0
        for feature in layer:
            city_name = feature.get('DISTRICT')  # Change if needed
            uc_name = feature.get('UC')
            geom = feature.geom.geos

            if isinstance(geom, Polygon):
                geom = MultiPolygon(geom)

            if not city_name or not uc_name:
                self.stdout.write(self.style.WARNING("Skipping feature with missing data"))
                continue

            obj, created = UnionCouncil.objects.get_or_create(
                city_name=city_name.strip(),
                uc_name=uc_name.strip(),
                defaults={'geometry': geom}
            )

            if created:
                count += 1

        self.stdout.write(self.style.SUCCESS(f"{count} union councils added."))
