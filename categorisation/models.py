from collections import defaultdict
from django.db import connection
from django.db.backends import utils as db_backends_utils
from django.db.migrations.state import ModelState

from gm2m.contenttypes import ct as ct_classes
from gm2m.helpers import is_fake_model
from gm2m.models import (
    SRC_ATTNAME,
    TGT_ATTNAME,
    CT_ATTNAME,
    FK_ATTNAME,
    THROUGH_FIELDS,
    Options,
)
from gm2m.query import GM2MTgtQuerySetIterable

SORT_ATTNAME = 'sort_value'
THROUGH_FIELDS += (SORT_ATTNAME,)

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
    if field.sorted:
        meta_kwargs['ordering'] = [CT_ATTNAME, SORT_ATTNAME]


    meta = type('Meta', (object,), meta_kwargs)

    fk_maxlength = 16  # default value
    if field.pk_maxlength is not False:
        fk_maxlength = field.pk_maxlength

    properties = {
        'Meta': meta,
        '__module__': klass.__module__,
        SRC_ATTNAME: models.ForeignKey(
            klass, auto_created=True,
            on_delete=field.remote_field.on_delete_src,
            db_constraint=field.remote_field.db_constraint
        ),
        CT_ATTNAME: models.ForeignKey(
            ct_classes.ContentType,
            on_delete=models.CASCADE,
            db_constraint=field.remote_field.db_constraint
        ),
        FK_ATTNAME: models.PositiveIntegerField(),
        TGT_ATTNAME: ct_classes.GenericForeignKey(
            ct_field=CT_ATTNAME,
            fk_field=FK_ATTNAME,
            for_concrete_model=field.remote_field.for_concrete_model,
        ),
    }

    if field.sorted:
        properties[SORT_ATTNAME] = models.IntegerField(default=0)
        properties['_sort_field_name'] = SORT_ATTNAME
    model = type(str(name), (models.Model,), properties)

    if is_fake_model(klass):
        # if we are building a fake model for migrations purposes, create a
        # ModelState from the model and render it (see issues #3 and #5)
        model = ModelState.from_model(model).render(klass._meta.apps)

    # changing the options' class to override get_field for RenameModel
    # migrations' database_forwards
    model._meta.__class__ = Options

    return model


def fixed_queryset_iter(self):
    """
    Override to return the actual objects, not the GM2MObject
    Fetch the actual objects by content types to optimize database access
    """

    qs = self.queryset

    try:
        del qs._related_prefetching
        rel_prefetching = True
    except AttributeError:
        rel_prefetching = False

    ct_attrs = defaultdict(lambda: defaultdict(lambda: []))
    objects = {}
    ordered_ct_attrs = []

    field_names = qs.model._meta._field_names
    fk_field = qs.model._meta.get_field(field_names['tgt_fk'])

    extra_select = list(qs.query.extra_select)

    for vl in qs.values_list(field_names['tgt_ct'],
                                field_names['tgt_fk'],
                                *extra_select):
        ct = vl[0]
        pk = fk_field.to_python(vl[1])
        ct_attrs[ct][pk].append(vl[2:])
        ordered_ct_attrs.append((ct, pk))

    for ct, attrs in ct_attrs.items():
        for pk, obj in ct_classes.ContentType.objects.get_for_id(ct).\
                model_class()._default_manager.in_bulk(attrs.keys()).\
                items():

            pk = fk_field.to_python(pk)

            # we store the through model id in case we are in the process
            # of fetching related objects
            for i, k in enumerate(extra_select):
                e_list = []
                for e in attrs[pk]:
                    e_list.append(e[i])
                setattr(obj, k, e_list)

            if rel_prefetching:
                # when prefetching related objects, one must yield one
                # object per through model instance
                for __ in attrs[pk]:
                    if qs.ordered:
                        objects[(ct, pk)] = obj
                    else:
                        yield obj
                continue

            if qs.ordered:
                objects[(ct, pk)] = obj
            else:
                yield obj

    if qs.ordered:
        for ct, pk in ordered_ct_attrs:
            if (ct, pk) in objects:
                yield objects[(ct, pk)]

GM2MTgtQuerySetIterable.__iter__ = fixed_queryset_iter


from django.contrib.admin import utils
from django.utils.html import conditional_escape
from categorisation import fields

old_display_for_field = utils.display_for_field

def display_for_field(value, field, empty_value_display):
    if isinstance(field.remote_field, fields.CategorisationField):
        return conditional_escape(", ".join(map(str, value.all())))
    return old_display_for_field(value, field, empty_value_display)

utils.display_for_field = display_for_field


    

