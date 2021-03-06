from __future__ import unicode_literals

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Model, NOT_PROVIDED, DateTimeField
from django.utils import timezone
from django.utils.encoding import smart_text
from django.db.models.fields.related import ManyToManyField


def track_field(field):
    """
    Returns whether the given field should be tracked by Auditlog.

    Untracked fields are many-to-many relations and relations to the Auditlog LogEntry model.

    :param field: The field to check.
    :type field: Field
    :return: Whether the given field should be tracked.
    :rtype: bool
    """
    from auditlog.models import LogEntry
    # Do not track many to many relations
    if field.many_to_many:
        return False

    # Do not track relations to LogEntry
    if getattr(field, 'remote_field', None) is not None and field.remote_field.model == LogEntry:
        return False

    # 1.8 check
    elif getattr(field, 'rel', None) is not None and field.rel.to == LogEntry:
        return False

    return True


def get_fields_in_model(instance):
    """
    Returns the list of fields in the given model instance. Checks whether to use the official _meta API or use the raw
    data. This method excludes many to many fields.

    :param instance: The model instance to get the fields for
    :type instance: Model
    :return: The list of fields for the given model (instance)
    :rtype: list
    """
    assert isinstance(instance, Model)

    # Check if the Django 1.8 _meta API is available
    use_api = hasattr(instance._meta, 'get_fields') and callable(instance._meta.get_fields)

    if use_api:
        return [f for f in instance._meta.get_fields() if track_field(f)]
    return instance._meta.fields


def get_field_value(obj, field):
    """
    Gets the value of a given model instance field.
    :param obj: The model instance.
    :type obj: Model
    :param field: The field you want to find the value of.
    :type field: Any
    :return: The value of the field as a string.
    :rtype: str
    """
    if isinstance(field, DateTimeField):
        # DateTimeFields are timezone-aware, so we need to convert the field
        # to its naive form before we can accuratly compare them for changes.
        try:
            value = field.to_python(getattr(obj, field.name, None))
            if value is not None and settings.USE_TZ:
                value = timezone.make_naive(value, timezone=timezone.utc)
        except ObjectDoesNotExist:
            value = field.default if field.default is not NOT_PROVIDED else None
            
    else:
        try:
            value = getattr(obj, field.name, None)
        except ObjectDoesNotExist:
            value = field.default if field.default is not NOT_PROVIDED else None

    value_string = smart_text(value)

    return (value,value_string)


# for use with django-auditlog conflict()
def model_instance_diff_m2m_post_vs_saved(request, target, saved):
    cls=target.__class__
    diffs={}
    for f in target._meta._get_fields():
        if type(f) is ManyToManyField:

            fn=f.name

            # TODO: what if fks are UUIDs or other type?
            target_idlist=map(int,request.POST.getlist(fn))
            target_idlist.sort(key=lambda x: int(x))
            target_list=f.related_model.objects.filter(pk__in=target_idlist)

            target_strlist=[str(x) for x in target_list]

            saved_list=getattr(saved,fn).all()
            saved_idlist=[x.id for x in saved_list]
            saved_idlist.sort()
            saved_strlist=[str(x) for x in saved_list]
            saved_strlist.sort()

            ids_added=[val for val in target_idlist if val not in saved_idlist]
            ids_removed=[val for val in saved_idlist if val not in target_idlist]

            str_added=[val for val in target_strlist if val not in saved_strlist]
            str_removed=[val for val in saved_strlist if val not in target_strlist]

            # dont add diff if there is no change
            if saved_idlist!=target_idlist:
                diffs[fn]={ 'ids':{'try':target_idlist, 'exist':saved_idlist, 'try_add':ids_added, 'try_rmv':ids_removed }, 
                    'str':{'try':target_strlist, 'exist':saved_strlist, 'try_add':str_added, 'try_rmv':str_removed} }

    return diffs


def model_instance_diff(old, new):
    """
    Calculates the differences between two model instances. One of the instances may be ``None`` (i.e., a newly
    created model or deleted model). This will cause all fields with a value to have changed (from ``None``).

    :param old: The old state of the model instance.
    :type old: Model
    :param new: The new state of the model instance.
    :type new: Model
    :return: A dictionary with the names of the changed fields as keys and a two tuple of the old and new field values
             as value.
    :rtype: dict
    """
    from auditlog.registry import auditlog

    if not(old is None or isinstance(old, Model)):
        raise TypeError("The supplied old instance is not a valid model instance.")
    if not(new is None or isinstance(new, Model)):
        raise TypeError("The supplied new instance is not a valid model instance.")

    diff = {}

    if old is not None and new is not None:
        fields = set(old._meta.fields + new._meta.fields)
        model_fields = auditlog.get_model_fields(new._meta.model)
    elif old is not None:
        fields = set(get_fields_in_model(old))
        model_fields = auditlog.get_model_fields(old._meta.model)
    elif new is not None:
        fields = set(get_fields_in_model(new))
        model_fields = auditlog.get_model_fields(new._meta.model)
    else:
        fields = set()
        model_fields = None

    # Check if fields must be filtered
    if model_fields and (model_fields['include_fields'] or model_fields['exclude_fields']) and fields:
        filtered_fields = []
        if model_fields['include_fields']:
            filtered_fields = [field for field in fields
                               if field.name in model_fields['include_fields']]
        else:
            filtered_fields = fields
        if model_fields['exclude_fields']:
            filtered_fields = [field for field in filtered_fields
                               if field.name not in model_fields['exclude_fields']]
        fields = filtered_fields

    for field in fields:
        old_value, old_value_string = get_field_value(old, field)
        new_value, new_value_string = get_field_value(new, field)

        if old_value != new_value:
            if old_value is None and new_value_string=="":
                pass
            else:
                diff[field.name] = (smart_text(old_value), smart_text(new_value))

    if len(diff) == 0:
        diff = None

    return diff
