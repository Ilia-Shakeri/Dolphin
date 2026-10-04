from config.devcheck_settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "postgres",
        "USER": "postgres",
        "PASSWORD": "devtest",
        "HOST": "172.20.243.37",
        "PORT": "5432",
    }
}
