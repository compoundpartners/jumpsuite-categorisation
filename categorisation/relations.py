from django.db.models.fields.related import \
    ForeignObjectRel, ForeignObject, ManyToManyRel, lazy_related_operation
from django.core.exceptions import FieldDoesNotExist
from django.db.models.signals import pre_delete
from django.db.utils import DEFAULT_DB_ALIAS
from django.db.models import Q
from django.apps import apps
from django.core import checks
from django.utils.functional import cached_property
from django.db.models.query_utils import PathInfo

from gm2m.contenttypes import ct, get_content_type
from gm2m.managers import create_gm2m_related_manager
from gm2m.descriptors import RelatedGM2MDescriptor, SourceGM2MDescriptor
from gm2m.deletion import *
from gm2m.signals import deleting
from gm2m.helpers import GM2MModel, is_fake_model
from gm2m import fields
from gm2m.relations import GM2MRel

from .monkeypatch import create_gm2m_intermediary_model, THROUGH_FIELDS

class CGM2MRel(GM2MRel):

    def contribute_to_class(self, cls, virtual_only=False):

        # Connect the descriptor for this field
        setattr(cls, self.field.attname,
                SourceGM2MDescriptor(self.field))

        if cls._meta.abstract or cls._meta.swapped:
            # do not do anything for abstract or swapped model classes
            return

        if not self.through:
            self.set_init('through',
                          create_gm2m_intermediary_model(self.field, cls))
            # we set through_fields to the default intermediary model's
            # THROUGH_FIELDS as it carries fields assignments for
            # ModelState instances
            self.set_init('through_fields', THROUGH_FIELDS)

        # set related name
        if not self.field.model._meta.abstract and self.related_name:
            self.set_init('related_name', self.related_name % {
                'class': self.field.model.__name__.lower(),
                'app_label': self.field.model._meta.app_label.lower()
            })

        def calc_field_names(rel):
            # Extract field names from through model and stores them in
            # rel.through_field (so that they are sent on deconstruct and
            # passed to ModelState instances)

            tf_dict = {}

            if is_fake_model(rel.through):
                # we populate the through field dict using rel.through_fields
                # that was either provided or computed beforehand with the
                # actual model
                for f, k in zip(rel.through_fields,
                                ('src', 'tgt', 'tgt_ct', 'tgt_fk')):
                    tf_dict[k] = f
                rel.through._meta._field_names = tf_dict
                return

            if rel.through_fields:
                tf_dict['src'], tf_dict['tgt'] = \
                    rel.through_fields[:2]
                for gfk in rel.through._meta.private_fields:
                    if gfk.name == tf_dict['tgt']:
                        break
                else:
                    raise FieldDoesNotExist(
                        'Generic foreign key "%s" does not exist in through '
                        'model "%s"' % (tf_dict['tgt'],
                                        rel.through._meta.model_name)
                    )
                tf_dict['tgt_ct'] = gfk.ct_field
                tf_dict['tgt_fk'] = gfk.fk_field
            else:
                for f in rel.through._meta.fields:
                    try:
                        remote_field = f.remote_field
                    except AttributeError:
                        continue
                    if remote_field and (remote_field.model == rel.field.model
                        or remote_field.model == '%s.%s' % (
                            rel.field.model._meta.app_label,
                            rel.field.model._meta.object_name)):
                        tf_dict['src'] = f.name
                        break
                for f in rel.through._meta.private_fields:
                    if isinstance(f, ct.GenericForeignKey):
                        tf_dict['tgt'] = f.name
                        tf_dict['tgt_ct'] = f.ct_field
                        tf_dict['tgt_fk'] = f.fk_field
                        break

            if not set(tf_dict.keys()).issuperset(('src', 'tgt')):
                raise ValueError('Bad through model for GM2M relationship.')

            rel.through._meta._field_names = tf_dict

            # save the result in rel.through_fields so that it appears
            # in the deconstruction. Without that there would be no way for
            # a ModelState constructed from a migration to know which fields
            # have which function, as all virtual fields are stripped
            tf = []
            for f in ('src', 'tgt', 'tgt_ct', 'tgt_fk'):
                tf.append(tf_dict[f])
            rel.set_init('through_fields', tf)

        # resolve through model if it's provided as a string
        if isinstance(self.through, str):
            def resolve_through_model(c, model, r):
                r.set_init('through', model)
                calc_field_names(r)
            lazy_related_operation(resolve_through_model, cls, self.through,
                                   r=self)
        else:
            calc_field_names(self)

        self.related_model = cls

        for rel in self.rels:
            # we need to make sure the GM2MUnitRel's field instance is the
            # right one. Indeed, if cls is derived from an abstract model
            # where the GM2MField is defined, rel.field is the field linked
            # to the abstract model
            rel.field = self.field
            rel.contribute_to_class()
