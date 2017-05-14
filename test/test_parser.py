import pytest

from duiker import parser


def millenium():
    from datetime import datetime as dt
    return dt.strptime('2001-01-01 00:00:00', '%Y-%m-%d %H:%M:%S')


@pytest.fixture
def millenium_unix():
    import time
    return time.mktime(millenium().timetuple())


@pytest.mark.parametrize('line,histtimeformat,expected', [
    ('  1  help history', None, parser.Command(None, None, 'help history')),
    ('100  help history', None, parser.Command(None, None, 'help history')),
    ('  1  2001-01-01 00:00:00 help history', '%Y-%m-%d %H:%M:%S ', parser.Command(None, millenium_unix(), 'help history')),
    ('100  2001-01-01 00:00:00 help history', '%Y-%m-%d %H:%M:%S ', parser.Command(None, millenium_unix(), 'help history')),
    ('  1  2001-01-01 00:00:00 help history', '%Y-%m-%d %H:%M:%S', parser.Command(None, millenium_unix(), 'help history')),
    ('100  2001-01-01 00:00:00 help history', '%Y-%m-%d %H:%M:%S', parser.Command(None, millenium_unix(), 'help history')),
])
def test_parse_history_line(line, histtimeformat, expected):
    assert parser.parse_history_line(line, histtimeformat) == expected


@pytest.mark.parametrize('line,histtimeformat', [
    ('  1  2001-01-01 00:00:00 help history', '%%'),
    ('100  2001-01-01 00:00:00 help history', '%%'),
])
def test_parse_history_line_failure(line, histtimeformat):
    with pytest.raises(ValueError):
        parser.parse_history_line(line, histtimeformat)
