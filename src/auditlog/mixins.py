import json
import cgi

from django.conf import settings
from django.core import urlresolvers
from django.utils.html import format_html
try:
    from django.urls.exceptions import NoReverseMatch
except ImportError:
    from django.core.urlresolvers import NoReverseMatch
from auditlog.models import LogEntry

MAX = 75


def chop(s,length):
    if not s:
        return ''
    if len(s)<=length:
        return s
    return s[:length]+'...'


def tableizer(dic):
    ht='<table border=0 cellspacing=0 cellpadding=0>'
    for k in dic.keys():
        v=dic[k]
        ht+='<tr>'
        ht+='<td width=100 style="background-color:#ddd">%s</td>' % str(k)
        if type(v) is dict:
            ht+='<td>%s</td>' % tableizer(v)
        elif type(v) is list:
            ht+='<td>'
            for el in v:
                ht+=str(el)+'<br>\n'
            ht+='</td>'
        else:
            ht+='<td>%s</td>' % str(v)
        ht+='</tr>'
    ht+='</table>'
    return ht


class LogEntryAdminMixin(object):

    def created(self, obj):
        return obj.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    created.short_description = 'Created'

    def user_url(self, obj):
        if obj.actor:
            # if user does not have perms on users, could not reverse url
            try:
                app_label, model = settings.AUTH_USER_MODEL.split('.')
                viewname = 'admin:%s_%s_change' % (app_label, model.lower())
                link = urlresolvers.reverse(viewname, args=[obj.actor.id])
                return u'<a href="%s">%s</a>' % (link, obj.actor)
            except:
                return obj.actor

        return 'system'
    user_url.allow_tags = True
    user_url.short_description = 'User'

    def resource_url(self, obj):
        app_label, model = obj.content_type.app_label, obj.content_type.model
        viewname = 'admin:%s_%s_change' % (app_label, model)
        try:
            link = urlresolvers.reverse(viewname, args=[obj.object_id])
        except NoReverseMatch:
            return obj.object_repr
        else:
            return u'<a href="%s">%s</a>' % (link, obj.object_repr)
    resource_url.allow_tags = True
    resource_url.short_description = 'Resource'

    def remote_addr_url_w(self, obj):
        if obj.remote_addr is None:
            return None
        link = "https://ipinfo.io/" + str(obj.remote_addr)
        return u'%s [ <a target="_blank" href="%s">Lookup</a> ]' % (obj.remote_addr, link )
    remote_addr_url_w.allow_tags = True
    remote_addr_url_w.short_description = 'IP'


    def msg_short(self, obj):
        if obj.action == 2:
            return ''  # delete
        changes = json.loads(obj.changes)

    # single-field changes, display data
        if len(changes.keys())<=6:
            html='<span style="font-size:0.8em; font-weight:900;">%s</span><br><span style="color:red">%s</span> &rarr;  <span style="color:darkgreen">%s</span>'
            s=''
            for key in changes.keys():
                #import pdb; pdb.set_trace()
                val = changes[key]

                if type(val[0]) is list:
                    str_0=cgi.escape( "\n".join(val[0]) ).replace("{","(").replace("}",")")
                else:
                    str_0=cgi.escape(val[0]).replace("{","(").replace("}",")")

                if type(val[1]) is list:
                    str_1=cgi.escape( "\n".join(val[1]) ).replace("{","(").replace("}",")")

                else:
                    str_1=cgi.escape(val[1]).replace("{","(").replace("}",")")


                MAX_LIST_STR_LEN=250
                s += format_html(html % (key ,  chop(str_0,MAX_LIST_STR_LEN).replace("\n","<br>"),  chop(str_1,MAX_LIST_STR_LEN).replace("\n","<br>") ) )
                s += '<br>'
            return s

	# multi-field changes, list fields
        fields = ', '.join(sorted(changes.keys()))
        if len(fields) > MAX:
            i = fields.rfind(' ', 0, MAX)
            fields = fields[:i] + ' ..'
        return '<span style="font-size:0.8em; font-weight:900;">%s</span>' % fields
    msg_short.short_description = 'Changes'
    msg_short.allow_tags = True

    def msg(self, obj):
        changes = json.loads(obj.changes)

        msg='<table width="100%"><tr><th>#</th><th width="15%">Field</th>'
        if obj.action==LogEntry.Action.CONFLICT:
            msg += '<th width="40%">Existing</th><th width="40%">Failed Conflicting Attempt</th></tr>'
        else:
            msg += '<th width="40%">From</th><th width="40%">To</th></tr>'

        for i, field in enumerate(sorted(changes), 1):
            r=0
            vfrom=changes[field][0]
            vto=changes[field][1]
            if type(vfrom)==list and type(vto)==list:
                vfrom.sort()
                vto.sort()
                vfrom_uniq=[val for val in vfrom if val not in vto]
                vto_uniq=[val for val in vto if val not in vfrom]

                vfrom_strlist=[]
                for vf in vfrom:
                    if vf in vfrom_uniq:
                        col='blue'
                    else:
                        col='#aaa'
                    vfrom_strlist.append('<span style="color:%s">' % col +vf+'</span>')

                vto_strlist=[]
                for vf in vto:
                    if vf in vto_uniq:
                        col='purple'
                    else:
                        col='#aaa'
                    vto_strlist.append('<span style="color:%s">' % col+vf+'</span>')

                vfrom="<br>".join(vfrom_strlist)
                vto="<br>".join(vto_strlist)
                
            value = [i, field] + (['***', '***'] if field == 'password' else [vfrom,vto])
            rc="row2" if r%2 else "row1"
            args = (rc,) + tuple(value)
            msg += '<tr class="%s"><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' %  args
            r += 1
        msg += '</table>'
        return msg
    msg.allow_tags = True
    msg.short_description = 'Changes'


    def additional_data_w(self, obj):
        return tableizer(obj.additional_data)
    additional_data_w.allow_tags = True
    additional_data_w.short_description = 'Additional Data'
        
