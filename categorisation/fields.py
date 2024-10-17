from django.db.models import Q, Manager
from django.db.models.fields import Field

from gm2m.contenttypes import ct, get_content_type
from gm2m.fields import GM2MField
from gm2m.managers import GM2MBaseSrcManager
from .relations import CGM2MRel

class CategorisationField(GM2MField):
    def __init__(self, *related_models, **params):
        super(GM2MField, self).__init__(
            verbose_name=params.pop('verbose_name', None),
            name=params.pop('name', None),
            help_text=params.pop('help_text', u''),
            error_messages=params.pop('error_messages', None),
            rel=CGM2MRel(self, related_models, **params),
            blank=params.pop('blank', False),
            # setting null to True only prevent makemigrations from asking for
            # a default value
            null=True
        )
        self.db_table = params.pop('db_table', None)
        self.pk_maxlength = params.pop('pk_maxlength', False)


def _to_change(self, objs, db):
    """
    Returns the sets of items to be added and a Q object for removal
    """
    inst_ct = get_content_type(self.instance)

    vals = list(self.through._default_manager.using(db)
                            .values_list(self.field_names['src'], flat=True)
                            .filter(**{
                                self.field_names['tgt_ct']: inst_ct,
                                self.field_names['tgt_fk']: self.pk
                            }))

    to_add = set()
    to_remove = set()
    for obj in objs:
        try:
            vals.remove(obj.pk)
        except ValueError:
            # obj.pk is not in vals and must be added
            #to_add.add(self.through(**{
            #dm
            self.through._default_manager.using(db).create(**{
                '%s_id' % self.field_names['src']:
                    obj.pk,
                self.field_names['tgt_ct']: inst_ct,
                self.field_names['tgt_fk']: self.pk
            })
    for v in vals:
        #to_remove.add(v)
        #dm
        f = {
            '%s_id' % self.field_names['src']:
                v,
            self.field_names['tgt_ct']: inst_ct,
            self.field_names['tgt_fk']: self.pk
        }
        self.through._default_manager.using(db).get(**f).delete()
    return to_add, Q(pk__in=to_remove)

GM2MBaseSrcManager._to_change = _to_change