import re

from django import forms, template
from django.db.models import Model
from django.urls import NoReverseMatch
from django.utils.encoding import force_text
from django.utils.html import conditional_escape

from viewflow.contrib import auth
from viewflow.urls import Site, Viewset


register = template.Library()

KWARG_RE = re.compile(r"(?:(\w+)=)?(.+)")


def _parse_var_and_args(tagname, parser, bits):
    variable_name, args, kwargs = None, [], {}
    if len(bits) >= 2 and bits[-2] == 'as':
        variable_name = bits[-1]
        bits = bits[:-2]

    if len(bits):
        for bit in bits:
            match = KWARG_RE.match(bit)
            if not match:
                raise template.TemplateSyntaxError("Malformed arguments for {} tag".format(tagname))
            name, value = match.groups()
            if name:
                kwargs[name] = parser.compile_filter(value)
            else:
                args.append(parser.compile_filter(value))

    return variable_name, args, kwargs


def _resolve_args(context, args, kwargs):
    args = [arg.resolve(context) for arg in args]
    kwargs = {
        force_text(key, 'ascii'): value.resolve(context)
        for key, value in kwargs.items()
    }
    return args, kwargs


@register.tag('reverse')
class ViewsetURLNode(template.Node):
    """
    Reverse a url to a view within viewset

    Example::
        {% reverse viewset viewname args kwargs %}
    """

    def __init__(self, parser, token):
        bits = token.split_contents()
        if len(bits) < 2:
            raise template.TemplateSyntaxError(
                "get_url takes at least two arguments, an "
                "viewset and the name of a url.")

        self.viewset = parser.compile_filter(bits[1])
        self.view_name = parser.compile_filter(bits[2])
        self.variable_name, self.args, self.kwargs = _parse_var_and_args(
            'get_url', parser, bits[3:]
        )

    def render(self, context):
        args, kwargs = _resolve_args(context, self.args, self.kwargs)

        viewset = self.viewset.resolve(context)
        if not isinstance(viewset, Viewset):
            raise template.TemplateSyntaxError(f"reverse first argument must be a viewset instance, got '{viewset}'")

        view_name = self.view_name.resolve(context)

        try:
            current_app = context.request.current_app
        except AttributeError:
            try:
                current_app = context.request.resolver_match.namespace
            except AttributeError:
                current_app = None

        url = ''
        try:
            url = viewset.reverse(view_name, args=args, kwargs=kwargs, current_app=current_app)
        except NoReverseMatch:
            if self.variable_name is None:
                raise

        if self.variable_name:
            context[self.variable_name] = url
            return ''
        else:
            if context.autoescape:
                url = conditional_escape(url)
            return url


@register.tag('get_absolute_url')
class AbsoluteURLNode(template.Node):
    """
    Call viewset.get_absolute_url for an object from site

    Example::
        {% get_absolute_url site view.object %}
    """

    def __init__(self, parser, token):
        bits = token.split_contents()
        if len(bits) < 3:
            raise template.TemplateSyntaxError(
                "viewset_url takes at least two arguments, a "
                "site and an object.")

        self.site = parser.compile_filter(bits[1])
        self.object = parser.compile_filter(bits[2])
        if len(bits) >= 2 and bits[-2] == 'as':
            self.variable_name = bits[-1]

    def render(self, context):
        site = self.site.resolve(context)
        if not isinstance(site, Site):
            raise template.TemplateSyntaxError("site_url first argument must be a site instance")

        obj = self.object.resolve(context)
        if not isinstance(obj, Model):
            raise template.TemplateSyntaxError("site_url third argument must be a model instance")

        url = ''
        try:
            url = site.get_absolute_url(context.request, obj)
        except NoReverseMatch:
            if self.variable_name is None:
                raise

        if self.variable_name:
            context[self.variable_name] = url
            return ''
        else:
            if context.autoescape:
                url = conditional_escape(url)
            return url


@register.filter
def verbose_name(obj):
    """Return model verbose name."""
    if isinstance(obj, Model):
        type(obj)._meta.verbose_name
    return obj._meta.verbose_name


@register.filter
def verbose_name_plural(obj):
    """Return model verbose name in plural mode."""
    if isinstance(obj, Model):
        type(obj)._meta.verbose_name_plural
    return obj._meta.verbose_name_plural


@register.filter
def has_perm(app, user):
    """
    Check a user access rights for an application

    Example:

        {% if request.resolver_match.app|has_perm:request.user %}
            {% include app.menu_template_name app=request.resolver_match.app only %}
        {% endif %}
    """
    return app.has_perm(user)


@register.filter
def user_avatar_url(user):
    """Lookup for the user avatar."""
    return auth.get_user_avatar_url(user)


@register.filter
def list_column_order(column_def, list_view):
    """Sort order for the column from the list view."""
    if hasattr(list_view, 'columns_order'):
        position, order = None, list_view.columns_order.get(column_def)
        if order:
            position = list(list_view.columns_order.keys()).index(column_def) + 1
            return {'position': position, 'sort': order}
    return None


@register.filter
def list_page_data(page, list_view):
    """Formated page data for a table.

       Returned data is a list of list of cell values zipped with column definitions.
       [[(column, value), (column, value), ...], ...]
    """
    return list_view.get_page_data(page)


@register.filter
def list_order(request_kwargs, list_view):
    return request_kwargs.get(list_view.ordering_kwarg, '')