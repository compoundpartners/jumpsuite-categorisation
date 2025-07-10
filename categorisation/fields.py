from django.core.exceptions import FieldDoesNotExist
from django.db import router
from django.db.models import Q, Manager
from django.db.models.fields import Field
from gm2m.contenttypes import ct, get_content_type
from gm2m.fields import GM2MField
from gm2m.managers import GM2MBaseSrcManager
from .relations import CGM2MRel

class CategorisationField(GM2MField):
    def __init__(self, sorted=False, *related_models, **params):
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
        self.sorted = sorted


def _to_change(self, objs, db):
    """
    Returns the sets of items to be added and a Q object for removal
    """
    inst_ct = get_content_type(self.instance)
    if self.field.sorted:
        vals = dict([getattr(obj, self.field_names['src']).pk, obj] for obj in (self.through._default_manager.using(db)
            .filter(**{
                self.field_names['tgt_ct']: inst_ct,
                self.field_names['tgt_fk']: self.pk
            })))
    else:
        vals = list(self.through._default_manager.using(db)
            .values_list(self.field_names['src'], flat=True)
            .filter(**{
                self.field_names['tgt_ct']: inst_ct,
                self.field_names['tgt_fk']: self.pk
            }))

    to_add = set()
    to_remove = set()
    to_update = set()
    for sort_value, obj in enumerate(objs, 1):
        if hasattr(obj, 'pk'):
            pk = obj.pk
        else:
            try:
                pk = int(obj)
            except ValueError:
                continue
        if pk in vals:
            if self.field.sorted:
                through = vals[pk]
                if through.sort_value != sort_value:
                    through.sort_value = sort_value
                    to_update.add(through)
                del vals[pk]
            else:
                vals.remove(pk)
        else:
            insert = {
                '%s_id' % self.field_names['src']:
                    pk,
                self.field_names['tgt_ct']: inst_ct,
                self.field_names['tgt_fk']: self.pk,
            }
            if self.field.sorted:
                insert['sort_value'] = sort_value
            self.through._default_manager.using(db).create(**insert)
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
    
    if to_update:
        self.through._default_manager.using(db).bulk_update(to_update, ['sort_value'])
    return to_add, Q(pk__in=to_remove)

def get_queryset(self):
    try:
        return self.instance \
                    ._prefetched_objects_cache[self.prefetch_cache_name]
    except (AttributeError, KeyError):
        db = self._db or router.db_for_read(self.instance.__class__,
                                            instance=self.instance)
        if self.field.sorted:
            model_name = self.model._meta.model_name
            return self._get_queryset(using=db)._next_is_sticky() \
                        .filter(**self.core_filters).order_by(f'{model_name}_related__sort_value')
        return self._get_queryset(using=db)._next_is_sticky() \
                    .filter(**self.core_filters)
        
GM2MBaseSrcManager._to_change = _to_change
GM2MBaseSrcManager.get_queryset = get_queryset