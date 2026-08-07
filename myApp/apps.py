from django.apps import AppConfig


class MyAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'myApp'
    
    def ready(self):
        import myApp.signals  # This connects the signals

