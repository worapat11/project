from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Set admin password'

    def handle(self, *args, **options):
        admin = User.objects.get(username='admin')
        admin.set_password('123456')
        admin.save()
        self.stdout.write(self.style.SUCCESS('✓ Admin password set to: 123456'))
