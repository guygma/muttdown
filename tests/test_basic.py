from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.message import Message
from email.iterators import _structure

import pytest
from six.moves import StringIO

from muttdown.main import convert_tree
from muttdown.main import process_message
from muttdown.config import Config


@pytest.fixture
def basic_config():
    return Config()


@pytest.fixture
def config_with_css(tmpdir):
    with open('%s/test.css' % tmpdir, 'w') as f:
        f.write('html, body, p { font-family: serif; }\n')
    c = Config()
    c.merge_config({'css_file': '%s/test.css' % tmpdir})
    return c


def test_unmodified_no_match(basic_config):
    msg = Message()
    msg['Subject'] = 'Test Message'
    msg['From'] = 'from@example.com'
    msg['To'] = 'to@example.com'
    msg['Bcc'] = 'bananas'
    msg.set_payload('This message has no sigil')

    converted = process_message(msg, basic_config)
    assert converted == msg


def test_simple_message(basic_config):
    msg = MIMEMultipart()
    msg['Subject'] = 'Test Message'
    msg['From'] = 'from@example.com'
    msg['To'] = 'to@example.com'
    msg['Bcc'] = 'bananas'
    msg.preamble = 'Outer preamble'

    msg.attach(MIMEText("!m This is the main message body"))

    attachment = MIMEText('this is an attachment', 'x-misc')
    attachment.add_header('Content-Disposition', 'attachment')
    msg.attach(attachment)

    converted, _ = convert_tree(msg, basic_config)
    assert converted['Subject'] == 'Test Message'
    assert converted['From'] == 'from@example.com'
    assert converted['To'] == 'to@example.com'
    assert converted.get('Bcc', None) is None
    assert isinstance(converted, MIMEMultipart)
    assert converted.preamble == 'Outer preamble'
    assert len(converted.get_payload()) == 2
    alternatives_part = converted.get_payload()[0]
    assert isinstance(alternatives_part, MIMEMultipart)
    assert alternatives_part.get_content_type() == 'multipart/alternative'
    assert len(alternatives_part.get_payload()) == 2
    text_part = alternatives_part.get_payload()[0]
    html_part = alternatives_part.get_payload()[1]
    assert isinstance(text_part, MIMEText)
    assert text_part.get_content_type() == 'text/plain'
    assert isinstance(html_part, MIMEText)
    assert html_part.get_content_type() == 'text/html'
    attachment_part = converted.get_payload()[1]
    assert isinstance(attachment_part, MIMEText)
    assert attachment_part['Content-Disposition'] == 'attachment'
    assert attachment_part.get_content_type() == 'text/x-misc'


def test_with_css(config_with_css):
    msg = Message()
    msg['Subject'] = 'Test Message'
    msg['From'] = 'from@example.com'
    msg['To'] = 'to@example.com'
    msg['Bcc'] = 'bananas'
    msg.set_payload('!m\n\nThis is a message')

    converted, _ = convert_tree(msg, config_with_css)
    assert isinstance(converted, MIMEMultipart)
    assert len(converted.get_payload()) == 2
    text_part = converted.get_payload()[0]
    assert text_part.get_payload(decode=True) == b'!m\n\nThis is a message'
    html_part = converted.get_payload()[1]
    assert html_part.get_payload(decode=True) == b'<p style="font-family: serif">This is a message</p>'


def test_multipart_signed(basic_config):
    msg = MIMEMultipart('signed')
    msg['Subject'] = 'Test Message'
    msg['From'] = 'from@example.com'
    msg['To'] = 'to@example.com'
    msg['Bcc'] = 'bananas'

    msg.attach(MIMEText("!m This is the signed message body. \U0001f4a9"))
    msg.attach(MIMEApplication("some-signature-here", "pgp-signature", name="signature.asc"))
    converted, _ = convert_tree(msg, basic_config)

    structure = StringIO()

    _structure(converted, fp=structure)
    assert structure.getvalue() == '\n'.join([
        'multipart/alternative',
        '    multipart/signed',
        '        text/plain',
        '        application/pgp-signature',
        '    text/html',
        ''
    ])
