from django.db import models
from django.db.migrations.operations import AlterField


def get_field(model, field_name):
    return model._meta.get_field(field_name)


def get_apps_from_state(migration_state):
    return migration_state.apps


def get_rel(f):
    return f.remote_field


class AlterCategorisationField(AlterField):

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        to_apps = get_apps_from_state(to_state)
        to_model = to_apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, to_model):
            to_field = get_field(to_model, self.name)
            to_m2m_model = get_rel(to_field).through
            self.add_sort_value_field(schema_editor, to_m2m_model)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        from_apps = get_apps_from_state(from_state)
        from_model = from_apps.get_model(app_label, self.model_name)
        from_field = get_field(from_model, self.name)

        to_apps = get_apps_from_state(to_state)
        to_model = to_apps.get_model(app_label, self.model_name)
        if self.allow_migrate_model(schema_editor.connection.alias, to_model):
            from_m2m_model = get_rel(from_field).through
            self.remove_sort_value_field(schema_editor, from_m2m_model)

    def add_sort_value_field(self, schema_editor, model):
        field = self.make_sort_by_field(model)
        schema_editor.add_field(model, field)

    @staticmethod
    def remove_sort_value_field(schema_editor, model):
        field = get_field(model, 'sort_value')
        schema_editor.remove_field(model, field)

    @staticmethod
    def make_sort_by_field(model):
        field = models.IntegerField(name='sort_value', default=0)
        field.set_attributes_from_name('sort_value')
        return field