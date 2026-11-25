"""URL configuration for marketplace project.

The urlpatterns list maps URLs to views. Documentation:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import include and path from django.urls.
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path
from shop.views import reddit_feed

urlpatterns = [
    path("api/", include("shop.api_urls")),
    path("reddit/", reddit_feed, name="reddit-feed"),
    path("admin/", admin.site.urls),
    path("", include("shop.urls")),
]
