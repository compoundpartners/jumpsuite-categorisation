from django.db import connection
from django.db.backends import utils as db_backends_utils
from django.db.migrations.state import ModelState

from gm2m.contenttypes import ct
from gm2m.helpers import is_fake_model
from gm2m.models import (
    SRC_ATTNAME,
    TGT_ATTNAME,
    CT_ATTNAME,
    FK_ATTNAME,
    THROUGH_FIELDS,
    Options,
)

def create_gm2m_intermediary_model(field, klass):
    """
    Creates a generic M2M model for the GM2M field 'field' on model 'klass'
    """

    from django.db import models

    managed = klass._meta.managed
    name = '%s_%s' % (klass._meta.object_name, field.name)

    model_name = klass._meta.model_name

    db_table = db_backends_utils.truncate_name(
                   '%s_%s' % (klass._meta.db_table, field.name),
                   connection.ops.max_name_length())

    meta_kwargs = {
        'db_table': db_table,
        'managed': managed,
        'auto_created': klass,
        'app_label': klass._meta.app_label,
        'db_tablespace': klass._meta.db_tablespace,
        'unique_together': (SRC_ATTNAME, CT_ATTNAME, FK_ATTNAME),
        'verbose_name': '%s-generic relationship' % model_name,
        'verbose_name_plural': '%s-generic relationships' % model_name,
        'apps': field.model._meta.apps,
    }

    meta = type('Meta', (object,), meta_kwargs)

    fk_maxlength = 16  # default value
    if field.pk_maxlength is not False:
        fk_maxlength = field.pk_maxlength

    model = type(str(name), (models.Model,), {
        'Meta': meta,
        '__module__': klass.__module__,
        SRC_ATTNAME: models.ForeignKey(
            klass, auto_created=True,
            on_delete=field.remote_field.on_delete_src,
            db_constraint=field.remote_field.db_constraint
        ),
        CT_ATTNAME: models.ForeignKey(
            ct.ContentType,
            on_delete=models.CASCADE,
            db_constraint=field.remote_field.db_constraint
        ),
        FK_ATTNAME: models.PositiveIntegerField(),
        TGT_ATTNAME: ct.GenericForeignKey(
            ct_field=CT_ATTNAME,
            fk_field=FK_ATTNAME,
            for_concrete_model=field.remote_field.for_concrete_model,
        ),
    })

    if is_fake_model(klass):
        # if we are building a fake model for migrations purposes, create a
        # ModelState from the model and render it (see issues #3 and #5)
        model = ModelState.from_model(model).render(klass._meta.apps)

    # changing the options' class to override get_field for RenameModel
    # migrations' database_forwards
    model._meta.__class__ = Options

    return model
