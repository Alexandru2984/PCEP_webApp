import pytest
from django.utils.http import parse_header_parameters
from django.utils.translation import get_supported_language_variant, trans_real


def test_header_parser_handles_many_quoted_separators():
    value = ';' * 5000

    assert parse_header_parameters(
        f'attachment; filename="{value}"; size=1'
    ) == ('attachment', {'filename': value, 'size': '1'})


def test_oversized_language_code_is_rejected_before_cache_lookup():
    cached_lookup = trans_real._get_supported_language_variant
    cached_lookup.cache_clear()

    try:
        with pytest.raises(LookupError):
            get_supported_language_variant('e' * 501, strict=True)

        cache_info = cached_lookup.cache_info()
        assert cache_info.currsize == 0
        assert cache_info.misses == 0
    finally:
        cached_lookup.cache_clear()
