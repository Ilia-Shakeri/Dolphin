from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from rest_framework import renderers
from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser
from rest_framework.settings import api_settings
from rest_framework.utils import json


MAX_JSON_NESTING_DEPTH = 32


def _reject_deep_json(value):
    depth = 0
    in_string = False
    escaped = False
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_NESTING_DEPTH:
                raise ParseError("JSON nesting is too deep.")
        elif character in "]}":
            depth -= 1


class BoundedJSONParser(BaseParser):
    media_type = "application/json"
    renderer_class = renderers.JSONRenderer
    strict = api_settings.STRICT_JSON

    def parse(self, stream, media_type=None, parser_context=None):
        parser_context = parser_context or {}
        encoding = parser_context.get("encoding", settings.DEFAULT_CHARSET)
        raw_value = stream.read(settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1)
        if len(raw_value) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE:
            raise RequestDataTooBig
        try:
            value = raw_value.decode(encoding) if isinstance(raw_value, bytes) else raw_value
        except UnicodeError as exc:
            raise ParseError("Malformed JSON.") from exc
        _reject_deep_json(value)
        try:
            parse_constant = json.strict_constant if self.strict else None
            return json.loads(value, parse_constant=parse_constant)
        except (ValueError, RecursionError) as exc:
            raise ParseError("Malformed JSON.") from exc
