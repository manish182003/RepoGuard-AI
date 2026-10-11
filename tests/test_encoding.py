import pytest
from app.utils.encoding import decode_base64_content

def test_decode_base64_content():
     encoded = "SGVsbG8gV29ybGQhCg=="

     decoded=decode_base64_content(encoded)

     assert decoded=="Hello World!\n"

def test_invalid_utf8_content():
     invalid_content="//79"

     with pytest.raises(ValueError):
          decode_base64_content(invalid_content)