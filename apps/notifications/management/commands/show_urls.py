from django.core.management.base import BaseCommand
from django.urls import get_resolver


class Command(BaseCommand):
    help = 'Показывает все доступные URL пути'

    def handle(self, *args, **options):
        urlconf = get_resolver()

        def show_urls(urlpatterns, indent=0):
            for pattern in urlpatterns:
                spaces = ' ' * indent
                if hasattr(pattern, 'url_patterns'):
                    self.stdout.write(f"{spaces}{pattern.pattern} ->")
                    show_urls(pattern.url_patterns, indent + 2)
                else:
                    if hasattr(pattern, 'callback'):
                        if hasattr(pattern.callback, 'cls'):
                            view_name = f"{pattern.callback.cls.__name__}"
                        else:
                            view_name = f"{pattern.callback.__name__}"
                    else:
                        view_name = "Unknown"
                    self.stdout.write(f"{spaces}{pattern.pattern} -> {view_name}")

        self.stdout.write("Доступные URL пути:")
        show_urls(urlconf.url_patterns)