import django.contrib.admin.helpers as admin_helpers
import django.contrib.admin.templatetags.admin_list as admin_list
import django.contrib.admin.utils as admin_utils
from django.utils.html import conditional_escape

from .fields import CategorisationField


MODULES_TO_PATCH = [admin_utils, admin_helpers, admin_list]


def setup_admin_integration():
    original_display_for_field = admin_utils.display_for_field

    def display_for_field(value, field, *args, **kwargs):
        if isinstance(field.remote_field, CategorisationField):
            return conditional_escape(", ".join(map(str, value.all())))
        return original_display_for_field(value, field, *args, **kwargs)

    for mod in MODULES_TO_PATCH:
        setattr(mod, "display_for_field", display_for_field)
