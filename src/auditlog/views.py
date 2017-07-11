from diff_match_patch import diff_match_patch
from concurrency.views import ConflictResponse
from django.template import loader
from django.utils.safestring import mark_safe
from django.template.context import RequestContext
from django.http.response import HttpResponseRedirect
from auditlog.diff import model_instance_diff, model_instance_diff_m2m_post_vs_saved
from auditlog.models import LogEntry
from django.contrib import messages
import json

def get_instance_diff_json(current, stored):
    data = {}
    fields = current._meta.fields
    for field in fields:
        v1 = getattr(current, field.name, "")
        v2 = getattr(stored, field.name, "")
        if v1!=v2:
            data[field.name+'.try']= v1
            data[field.name+'.stored']=v2
    return data


def conflict(request, target=None, template_name='409.html'):
    '''
    ContentType.objects.get(app_label="auth", model="user")

    target.__class__._meta.app_label
    target.__class__._meta.model_name
    target.pk
    template = loader.get_template(template_name)
    '''

    try:
        saved = target.__class__._default_manager.get(pk=target.pk)
        diff = get_instance_diff_json(target, saved)

        add_data={}

        get_additional_data = getattr(target, 'get_additional_data', None)
        if callable(get_additional_data):
            add_data=get_additional_data()

        changes = model_instance_diff(saved, target)

        changes_m2m = model_instance_diff_m2m_post_vs_saved(request,saved, target)
        changes_m2m_ids={}
        changes_m2m_str={}
        for fld in changes_m2m.keys():
            changes_m2m_ids[fld]=changes_m2m[fld]['ids']
            #changes_m2m_str[fld+' (try del,try add)']=( changes_m2m[fld]['str']['try_rmv'], changes_m2m[fld]['str']['try_add'] )
            changes_m2m_str[fld]=( changes_m2m[fld]['str']['exist'], changes_m2m[fld]['str']['try'] )

        if changes_m2m_ids:
            add_data['m2m_changes']=changes_m2m_ids

        if changes_m2m_str:
            changes.update(changes_m2m_str)

        log_entry = LogEntry.objects.log_create(
            target,
            action=LogEntry.Action.CONFLICT,
            changes=json.dumps(changes),
            add_data=add_data
        )

        messages.add_message(request, messages.ERROR, 'Another user edited this record since you began. Both changes stored below.')


    except target.__class__.DoesNotExist:
        saved = None
        diff = None

    return HttpResponseRedirect('/admin/auditlog/logentry/%d/change/'%log_entry.id)
